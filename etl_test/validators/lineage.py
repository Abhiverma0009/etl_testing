"""Data lineage / traceability validation.

Verifies that audit/lineage columns required for traceability are present and
populated on every target row. The set of required lineage columns is taken from
the run option ``lineage_columns`` (global default) and can be overridden per
table via ``lineage_columns`` in the table options.

Typical columns: SOURCE_SYSTEM, SOURCE_FILE, LOAD_TIMESTAMP, BATCH_ID.
"""

from __future__ import annotations

from ..connectors.base import Dataset
from ..core.normalize import is_nullish
from ..core.result import Category, CheckResult, Evidence, Severity, Status
from .base import Validator, timed_check

DEFAULT_LINEAGE = ["SOURCE_SYSTEM", "LOAD_TIMESTAMP"]


class LineageValidator(Validator):
    category = Category.LINEAGE

    def validate(self, tables):
        return [self._one(t) for t in tables]

    @timed_check
    def _one(self, t) -> CheckResult:
        name = f"Lineage [{t.target_table}]"
        # A per-table override (including an explicit [] opt-out) always wins;
        # only fall back to the suite-level default when the table has no
        # override at all. `or` here would treat [] the same as "unset" and
        # incorrectly fall through to the default (Python empty-list falsiness).
        table_cols = t.options.get("lineage_columns")
        cols = table_cols if table_cols is not None else self.ctx.opt(
            "lineage_columns", DEFAULT_LINEAGE)
        if isinstance(cols, str):
            cols = [cols]
        if not cols:
            return self._check(name, table=t.target_table, status=Status.SKIPPED,
                               message="No lineage columns configured.")
        actual = self.ctx.target.list_columns(
            Dataset(name=t.target_table, table=t.fq_target() or t.target_table))
        actual_lower = {a.lower() for a in actual}
        missing_cols = [c for c in cols if c.lower() not in actual_lower]
        if missing_cols:
            return self._check(
                name, table=t.target_table, status=Status.FAIL, severity=Severity.P3,
                message=f"Lineage column(s) absent from target: {missing_cols}",
                metrics={"required": cols, "missing_columns": missing_cols})
        present = [c for c in cols]
        df = self.load_target(t, columns=present)
        null_counts = {c: int(df[c].map(is_nullish).sum()) for c in present if c in df.columns}
        offenders = {k: v for k, v in null_counts.items() if v > 0}
        if offenders:
            return self._check(
                name, table=t.target_table, status=Status.FAIL, severity=Severity.P3,
                message=f"Lineage columns present but contain nulls: {offenders}",
                metrics={"required": cols, "null_counts": offenders, "rows": len(df)})
        return self._check(name, table=t.target_table, status=Status.PASS,
                           message=f"All {len(present)} lineage columns present & populated.",
                           metrics={"required": cols, "rows": len(df)})
