"""Deduplication validation.

Confirms the target has no duplicate business keys (the dedup logic in Silver/Gold
worked). Operates purely on the target using each table's ``key_columns``.
"""

from __future__ import annotations

from ..core.result import Category, CheckResult, Evidence, Severity, Status
from .base import Validator, timed_check


class DeduplicationValidator(Validator):
    category = Category.DEDUPLICATION

    def validate(self, tables):
        return [self._one(t) for t in tables]

    @timed_check
    def _one(self, t) -> CheckResult:
        name = f"Deduplication [{t.target_table}]"
        if not t.key_columns:
            return self._check(name, table=t.target_table, status=Status.SKIPPED,
                               message="No key_columns declared; cannot detect duplicates.")
        df = self.load_target(t, columns=t.key_columns)
        missing = [k for k in t.key_columns if k not in df.columns]
        if missing:
            return self._check(name, table=t.target_table, status=Status.ERROR,
                               severity=Severity.P2,
                               message=f"Key column(s) missing in target: {missing}")
        dup_mask = df.duplicated(subset=t.key_columns, keep=False)
        dups = df[dup_mask]
        n_keys = dups[t.key_columns].drop_duplicates().shape[0]
        if dups.empty:
            return self._check(name, table=t.target_table, status=Status.PASS,
                               message=f"No duplicate keys across {len(df):,} rows.",
                               metrics={"rows": len(df), "duplicate_keys": 0})
        path = self.ctx.evidence_dir / f"dedup_{t.target_table}.csv"
        dups.sort_values(t.key_columns).to_csv(path, index=False)
        return self._check(
            name, table=t.target_table, status=Status.FAIL, severity=Severity.P2,
            message=f"{n_keys} duplicated key value(s) across {len(dups)} rows.",
            metrics={"rows": len(df), "duplicate_keys": n_keys,
                     "duplicate_rows": int(len(dups))},
            sample=dups.head(100).to_dict("records"),
            sample_columns=list(dups.columns),
            evidence=[Evidence("Duplicate-key rows", str(path), len(dups))])
