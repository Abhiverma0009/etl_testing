"""Schema & structure validation.

Compares the columns declared in the mapping (the expected target schema) against
the columns actually present in the target table:
  * missing columns (declared but absent in target)  -> FAIL
  * extra columns (present in target, not mapped)     -> WARN

Case-insensitive name matching is configurable per run via option
``schema_case_sensitive`` (default False).
"""

from __future__ import annotations

from ..connectors.base import Dataset
from ..core.result import Category, CheckResult, Severity, Status
from .base import Validator, timed_check


class SchemaValidator(Validator):
    category = Category.SCHEMA

    def validate(self, tables):
        return [self._one(t) for t in tables]

    @timed_check
    def _one(self, t) -> CheckResult:
        declared = [c.target_column for c in t.columns]
        if not declared:
            return self._check(
                f"Schema [{t.target_table}]", table=t.target_table,
                status=Status.SKIPPED,
                message="No columns declared in mapping for this table.")

        ds = Dataset(name=t.target_table, table=t.fq_target() or t.target_table)
        actual = self.ctx.target.list_columns(ds)

        case_sensitive = bool(self.ctx.opt("schema_case_sensitive", False))
        norm = (lambda s: s) if case_sensitive else (lambda s: s.lower())
        actual_norm = {norm(a): a for a in actual}
        declared_norm = {norm(d): d for d in declared}

        missing = [declared_norm[k] for k in declared_norm if k not in actual_norm]
        extra = [actual_norm[k] for k in actual_norm if k not in declared_norm]

        metrics = {"declared": len(declared), "actual": len(actual),
                   "missing": missing, "extra": extra}
        if missing:
            return self._check(
                f"Schema [{t.target_table}]", table=t.target_table,
                status=Status.FAIL, severity=Severity.P2,
                message=f"{len(missing)} mapped column(s) missing in target: {missing}"
                        + (f"; {len(extra)} unmapped extra column(s): {extra}" if extra else ""),
                metrics=metrics)
        if extra:
            return self._check(
                f"Schema [{t.target_table}]", table=t.target_table,
                status=Status.WARN, severity=Severity.P4,
                message=f"All mapped columns present. {len(extra)} extra unmapped "
                        f"column(s) in target: {extra}",
                metrics=metrics)
        return self._check(
            f"Schema [{t.target_table}]", table=t.target_table,
            status=Status.PASS, message="Target schema matches mapping.",
            metrics=metrics)
