"""Incremental / delta load integrity.

Compares a baseline snapshot (state before the incremental run) with the current
target to confirm the delta behaved correctly:

  options.incremental:
    baseline:          connection name holding the pre-load snapshot
    baseline_object:   object in that connection (defaults to target name)
    updatable_columns: columns allowed to change for existing keys (default: none)
    allow_deletes:     whether keys may disappear (default false)

Findings:
  * existing keys whose non-updatable columns changed -> FAIL (unexpected mutation)
  * keys present in baseline but gone now (when allow_deletes is false) -> FAIL
  * brand-new keys -> reported as additions (INFO in metrics)

Skips cleanly when no incremental config / baseline is provided.
"""

from __future__ import annotations

import pandas as pd

from ..connectors.base import Dataset
from ..core.comparison import compare, write_evidence
from ..core.result import Category, CheckResult, Evidence, Severity, Status
from ..core.specs import specs_from_table
from .base import Validator, timed_check


class IncrementalValidator(Validator):
    category = Category.INCREMENTAL

    def validate(self, tables):
        results = []
        for t in tables:
            cfg = t.options.get("incremental")
            if not cfg:
                results.append(self._check(
                    f"Incremental [{t.target_table}]", table=t.target_table,
                    status=Status.SKIPPED,
                    message="No 'incremental' config for this table."))
                continue
            results.append(self._one(t, cfg))
        return results

    @timed_check
    def _one(self, t, cfg) -> CheckResult:
        name = f"Incremental integrity [{t.target_table}]"
        baseline = cfg.get("baseline")
        if not baseline:
            return self._check(name, table=t.target_table, status=Status.SKIPPED,
                               message="No baseline snapshot configured.")
        if not t.key_columns:
            return self._check(name, table=t.target_table, status=Status.SKIPPED,
                               message="No key_columns; cannot compare snapshots.")
        try:
            conn = self.ctx.connector(baseline)
        except KeyError as exc:
            return CheckResult.error(name, self.category.value, str(exc),
                                     target_table=t.target_table)

        base_obj = cfg.get("baseline_object", t.target_table)
        updatable = set(cfg.get("updatable_columns") or [])
        allow_deletes = bool(cfg.get("allow_deletes", False))

        base_df = conn.fetch_dataframe(Dataset(name=base_obj, table=base_obj))
        curr_df = self.load_target(t)

        # Compare only non-updatable columns for existing keys.
        compare_cols = [c for c in t.compare_columns() if c not in updatable]
        specs = specs_from_table(t)
        res = compare(base_df, curr_df, t.key_columns, compare_cols, specs)
        evidence = write_evidence(res, self.ctx.evidence_dir, f"incremental_{t.target_table}")

        additions = res.target_only      # new keys
        deletions = res.source_only      # keys gone since baseline
        mutations = res.value_mismatches  # changed non-updatable values

        problems = mutations + (0 if allow_deletes else deletions)
        metrics = {**res.summary_metrics(), "additions": additions,
                   "deletions": deletions, "unexpected_mutations": mutations,
                   "allow_deletes": allow_deletes, "updatable_columns": sorted(updatable)}
        if problems == 0:
            return self._check(
                name, table=t.target_table, status=Status.PASS,
                message=f"Delta clean: {additions} new key(s), "
                        f"{res.matched} existing unchanged"
                        + (f", {deletions} deleted (allowed)" if allow_deletes and deletions else "")
                        + ".",
                metrics=metrics)
        parts = []
        if mutations:
            parts.append(f"{mutations} existing key(s) had non-updatable columns change")
        if deletions and not allow_deletes:
            parts.append(f"{deletions} key(s) disappeared (deletes not allowed)")
        return self._check(
            name, table=t.target_table, status=Status.FAIL, severity=Severity.P2,
            message="; ".join(parts) + ".", metrics=metrics,
            sample=res.sample_mismatches or res.sample_source_only,
            sample_columns=list((res.sample_mismatches or res.sample_source_only or [{}])[0].keys())
            if (res.sample_mismatches or res.sample_source_only) else [],
            evidence=[Evidence(**e) for e in evidence])
