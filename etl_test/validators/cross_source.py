"""Cross-source consistency.

Where the same logical entity is fed from more than one source (e.g. a deal that
appears in both ILM and Global Credit), the overlapping records must agree.

Driven by per-table ``cross_source`` options:

  options.cross_source:
    second_source:    connection name of the other source
    object:           table/file in that connection
    key_columns:      keys to align on (defaults to the table's key_columns)
    compare_columns:  columns that must agree (defaults to the table's compare cols)
    rename:           {source_col: target_col} mapping for the second source

Compares the primary source (the table's configured source) with the second
source on the overlapping keys. Skips cleanly when not configured.
"""

from __future__ import annotations

from ..connectors.base import Dataset
from ..core.comparison import compare, write_evidence
from ..core.result import Category, CheckResult, Evidence, Severity, Status
from ..core.specs import specs_from_table
from .base import Validator, timed_check


class CrossSourceValidator(Validator):
    category = Category.CROSS_SOURCE

    def validate(self, tables):
        results = []
        for t in tables:
            cfg = t.options.get("cross_source")
            if not cfg:
                results.append(self._check(
                    f"Cross-source [{t.target_table}]", table=t.target_table,
                    status=Status.SKIPPED,
                    message="No 'cross_source' config for this table."))
                continue
            results.append(self._one(t, cfg))
        return results

    @timed_check
    def _one(self, t, cfg) -> CheckResult:
        name = f"Cross-source [{t.target_table}]"
        second = cfg.get("second_source")
        obj = cfg.get("object")
        if not second or not obj:
            return CheckResult.error(name, self.category.value,
                                     "cross_source needs 'second_source' and 'object'.",
                                     target_table=t.target_table)
        keys = cfg.get("key_columns") or t.key_columns
        if not keys:
            return self._check(name, table=t.target_table, status=Status.SKIPPED,
                               message="No key columns for cross-source alignment.")
        compare_cols = cfg.get("compare_columns") or t.compare_columns()

        primary = self.load_source(t)
        if primary is None:
            return self._check(name, table=t.target_table, status=Status.SKIPPED,
                               message="Primary source unavailable.")
        try:
            conn = self.ctx.connector(second)
        except KeyError as exc:
            return CheckResult.error(name, self.category.value, str(exc),
                                     target_table=t.target_table)
        sec = conn.fetch_dataframe(Dataset(name=obj, table=obj))
        rename = cfg.get("rename") or {}
        if rename:
            sec = sec.rename(columns=rename)

        # Align to the intersection of keys present.
        usable_keys = [k for k in keys if k in primary.columns and k in sec.columns]
        if not usable_keys:
            return CheckResult.error(name, self.category.value,
                                     f"No shared key columns between sources for {keys}.",
                                     target_table=t.target_table)
        usable_cols = [c for c in compare_cols if c in primary.columns and c in sec.columns]
        specs = specs_from_table(t)
        res = compare(primary, sec, usable_keys, usable_cols, specs)
        evidence = write_evidence(res, self.ctx.evidence_dir, f"crosssource_{t.target_table}")

        # Focus on overlapping keys that disagree (value mismatches). Rows unique
        # to one source are reported but not necessarily a failure.
        status = Status.PASS if res.value_mismatches == 0 else Status.FAIL
        msg = (f"{res.matched} overlapping key(s) agree "
               f"({res.source_only} only in primary, {res.target_only} only in second)."
               if status == Status.PASS
               else f"{res.value_mismatches} overlapping key(s) disagree between sources.")
        return self._check(
            name, table=t.target_table, status=status, severity=Severity.P2,
            message=msg, metrics=res.summary_metrics(),
            sample=res.sample_mismatches,
            sample_columns=list(res.sample_mismatches[0].keys()) if res.sample_mismatches else [],
            evidence=[Evidence(**e) for e in evidence])
