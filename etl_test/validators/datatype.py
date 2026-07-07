"""Data type & format validation.

For each mapped column with a declared ``target_datatype``, verify that the
values actually loaded are coercible to that type without loss:
  * numeric columns: every non-null value parses as a number
  * date/datetime columns: every non-null value parses as a date
  * bool/flag columns: every non-null value is a recognised boolean token

Reports the count and a sample of values that fail coercion. This catches issues
like numbers stored as text, dates in the wrong format, or flags stored as
free-text.
"""

from __future__ import annotations

import pandas as pd

from ..core.result import Category, CheckResult, Evidence, Severity, Status
from ..core.normalize import is_nullish
from ..core.specs import _kind_from_datatype
from .base import Validator, timed_check

_BOOL_OK = {"true", "t", "yes", "y", "1", "1.0", "false", "f", "no", "n", "0", "0.0"}


class DataTypeValidator(Validator):
    category = Category.DATATYPE

    def validate(self, tables):
        results = []
        for t in tables:
            typed = [c for c in t.columns
                     if (c.target_datatype or c.source_datatype)
                     and _kind_from_datatype(c.target_datatype or c.source_datatype)
                     in ("numeric", "date", "datetime", "bool")]
            if not typed:
                results.append(self._check(
                    f"Data types [{t.target_table}]", table=t.target_table,
                    status=Status.SKIPPED,
                    message="No typed columns declared in mapping."))
                continue
            cols = [c.target_column for c in typed]
            try:
                df = self.load_target(t, columns=cols)
            except Exception as exc:  # noqa: BLE001
                results.append(CheckResult.error(
                    f"Data types [{t.target_table}]", self.category.value,
                    f"Failed to read target columns {cols}: {exc}",
                    target_table=t.target_table))
                continue
            results.append(self._one(t, typed, df))
        return results

    @timed_check
    def _one(self, t, typed, df) -> CheckResult:
        offenders = {}  # column -> sample bad values
        total_bad = 0
        for c in typed:
            if c.target_column not in df.columns:
                continue
            kind = _kind_from_datatype(c.target_datatype or c.source_datatype)
            series = df[c.target_column]
            non_null = series[~series.map(is_nullish)]
            if non_null.empty:
                continue
            if kind == "numeric":
                bad = non_null[pd.to_numeric(
                    non_null.astype(str).str.replace(",", "", regex=False)
                    .str.replace("$", "", regex=False), errors="coerce").isna()]
            elif kind in ("date", "datetime"):
                bad = non_null[pd.to_datetime(non_null, errors="coerce").isna()]
            elif kind == "bool":
                bad = non_null[~non_null.astype(str).str.strip().str.lower().isin(_BOOL_OK)]
            else:
                continue
            if len(bad):
                total_bad += len(bad)
                offenders[c.target_column] = {
                    "expected_kind": kind,
                    "bad_count": int(len(bad)),
                    "sample": [str(v) for v in bad.head(5).tolist()],
                }

        if not offenders:
            return self._check(
                f"Data types [{t.target_table}]", table=t.target_table,
                status=Status.PASS,
                message=f"All {len(typed)} typed columns hold valid values.",
                metrics={"typed_columns": len(typed)})

        sample_rows = [{"column": k, **v} for k, v in offenders.items()]
        path = self.ctx.evidence_dir / f"datatype_{t.target_table}.csv"
        pd.DataFrame(sample_rows).to_csv(path, index=False)
        return self._check(
            f"Data types [{t.target_table}]", table=t.target_table,
            status=Status.FAIL, severity=Severity.P3,
            message=f"{len(offenders)} column(s) contain {total_bad} value(s) that do "
                    f"not match their declared type.",
            metrics={"typed_columns": len(typed), "bad_columns": len(offenders),
                     "bad_values": total_bad},
            sample=sample_rows, sample_columns=["column", "expected_kind", "bad_count", "sample"],
            evidence=[Evidence("Type-coercion failures", str(path), len(sample_rows))])
