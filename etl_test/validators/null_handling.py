"""Null / default / zero handling validation.

Verifies the semantically important distinction the strategy calls out: a null is
not a zero and not a default. Two checks per table:

  1. Unexpected defaulting: columns declared nullable that are *never* null but
     contain a suspicious constant (the declared ``default_value``) for a large
     share of rows -> WARN (possible silent defaulting of true nulls).
  2. Zero-vs-null on numeric columns flagged ``null_not_zero: true`` in the table
     options: such columns must not contain literal 0 where the source was null.
     Without a source we at least report the count of zeros vs nulls for review.
"""

from __future__ import annotations

import pandas as pd

from ..core.normalize import coerce_numeric, is_nullish
from ..core.result import Category, CheckResult, Evidence, Severity, Status
from .base import Validator, timed_check


class NullHandlingValidator(Validator):
    category = Category.NULL_HANDLING

    def validate(self, tables):
        results = []
        for t in tables:
            results.append(self._defaulting(t))
            zero_cols = t.options.get("null_not_zero") or []
            if isinstance(zero_cols, str):
                zero_cols = [zero_cols]
            if zero_cols:
                results.append(self._zero_vs_null(t, zero_cols))
        return results

    @timed_check
    def _defaulting(self, t) -> CheckResult:
        name = f"Default/null handling [{t.target_table}]"
        cols_with_default = [c for c in t.columns if c.default_value not in (None, "")]
        if not cols_with_default:
            return self._check(name, table=t.target_table, status=Status.SKIPPED,
                               message="No columns with a declared default_value.")
        df = self.load_target(t, columns=[c.target_column for c in cols_with_default])
        flagged = {}
        for c in cols_with_default:
            if c.target_column not in df.columns:
                continue
            series = df[c.target_column]
            n = len(series)
            if n == 0:
                continue
            default_share = (series.astype(str).str.strip()
                             == str(c.default_value).strip()).mean()
            null_share = series.map(is_nullish).mean()
            # Heuristic: lots of the literal default AND no nulls => suspicious.
            if default_share >= 0.5 and null_share == 0:
                flagged[c.target_column] = {
                    "default_value": c.default_value,
                    "default_share": round(float(default_share), 4),
                }
        if not flagged:
            return self._check(name, table=t.target_table, status=Status.PASS,
                               message="No suspicious wholesale defaulting detected.")
        return self._check(
            name, table=t.target_table, status=Status.WARN, severity=Severity.P3,
            message=f"{len(flagged)} column(s) are dominated by their default value "
                    f"with zero nulls — verify true nulls were not silently defaulted.",
            metrics={"flagged": flagged})

    @timed_check
    def _zero_vs_null(self, t, zero_cols) -> CheckResult:
        name = f"Zero-vs-null [{t.target_table}]"
        # Include key columns so the source-vs-target join below can run.
        load_cols = list(dict.fromkeys((t.key_columns or []) + list(zero_cols)))
        df = self.load_target(t, columns=load_cols)
        src = self.load_source(t, columns=load_cols)
        rows = []
        offenders_total = 0
        offender_frames = []
        for col in zero_cols:
            if col not in df.columns:
                continue
            t_num = coerce_numeric(df[col])
            zeros = int((t_num == 0).sum())
            nulls = int(df[col].map(is_nullish).sum())
            entry = {"column": col, "target_zeros": zeros, "target_nulls": nulls}
            if src is not None and col in src.columns and t.key_columns and \
                    all(k in df.columns and k in src.columns for k in t.key_columns):
                # Find keys where source is null but target is 0 -> defaulting bug.
                s_null = src[src[col].map(is_nullish)][t.key_columns].astype(str)
                merged = df.merge(s_null.assign(__src_null=1), on=t.key_columns, how="left")
                bug = merged[(merged["__src_null"] == 1)
                             & (coerce_numeric(merged[col]) == 0)]
                entry["null_source_zero_target"] = int(len(bug))
                offenders_total += len(bug)
                if len(bug):
                    offender_frames.append(bug[t.key_columns + [col]].assign(column=col))
            rows.append(entry)
        if not rows:
            return self._check(name, table=t.target_table, status=Status.SKIPPED,
                               message="Declared null_not_zero columns not found in target.")
        if src is None:
            return self._check(
                name, table=t.target_table, status=Status.WARN, severity=Severity.P4,
                message="No source to confirm; reporting zero/null counts for review.",
                metrics={"columns": rows})
        status = Status.PASS if offenders_total == 0 else Status.FAIL
        msg = ("No source-null became target-zero." if status == Status.PASS
               else f"{offenders_total} row(s) where source was null but target is 0.")
        evidence = []
        if offender_frames:
            allbug = pd.concat(offender_frames, ignore_index=True)
            path = self.ctx.evidence_dir / f"zero_vs_null_{t.target_table}.csv"
            allbug.to_csv(path, index=False)
            evidence = [Evidence("Null-source / zero-target rows", str(path), len(allbug))]
        return self._check(name, table=t.target_table, status=status, severity=Severity.P2,
                           message=msg, metrics={"columns": rows, "offenders": offenders_total},
                           evidence=evidence)
