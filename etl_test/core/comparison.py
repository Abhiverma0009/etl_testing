"""Key-based, in-memory comparison engine (pandas).

Given a source and target DataFrame, a set of key columns, and the columns to
compare, produce a :class:`ComparisonResult` describing:
  * matched rows
  * source-only rows  (present in source, missing in target)  -> data loss
  * target-only rows  (present in target, missing in source)   -> spurious rows
  * value mismatches  (same key, different value) with per-column detail
  * duplicate keys on each side (reported; excluded from 1:1 matching)

It deliberately never explodes on duplicate keys: duplicates are split out and
reported rather than producing a cartesian join.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .normalize import ColumnNormSpec, NULL, normalize_frame, values_equal

log = logging.getLogger(__name__)

SAMPLE_CAP = 100  # rows kept inline for the dashboard


@dataclass
class ComparisonResult:
    key_columns: list[str]
    compare_columns: list[str]
    source_total: int = 0
    target_total: int = 0
    matched: int = 0                       # keys present on both sides (1:1)
    values_matched: int = 0                # of matched keys, rows fully equal
    value_mismatches: int = 0
    source_only: int = 0
    target_only: int = 0
    source_dup_keys: int = 0
    target_dup_keys: int = 0
    # per-column mismatch counts
    column_mismatch_counts: dict[str, int] = field(default_factory=dict)
    # inline samples (capped)
    sample_source_only: list[dict] = field(default_factory=list)
    sample_target_only: list[dict] = field(default_factory=list)
    sample_mismatches: list[dict] = field(default_factory=list)
    # full evidence frames (not serialized; written to disk by caller)
    _source_only_df: pd.DataFrame | None = field(default=None, repr=False)
    _target_only_df: pd.DataFrame | None = field(default=None, repr=False)
    _mismatch_df: pd.DataFrame | None = field(default=None, repr=False)
    _dup_df: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def is_clean(self) -> bool:
        return (self.source_only == 0 and self.target_only == 0
                and self.value_mismatches == 0
                and self.source_dup_keys == 0 and self.target_dup_keys == 0)

    def summary_metrics(self) -> dict[str, Any]:
        return {
            "source_total": self.source_total,
            "target_total": self.target_total,
            "matched_keys": self.matched,
            "values_matched": self.values_matched,
            "value_mismatches": self.value_mismatches,
            "source_only": self.source_only,
            "target_only": self.target_only,
            "source_dup_keys": self.source_dup_keys,
            "target_dup_keys": self.target_dup_keys,
            "column_mismatch_counts": self.column_mismatch_counts,
        }


def _dedupe_keys(df: pd.DataFrame, keys: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split into (unique-key rows, duplicate-key rows)."""
    dup_mask = df.duplicated(subset=keys, keep=False)
    return df[~dup_mask].copy(), df[dup_mask].copy()


def _display(df: pd.DataFrame) -> pd.DataFrame:
    """Replace the NULL sentinel with the literal '(null)' for human-readable output."""
    return df.replace({NULL: "(null)"})


def compare(
    source: pd.DataFrame,
    target: pd.DataFrame,
    key_columns: list[str],
    compare_columns: list[str] | None,
    norm_specs: dict[str, ColumnNormSpec] | None = None,
) -> ComparisonResult:
    norm_specs = norm_specs or {}
    if not key_columns:
        raise ValueError("compare() requires at least one key column.")

    missing_src_keys = [k for k in key_columns if k not in source.columns]
    missing_tgt_keys = [k for k in key_columns if k not in target.columns]
    if missing_src_keys or missing_tgt_keys:
        raise ValueError(
            f"Key column(s) missing - source:{missing_src_keys} target:{missing_tgt_keys}. "
            f"source cols={list(source.columns)} target cols={list(target.columns)}"
        )

    # Determine compare columns = requested ∩ both frames (report schema drift).
    if compare_columns is None:
        shared = [c for c in source.columns if c in target.columns and c not in key_columns]
        compare_columns = shared
    usable = [c for c in compare_columns
              if c in source.columns and c in target.columns and c not in key_columns]

    res = ComparisonResult(key_columns=list(key_columns), compare_columns=list(usable))
    res.source_total = len(source)
    res.target_total = len(target)

    # Normalize only the columns we use.
    src_cols = key_columns + usable
    tgt_cols = key_columns + usable
    src_n = normalize_frame(source[src_cols], norm_specs)
    tgt_n = normalize_frame(target[tgt_cols], norm_specs)

    # Split out duplicate keys.
    src_u, src_dup = _dedupe_keys(src_n, key_columns)
    tgt_u, tgt_dup = _dedupe_keys(tgt_n, key_columns)
    res.source_dup_keys = src_dup[key_columns].drop_duplicates().shape[0]
    res.target_dup_keys = tgt_dup[key_columns].drop_duplicates().shape[0]
    if not src_dup.empty or not tgt_dup.empty:
        dup = pd.concat([
            src_dup.assign(__side="source"),
            tgt_dup.assign(__side="target"),
        ], ignore_index=True)
        res._dup_df = _display(dup)

    # Merge on keys.
    merged = src_u.merge(
        tgt_u, on=key_columns, how="outer", indicator=True,
        suffixes=("__src", "__tgt"),
    )

    left_only = merged[merged["_merge"] == "left_only"]
    right_only = merged[merged["_merge"] == "right_only"]
    both = merged[merged["_merge"] == "both"]

    res.source_only = len(left_only)
    res.target_only = len(right_only)
    res.matched = len(both)

    if res.source_only:
        cols = key_columns + [f"{c}__src" for c in usable]
        df = left_only[cols].rename(columns={f"{c}__src": c for c in usable})
        res._source_only_df = _display(df)
        res.sample_source_only = res._source_only_df.head(SAMPLE_CAP).to_dict("records")
    if res.target_only:
        cols = key_columns + [f"{c}__tgt" for c in usable]
        df = right_only[cols].rename(columns={f"{c}__tgt": c for c in usable})
        res._target_only_df = _display(df)
        res.sample_target_only = res._target_only_df.head(SAMPLE_CAP).to_dict("records")

    # Value comparison on matched keys.
    if not both.empty and usable:
        mismatch_rows, col_counts = _compare_values(both, key_columns, usable, norm_specs)
        res.value_mismatches = len(mismatch_rows)
        res.values_matched = res.matched - res.value_mismatches
        res.column_mismatch_counts = col_counts
        if not mismatch_rows.empty:
            res._mismatch_df = mismatch_rows
            res.sample_mismatches = mismatch_rows.head(SAMPLE_CAP).to_dict("records")
    else:
        res.values_matched = res.matched

    return res


def _compare_values(
    both: pd.DataFrame,
    key_columns: list[str],
    usable: list[str],
    norm_specs: dict[str, ColumnNormSpec],
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Return (long-format mismatch frame, per-column mismatch counts)."""
    col_counts: dict[str, int] = {}
    # Build a boolean mismatch matrix.
    mismatch_any = pd.Series(False, index=both.index)
    per_col_mask: dict[str, pd.Series] = {}
    for col in usable:
        sc, tc = f"{col}__src", f"{col}__tgt"
        spec = norm_specs.get(col, ColumnNormSpec(name=col))
        a = both[sc]
        b = both[tc]
        if spec.numeric_tolerance is not None or spec.relative_tolerance is not None:
            mask = pd.Series(
                [not values_equal(x, y, spec) for x, y in zip(a, b)],
                index=both.index,
            )
        else:
            # Direct (NULL sentinel compares equal to NULL; NaN won't appear).
            mask = ~(a.eq(b) | (a.isna() & b.isna()))
        per_col_mask[col] = mask
        cnt = int(mask.sum())
        if cnt:
            col_counts[col] = cnt
        mismatch_any |= mask

    bad = both[mismatch_any]
    if bad.empty:
        return pd.DataFrame(), col_counts

    # Emit one row per (key, column) mismatch for a tidy evidence table.
    records: list[dict] = []
    for idx, row in bad.iterrows():
        key_part = {k: (row[k] if row[k] is not NULL else "(null)") for k in key_columns}
        for col in usable:
            if per_col_mask[col].loc[idx]:
                sv = row[f"{col}__src"]
                tv = row[f"{col}__tgt"]
                rec = dict(key_part)
                rec["column"] = col
                rec["source_value"] = "(null)" if sv is NULL else sv
                rec["target_value"] = "(null)" if tv is NULL else tv
                records.append(rec)
    return pd.DataFrame.from_records(records), col_counts


def write_evidence(res: ComparisonResult, out_dir: Path, prefix: str) -> dict[str, Any]:
    """Write full evidence frames to CSV. Returns a list of evidence descriptors."""
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence: list[dict[str, Any]] = []

    def _dump(df: pd.DataFrame | None, label: str, suffix: str) -> None:
        if df is not None and not df.empty:
            path = out_dir / f"{prefix}_{suffix}.csv"
            df.to_csv(path, index=False, encoding="utf-8")
            evidence.append({"label": label, "path": str(path), "rows": len(df)})

    _dump(res._source_only_df, "Source-only rows (missing in target)", "source_only")
    _dump(res._target_only_df, "Target-only rows (extra in target)", "target_only")
    _dump(res._mismatch_df, "Value mismatches (per cell)", "mismatches")
    _dump(res._dup_df, "Duplicate keys", "duplicate_keys")
    return evidence
