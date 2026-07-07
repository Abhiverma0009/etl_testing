"""Referential integrity validation (within the target).

For each relationship declared in the ReferentialIntegrity sheet, verify every
non-null child key value exists in the parent table — i.e. no orphan child rows.
Null child keys are reported separately (an orphan vs a missing-FK is a different
problem).
"""

from __future__ import annotations

import pandas as pd

from ..core.normalize import is_nullish
from ..core.result import Category, CheckResult, Evidence, Severity, Status
from .base import Validator, timed_check


class ReferentialIntegrityValidator(Validator):
    category = Category.REFERENTIAL_INTEGRITY

    def validate(self, tables):
        names = {t.target_table for t in tables}
        rules = [r for r in self.ctx.mapping.ref_integrity
                 if r.active and (r.child_table in names or r.parent_table in names)]
        if not rules:
            return [self._check("Referential integrity", status=Status.SKIPPED,
                                message="No referential-integrity rules defined.")]

        tmap = {t.target_table: t for t in self.ctx.mapping.tables.values()}
        results = []
        cache: dict[str, pd.DataFrame] = {}
        for r in rules:
            try:
                results.append(self._one(r, tmap, cache))
            except Exception as exc:  # noqa: BLE001
                results.append(CheckResult.error(
                    f"FK {r.child_table}->{r.parent_table}", self.category.value,
                    str(exc), target_table=r.child_table))
        return results

    def _load(self, table_name, cols, tmap, cache):
        key = f"{table_name}:{','.join(cols)}"
        if key not in cache:
            t = tmap.get(table_name)
            if t is None:
                raise ValueError(f"Table {table_name!r} not in mapping; cannot load for FK check.")
            cache[key] = self.load_target(t, columns=cols)
        return cache[key]

    @timed_check
    def _one(self, r, tmap, cache) -> CheckResult:
        if len(r.child_columns) != len(r.parent_columns):
            return self._check(
                f"FK {r.child_table}->{r.parent_table}", table=r.child_table,
                status=Status.ERROR, severity=Severity.coerce(r.severity, Severity.P2),
                message="child/parent column counts differ.")
        child = self._load(r.child_table, r.child_columns, tmap, cache)
        parent = self._load(r.parent_table, r.parent_columns, tmap, cache)

        # Null child keys are not orphans; report separately.
        null_mask = child[r.child_columns].apply(
            lambda row: any(is_nullish(v) for v in row), axis=1)
        null_n = int(null_mask.sum())
        child_nn = child[~null_mask]

        # Build a set of parent key tuples (as strings to avoid dtype mismatch).
        parent_keys = set(
            map(tuple, parent[r.parent_columns].astype(str).apply(
                lambda s: s.str.strip()).values.tolist()))
        child_tuples = child_nn[r.child_columns].astype(str).apply(
            lambda s: s.str.strip())
        exists = child_tuples.apply(lambda row: tuple(row) in parent_keys, axis=1)
        orphans = child_nn[~exists]

        sev = Severity.coerce(r.severity, Severity.P2)
        metrics = {"child_rows": len(child), "parent_rows": len(parent),
                   "orphans": int(len(orphans)), "null_child_keys": null_n}
        if len(orphans) == 0:
            status = Status.PASS if null_n == 0 else Status.WARN
            msg = "All child keys resolve to a parent."
            if null_n:
                msg += f" ({null_n} child rows have null FK — not counted as orphans.)"
            return self._check(f"FK {r.child_table}.{r.child_columns} -> "
                               f"{r.parent_table}.{r.parent_columns}",
                               table=r.child_table, status=status,
                               severity=sev if null_n else Severity.P4,
                               message=msg, metrics=metrics)
        path = self.ctx.evidence_dir / f"fk_{r.child_table}_to_{r.parent_table}.csv"
        orphans.to_csv(path, index=False)
        return self._check(
            f"FK {r.child_table}.{r.child_columns} -> {r.parent_table}.{r.parent_columns}",
            table=r.child_table, status=Status.FAIL, severity=sev,
            message=f"{len(orphans)} orphan child row(s) with no matching parent.",
            metrics=metrics, sample=orphans.head(100).to_dict("records"),
            sample_columns=list(orphans.columns),
            evidence=[Evidence("Orphan child rows", str(path), len(orphans))])
