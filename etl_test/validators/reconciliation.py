"""Reconciliation / variance analysis.

The flagship end-to-end check: full source-vs-target row-level reconciliation on
all mapped compare columns, plus value-level aggregate reconciliation of numeric
columns against a variance threshold (default 0.01%, per the test strategy).

Produces:
  * a row-level reconciliation check (missing/extra/mismatched), and
  * one aggregate-variance check per table summing each numeric column on both
    sides and flagging columns whose relative variance exceeds the threshold.
"""

from __future__ import annotations

import pandas as pd

from ..core.normalize import coerce_numeric, is_nullish
from ..core.result import Category, CheckResult, Evidence, Severity, Status
from ..core.specs import _kind_from_datatype
from .base import Validator, timed_check
from ._keycompare import key_compare


class ReconciliationValidator(Validator):
    category = Category.RECONCILIATION

    def validate(self, tables):
        results = []
        threshold = float(self.ctx.opt("variance_threshold", 0.0001))  # 0.01%
        tol = self.ctx.opt("numeric_tolerance")
        for t in tables:
            sev = Severity.coerce(t.options.get("severity"), Severity.P1)
            chk, _ = key_compare(self, t, t.compare_columns(),
                                 f"Reconciliation [{t.target_table}]", sev,
                                 default_tolerance=tol)
            results.append(chk)
            results.append(self._variance(t, threshold))
        return results

    @timed_check
    def _variance(self, t, threshold) -> CheckResult:
        name = f"Aggregate variance [{t.target_table}]"
        numeric_cols = [c.target_column for c in t.columns
                        if _kind_from_datatype(c.target_datatype or c.source_datatype) == "numeric"
                        and c.compare]
        if not numeric_cols:
            return self._check(name, table=t.target_table, status=Status.SKIPPED,
                               message="No numeric compare columns declared.")
        src = self.load_source(t, columns=None)
        if src is None:
            return self._check(name, table=t.target_table, status=Status.SKIPPED,
                               message="No source available for variance check.")
        tgt = self.load_target(t)
        rows = []
        worst = 0.0
        for col in numeric_cols:
            if col not in src.columns or col not in tgt.columns:
                continue
            s_sum = coerce_numeric(src[col]).sum()
            t_sum = coerce_numeric(tgt[col]).sum()
            denom = abs(s_sum) if s_sum else (abs(t_sum) if t_sum else 0.0)
            variance = 0.0 if denom == 0 else abs(t_sum - s_sum) / denom
            worst = max(worst, variance)
            rows.append({"column": col, "source_sum": s_sum, "target_sum": t_sum,
                         "abs_diff": t_sum - s_sum, "rel_variance": variance,
                         "within_threshold": variance <= threshold})
        if not rows:
            return self._check(name, table=t.target_table, status=Status.SKIPPED,
                               message="Numeric columns not present on both sides.")
        breaches = [r for r in rows if not r["within_threshold"]]
        status = Status.PASS if not breaches else Status.FAIL
        msg = (f"All {len(rows)} numeric column sums within {threshold:.4%} "
               f"(worst {worst:.4%})." if status == Status.PASS
               else f"{len(breaches)} column(s) exceed {threshold:.4%} variance "
                    f"(worst {worst:.4%}).")
        path = self.ctx.evidence_dir / f"variance_{t.target_table}.csv"
        pd.DataFrame(rows).to_csv(path, index=False)
        return self._check(
            name, table=t.target_table, status=status,
            severity=Severity.coerce(t.options.get("severity"), Severity.P1),
            message=msg, metrics={"threshold": threshold, "worst_variance": worst,
                                  "columns": len(rows), "breaches": len(breaches)},
            sample=rows, sample_columns=["column", "source_sum", "target_sum",
                                         "abs_diff", "rel_variance", "within_threshold"],
            evidence=[Evidence("Per-column aggregate variance", str(path), len(rows))])
