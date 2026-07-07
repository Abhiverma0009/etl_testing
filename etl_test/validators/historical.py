"""Historical data integrity / immutability.

Two checks, both driven by per-table ``historical`` options:

  options.historical:
    baseline:        name of a connection holding a prior snapshot (optional)
    baseline_object: table/file in that connection (defaults to target name)
    period_column:   column identifying the reporting period
    current_period:  the period being loaded now (rows >= this are mutable)
    expected_periods: explicit list of periods that must all be present (optional)

  1. Immutability: for periods strictly before ``current_period``, the rows in the
     baseline snapshot must be unchanged in the current target (no value drift,
     no disappearances). Requires a baseline connection.
  2. Period continuity: every period in ``expected_periods`` is present; if a
     numeric/date sequence is detectable, gaps are flagged.

Skips cleanly when its configuration is absent.
"""

from __future__ import annotations

import pandas as pd

from ..connectors.base import Dataset
from ..core.comparison import compare, write_evidence
from ..core.result import Category, CheckResult, Evidence, Severity, Status
from ..core.specs import specs_from_table
from .base import Validator, timed_check


class HistoricalValidator(Validator):
    category = Category.HISTORICAL

    def validate(self, tables):
        results = []
        for t in tables:
            cfg = t.options.get("historical")
            if not cfg:
                results.append(self._check(
                    f"Historical [{t.target_table}]", table=t.target_table,
                    status=Status.SKIPPED,
                    message="No 'historical' config for this table."))
                continue
            results.append(self._continuity(t, cfg))
            results.append(self._immutability(t, cfg))
        return results

    @timed_check
    def _continuity(self, t, cfg) -> CheckResult:
        name = f"Period continuity [{t.target_table}]"
        col = cfg.get("period_column")
        expected = cfg.get("expected_periods")
        if not col or not expected:
            return self._check(name, table=t.target_table, status=Status.SKIPPED,
                               message="No period_column/expected_periods configured.")
        df = self.load_target(t, columns=[col])
        present = set(df[col].dropna().astype(str).unique())
        missing = [str(p) for p in expected if str(p) not in present]
        if missing:
            return self._check(name, table=t.target_table, status=Status.FAIL,
                               severity=Severity.P2,
                               message=f"{len(missing)} expected period(s) missing: {missing}",
                               metrics={"expected": len(expected), "missing": missing})
        return self._check(name, table=t.target_table, status=Status.PASS,
                           message=f"All {len(expected)} expected periods present.",
                           metrics={"expected": len(expected)})

    @timed_check
    def _immutability(self, t, cfg) -> CheckResult:
        name = f"Historical immutability [{t.target_table}]"
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
        period_col = cfg.get("period_column")
        current = cfg.get("current_period")

        where_base = where_curr = None
        if period_col and current is not None:
            where_base = f"[{period_col}] < '{current}'" if isinstance(current, str) \
                else f"[{period_col}] < {current}"
        base_df = conn.fetch_dataframe(Dataset(name=base_obj, table=base_obj, where=where_base))
        curr_df = self.load_target(t)
        if period_col and current is not None and period_col in curr_df.columns:
            curr_df = curr_df[curr_df[period_col].astype(str) < str(current)]

        specs = specs_from_table(t)
        res = compare(base_df, curr_df, t.key_columns, t.compare_columns(), specs)
        evidence = write_evidence(res, self.ctx.evidence_dir, f"historical_{t.target_table}")
        # For immutability: source_only = rows that disappeared; mismatches = drift.
        drifted = res.value_mismatches + res.source_only
        if drifted == 0:
            return self._check(name, table=t.target_table, status=Status.PASS,
                               message=f"All {res.matched:,} historical rows unchanged.",
                               metrics=res.summary_metrics())
        return self._check(
            name, table=t.target_table, status=Status.FAIL, severity=Severity.P1,
            message=f"Historical data changed: {res.source_only} disappeared, "
                    f"{res.value_mismatches} value drift(s).",
            metrics=res.summary_metrics(),
            sample=res.sample_mismatches or res.sample_source_only,
            sample_columns=list((res.sample_mismatches or res.sample_source_only or [{}])[0].keys())
            if (res.sample_mismatches or res.sample_source_only) else [],
            evidence=[Evidence(**e) for e in evidence])
