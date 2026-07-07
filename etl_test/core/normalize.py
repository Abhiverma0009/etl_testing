"""Value normalization — the single most important defence against false
mismatches when comparing data across heterogeneous engines (Access/SQL Server/
Snowflake/files).

Each column can be normalized according to a :class:`ColumnNormSpec`:
  * whitespace trimming
  * case folding (only when not case-sensitive)
  * numeric coercion with optional absolute/relative tolerance and rounding
  * date/datetime coercion (optionally stripping the time component / timezone)
  * boolean/flag canonicalization (Y/1/T/TRUE -> True)
  * **null canonicalization that deliberately keeps null distinct from 0 / ""**
    (critical for valuation data: a null FMV is NOT the same as a zero FMV).

The functions return pandas Series so they vectorize over whole columns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Strings that represent "null" coming out of CSV/Access/etc. NOTE: empty string
# is treated as null ONLY when treat_blank_as_null is set; "0" is NEVER null.
_NULL_TOKENS = {"", "null", "none", "nan", "na", "n/a", "<null>", "(null)"}
_TRUE_TOKENS = {"true", "t", "yes", "y", "1", "1.0"}
_FALSE_TOKENS = {"false", "f", "no", "n", "0", "0.0"}

# Canonical sentinel for null so it survives groupby/merge keys reliably.
NULL = "\x00NULL\x00"


@dataclass
class ColumnNormSpec:
    name: str
    kind: str = "auto"            # auto | string | numeric | date | datetime | bool
    case_sensitive: bool = False
    trim: bool = True
    treat_blank_as_null: bool = True
    numeric_tolerance: float | None = None   # absolute tolerance
    relative_tolerance: float | None = None
    round_to: int | None = None
    date_only: bool = True        # for datetime: drop the time part when comparing


def coerce_numeric(s: pd.Series, treat_blank_as_null: bool = True) -> pd.Series:
    """Coerce a Series to float, stripping thousands separators and currency
    symbols first (legacy Access/CSV often store amounts as text like
    '1,250,000.00'). Null-ish values become NaN. Shared by aggregate/variance
    and measure checks so they agree with row-level normalization."""
    def _clean(v: Any) -> Any:
        if is_nullish(v, treat_blank_as_null):
            return np.nan
        if isinstance(v, str):
            v = (v.strip().replace(",", "").replace("$", "")
                 .replace("€", "").replace("£", ""))
            if v in ("", "-"):
                return np.nan
        return v
    return pd.to_numeric(s.map(_clean), errors="coerce")


def is_nullish(value: Any, treat_blank_as_null: bool = True) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and np.isnan(value):
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        s = value.strip().lower()
        if s in _NULL_TOKENS:
            # empty string only counts as null when explicitly asked
            if s == "" and not treat_blank_as_null:
                return False
            return True
    return False


def _to_null_mask(s: pd.Series, treat_blank_as_null: bool) -> pd.Series:
    return s.apply(lambda v: is_nullish(v, treat_blank_as_null))


def normalize_string(s: pd.Series, spec: ColumnNormSpec) -> pd.Series:
    null_mask = _to_null_mask(s, spec.treat_blank_as_null)

    def _fmt(v: Any) -> Any:
        text = str(v)
        if spec.trim:
            text = text.strip()
        if not spec.case_sensitive:
            text = text.casefold()
        return text

    out = s.astype("object").map(_fmt)
    # Overwrite null positions with the sentinel AFTER formatting so the sentinel
    # itself is never trimmed/casefolded.
    out[null_mask.values] = NULL
    return out


def normalize_numeric(s: pd.Series, spec: ColumnNormSpec) -> pd.Series:
    null_mask = _to_null_mask(s, spec.treat_blank_as_null)
    # Strip thousands separators / currency symbols before coercion.
    def _clean(v: Any) -> Any:
        if is_nullish(v, spec.treat_blank_as_null):
            return np.nan
        if isinstance(v, str):
            v = v.strip().replace(",", "").replace("$", "").replace("€", "").replace("£", "")
            if v in ("", "-"):
                return np.nan
        return v

    coerced = pd.to_numeric(s.map(_clean), errors="coerce")
    if spec.round_to is not None:
        coerced = coerced.round(spec.round_to)
    # Represent null distinctly from 0.
    out = coerced.astype("object")
    out[null_mask.values | coerced.isna().values] = NULL
    return out


def normalize_datetime(s: pd.Series, spec: ColumnNormSpec) -> pd.Series:
    null_mask = _to_null_mask(s, spec.treat_blank_as_null)
    dt = pd.to_datetime(s, errors="coerce", utc=False)
    try:
        if getattr(dt.dtype, "tz", None) is not None:
            dt = dt.dt.tz_localize(None)
    except (AttributeError, TypeError):
        pass
    if spec.date_only:
        formatted = dt.dt.strftime("%Y-%m-%d")
    else:
        formatted = dt.dt.strftime("%Y-%m-%d %H:%M:%S")
    out = formatted.astype("object")
    out[null_mask.values | dt.isna().values] = NULL
    return out


def normalize_bool(s: pd.Series, spec: ColumnNormSpec) -> pd.Series:
    null_mask = _to_null_mask(s, spec.treat_blank_as_null)

    def _b(v: Any) -> Any:
        if is_nullish(v, spec.treat_blank_as_null):
            return NULL
        text = str(v).strip().lower()
        if text in _TRUE_TOKENS:
            return "true"
        if text in _FALSE_TOKENS:
            return "false"
        return text  # leave unknown tokens as-is (will surface as mismatch)

    out = s.astype("object").map(_b)
    out[null_mask.values] = NULL
    return out


def _infer_kind(s: pd.Series, spec: ColumnNormSpec) -> str:
    if spec.kind != "auto":
        return spec.kind
    # Use pandas dtype hints, then fall back to string.
    if pd.api.types.is_bool_dtype(s):
        return "bool"
    if pd.api.types.is_numeric_dtype(s):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    return "string"


def normalize_series(s: pd.Series, spec: ColumnNormSpec) -> pd.Series:
    kind = _infer_kind(s, spec)
    if kind == "numeric":
        return normalize_numeric(s, spec)
    if kind in ("date", "datetime"):
        spec2 = spec
        if kind == "datetime" and spec.date_only is None:
            spec2 = spec
        return normalize_datetime(s, spec)
    if kind == "bool":
        return normalize_bool(s, spec)
    return normalize_string(s, spec)


def normalize_frame(df: pd.DataFrame, specs: dict[str, ColumnNormSpec]) -> pd.DataFrame:
    """Return a copy with each named column normalized. Columns without a spec
    are normalized as auto-detected strings/numbers via a default spec."""
    out = pd.DataFrame(index=df.index)
    for col in df.columns:
        spec = specs.get(col, ColumnNormSpec(name=col))
        try:
            out[col] = normalize_series(df[col], spec).values
        except Exception as exc:  # noqa: BLE001 - never let one column kill the run
            log.warning("normalize failed for column %r (%s); using string fallback",
                        col, exc)
            out[col] = normalize_string(df[col].astype("object"),
                                        ColumnNormSpec(name=col)).values
    return out


def values_equal(a: Any, b: Any, spec: ColumnNormSpec) -> bool:
    """Compare two already-normalized scalar values, honouring numeric tolerance."""
    a_null = a is NULL or a == NULL
    b_null = b is NULL or b == NULL
    if a_null or b_null:
        return a_null and b_null
    if spec.numeric_tolerance is not None or spec.relative_tolerance is not None:
        try:
            fa, fb = float(a), float(b)
        except (TypeError, ValueError):
            return a == b
        atol = spec.numeric_tolerance or 0.0
        rtol = spec.relative_tolerance or 0.0
        return abs(fa - fb) <= max(atol, rtol * max(abs(fa), abs(fb)))
    return a == b
