"""Row/record count validation.

Checks per table:
  * overall source vs target row count (data loss / spurious rows)
  * optional per-group counts (e.g. per fund / per period) when the table mapping
    declares ``group_by`` in its options.

When no source is available (target-only table) the check reports the target
count as INFO (PASS) rather than failing.
"""

from __future__ import annotations

from ..core.result import Category, CheckResult, Severity, Status
from ..mapping.models import TableMapping
from .base import Validator, timed_check


class RowCountValidator(Validator):
    category = Category.ROW_COUNT

    def validate(self, tables):
        results = []
        for t in tables:
            results.append(self._overall(t))
            group_by = t.options.get("group_by")
            if group_by:
                results.append(self._by_group(t, group_by))
        return results

    @timed_check
    def _overall(self, t: TableMapping) -> CheckResult:
        from ..connectors.base import Dataset
        tgt_ds = Dataset(name=t.target_table, table=t.fq_target() or t.target_table,
                         where=t.options.get("target_where"))
        target_n = self.ctx.target.get_row_count(tgt_ds)

        if self.ctx.source is None or not t.source_object:
            return self._check(
                f"Row count [{t.target_table}]", table=t.target_table,
                status=Status.PASS, severity=Severity.P3,
                message=f"Target has {target_n:,} rows (no source to compare).",
                metrics={"target_rows": target_n},
            )

        src_ds = Dataset(name=t.source_object, table=t.source_object,
                         where=t.options.get("source_where"))
        source_n = self.ctx.source.get_row_count(src_ds)
        diff = target_n - source_n
        status = Status.PASS if diff == 0 else Status.FAIL
        msg = ("Counts match." if diff == 0
               else f"Count mismatch: target-source = {diff:+,} "
                    f"({'extra rows in target' if diff > 0 else 'rows missing in target'}).")
        return self._check(
            f"Row count [{t.target_table}]", table=t.target_table,
            status=status, severity=Severity.coerce(t.options.get("severity"), Severity.P1),
            message=msg,
            metrics={"source_rows": source_n, "target_rows": target_n, "difference": diff},
        )

    @timed_check
    def _by_group(self, t: TableMapping, group_by) -> CheckResult:
        if isinstance(group_by, str):
            group_by = [group_by]
        src = self.load_source(t, columns=None)
        tgt = self.load_target(t)
        if src is None:
            return self._check(
                f"Row count by {group_by} [{t.target_table}]", table=t.target_table,
                status=Status.SKIPPED, message="No source available for grouped count.")

        missing = [g for g in group_by if g not in tgt.columns or g not in src.columns]
        if missing:
            return self._check(
                f"Row count by {group_by} [{t.target_table}]", table=t.target_table,
                status=Status.ERROR, severity=Severity.P2,
                message=f"group_by column(s) not present on both sides: {missing}")

        s = src.groupby(group_by, dropna=False).size().rename("source_rows")
        d = tgt.groupby(group_by, dropna=False).size().rename("target_rows")
        merged = s.to_frame().join(d, how="outer").fillna(0).astype(int)
        merged["difference"] = merged["target_rows"] - merged["source_rows"]
        bad = merged[merged["difference"] != 0].reset_index()

        if bad.empty:
            return self._check(
                f"Row count by {group_by} [{t.target_table}]", table=t.target_table,
                status=Status.PASS, message=f"All {len(merged)} groups reconcile.",
                metrics={"groups": int(len(merged))})

        evidence = []
        path = self.ctx.evidence_dir / f"rowcount_{t.target_table}_by_group.csv"
        bad.to_csv(path, index=False)
        evidence.append({"label": "Groups with count differences", "path": str(path),
                         "rows": len(bad)})
        from ..core.result import Evidence
        return self._check(
            f"Row count by {group_by} [{t.target_table}]", table=t.target_table,
            status=Status.FAIL, severity=Severity.coerce(t.options.get("severity"), Severity.P1),
            message=f"{len(bad)} of {len(merged)} groups have mismatched counts.",
            metrics={"groups": int(len(merged)), "mismatched_groups": int(len(bad))},
            sample=bad.head(100).to_dict("records"),
            sample_columns=list(bad.columns),
            evidence=[Evidence(**e) for e in evidence],
        )
