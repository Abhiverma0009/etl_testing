"""Completeness validation.

Two complementary checks per table:
  1. Mandatory-column completeness: columns declared NOT nullable in the mapping
     must have zero nulls in the target.
  2. Expected-partition completeness: when the table mapping declares
     ``expected_values`` (e.g. a list of periods, files, or fund codes for a
     given column), verify every expected value is present — and, when
     ``forbidden_values`` is declared (e.g. CO2 files that must be excluded),
     verify none are present.
"""

from __future__ import annotations

import pandas as pd

from ..core.normalize import is_nullish
from ..core.result import Category, CheckResult, Evidence, Severity, Status
from .base import Validator, timed_check


class CompletenessValidator(Validator):
    category = Category.COMPLETENESS

    def validate(self, tables):
        results = []
        for t in tables:
            results.append(self._mandatory(t))
            for chk in self._partitions(t):
                results.append(chk)
        return results

    @timed_check
    def _mandatory(self, t) -> CheckResult:
        mandatory = [c.target_column for c in t.columns if not c.nullable]
        if not mandatory:
            return self._check(
                f"Mandatory completeness [{t.target_table}]", table=t.target_table,
                status=Status.SKIPPED, message="No NOT-NULL columns declared.")
        df = self.load_target(t, columns=mandatory)
        null_counts = {col: int(df[col].map(is_nullish).sum())
                       for col in mandatory if col in df.columns}
        offenders = {k: v for k, v in null_counts.items() if v > 0}
        if not offenders:
            return self._check(
                f"Mandatory completeness [{t.target_table}]", table=t.target_table,
                status=Status.PASS,
                message=f"All {len(mandatory)} mandatory columns fully populated.",
                metrics={"mandatory_columns": len(mandatory), "rows": len(df)})
        return self._check(
            f"Mandatory completeness [{t.target_table}]", table=t.target_table,
            status=Status.FAIL, severity=Severity.P2,
            message=f"{len(offenders)} mandatory column(s) contain nulls: {offenders}",
            metrics={"mandatory_columns": len(mandatory), "rows": len(df),
                     "null_counts": offenders})

    def _partitions(self, t):
        spec = t.options.get("completeness")
        if not spec:
            return []
        if isinstance(spec, dict):
            spec = [spec]
        out = []
        for s in spec:
            out.append(self._one_partition(t, s))
        return out

    @timed_check
    def _one_partition(self, t, s) -> CheckResult:
        col = s.get("column")
        expected = s.get("expected_values") or []
        forbidden = s.get("forbidden_values") or []
        name = f"Completeness of {col} [{t.target_table}]"
        if not col:
            return self._check(name, table=t.target_table, status=Status.ERROR,
                               severity=Severity.P3,
                               message="completeness spec missing 'column'.")
        df = self.load_target(t, columns=[col])
        if col not in df.columns:
            return self._check(name, table=t.target_table, status=Status.ERROR,
                               severity=Severity.P3,
                               message=f"Column {col!r} not found in target.")
        present = set(df[col].dropna().astype(str).unique())
        missing = [str(v) for v in expected if str(v) not in present]
        intruders = [str(v) for v in forbidden if str(v) in present]

        metrics = {"distinct_present": len(present), "expected": len(expected),
                   "missing": missing, "forbidden_present": intruders}
        if missing or intruders:
            parts = []
            if missing:
                parts.append(f"{len(missing)} expected value(s) missing: {missing}")
            if intruders:
                parts.append(f"{len(intruders)} forbidden value(s) present: {intruders}")
            return self._check(name, table=t.target_table, status=Status.FAIL,
                               severity=Severity.P2, message="; ".join(parts),
                               metrics=metrics)
        return self._check(name, table=t.target_table, status=Status.PASS,
                           message="All expected values present; no forbidden values.",
                           metrics=metrics)
