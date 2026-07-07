"""Business rule validation.

Generic rule primitives that the project's specific migration rules map onto.
Rules come from the BusinessRules sheet of the mapping workbook (see
``mapping/excel_parser.py``). Each rule runs against the **target** table (the
post-load result), optionally restricted by a pandas ``filter`` expression.

Supported rule_type values
--------------------------
value_equals     params: column, expected            -> all (filtered) rows have column == expected
allowed_values   params: column, allowed_values      -> all values within the allowed set
not_allowed      params: column, allowed_values      -> none of the values appear
conditional      params: when, column, expected      -> rows matching `when` have column == expected
                 (alias: flag_override)
not_null         params: column                      -> column is non-null for (filtered) rows
range            params: column, min, max            -> numeric column within [min, max]
unique           params: columns                     -> column combination is unique
must_exist       params: (filter), min_count=1       -> at least min_count rows match
must_not_exist   params: (filter)                    -> zero rows match (e.g. excluded records)
combine          params: group_by, expect_count=1    -> each group collapses to expect_count rows
split            params: group_by, type_column,      -> each group splits into the expected
                         expect_distinct OR min_count    number of line items
valid_expr       params: valid_expr                  -> rows failing the pandas boolean expr are offenders

Each rule's severity comes from the sheet (P1..P4).
"""

from __future__ import annotations

import pandas as pd

from ..core.normalize import is_nullish
from ..core.result import Category, CheckResult, Evidence, Severity, Status
from ..mapping.models import BusinessRule, TableMapping
from .base import Validator, timed_check


def _norm_eq(series: pd.Series, expected) -> pd.Series:
    """Vectorised equality tolerant of numeric/text and case/whitespace."""
    exp_str = str(expected).strip().casefold()
    s_str = series.astype(str).str.strip().str.casefold()
    eq = s_str == exp_str
    # numeric fallback
    try:
        exp_num = float(expected)
        s_num = pd.to_numeric(series, errors="coerce")
        eq = eq | (s_num == exp_num)
    except (TypeError, ValueError):
        pass
    return eq.fillna(False)


class BusinessRulesValidator(Validator):
    category = Category.BUSINESS_RULES

    def validate(self, tables):
        results = []
        table_names = {t.target_table for t in tables}
        rules = [r for r in self.ctx.mapping.business_rules
                 if r.active and r.target_table in table_names]
        if not rules:
            results.append(self._check(
                "Business rules", status=Status.SKIPPED,
                message="No active business rules defined for the selected tables."))
            return results

        # Cache target frames per table.
        cache: dict[str, pd.DataFrame] = {}
        tmap = {t.target_table: t for t in tables}
        for rule in rules:
            t = tmap[rule.target_table]
            try:
                if rule.target_table not in cache:
                    cache[rule.target_table] = self.load_target(t)
                results.append(self._apply(rule, t, cache[rule.target_table]))
            except Exception as exc:  # noqa: BLE001
                results.append(CheckResult.error(
                    f"Rule {rule.rule_id}", self.category.value,
                    f"Rule execution failed: {exc}", target_table=rule.target_table,
                    rule_id=rule.rule_id, use_case=rule.use_case))
        return results

    @timed_check
    def _apply(self, rule: BusinessRule, t: TableMapping, df: pd.DataFrame) -> CheckResult:
        sev = Severity.coerce(rule.severity)
        scope = df
        if rule.filter:
            try:
                scope = df.query(rule.filter)
            except Exception as exc:  # noqa: BLE001
                return self._fail_rule(rule, sev, Status.ERROR,
                                       f"Invalid filter {rule.filter!r}: {exc}")

        handler = getattr(self, f"_rt_{rule.rule_type}", None)
        if handler is None:
            return self._fail_rule(rule, sev, Status.ERROR,
                                   f"Unknown rule_type {rule.rule_type!r}.")
        return handler(rule, t, df, scope, sev)

    # --- rule handlers -----------------------------------------------------------
    def _rt_value_equals(self, rule, t, df, scope, sev):
        col = rule.params.get("column")
        expected = rule.params.get("expected", rule.params.get("value"))
        self._need(col, "column"); self._need_col(scope, col)
        bad = scope[~_norm_eq(scope[col], expected)]
        return self._result(rule, sev, scope, bad,
                            f"{col} must equal {expected!r}", offenders_cols=[col])

    def _rt_allowed_values(self, rule, t, df, scope, sev):
        col = rule.params.get("column")
        allowed = [str(a).strip().casefold() for a in rule.params.get("allowed_values", [])]
        self._need(col, "column"); self._need_col(scope, col)
        bad = scope[~scope[col].astype(str).str.strip().str.casefold().isin(allowed)]
        return self._result(rule, sev, scope, bad,
                            f"{col} must be one of {rule.params.get('allowed_values')}",
                            offenders_cols=[col])

    def _rt_not_allowed(self, rule, t, df, scope, sev):
        col = rule.params.get("column")
        banned = [str(a).strip().casefold() for a in rule.params.get("allowed_values", [])]
        self._need(col, "column"); self._need_col(scope, col)
        bad = scope[scope[col].astype(str).str.strip().str.casefold().isin(banned)]
        return self._result(rule, sev, scope, bad,
                            f"{col} must NOT be any of {rule.params.get('allowed_values')}",
                            offenders_cols=[col])

    def _rt_conditional(self, rule, t, df, scope, sev):
        when = rule.params.get("when")
        col = rule.params.get("column")
        expected = rule.params.get("expected", rule.params.get("value"))
        self._need(col, "column"); self._need(when, "when")
        try:
            subset = scope.query(when)
        except Exception as exc:  # noqa: BLE001
            return self._fail_rule(rule, sev, Status.ERROR, f"Invalid 'when' {when!r}: {exc}")
        self._need_col(subset, col)
        bad = subset[~_norm_eq(subset[col], expected)]
        return self._result(rule, sev, subset, bad,
                            f"When {when}: {col} must equal {expected!r}",
                            offenders_cols=[col])

    _rt_flag_override = _rt_conditional  # semantic alias

    def _rt_not_null(self, rule, t, df, scope, sev):
        col = rule.params.get("column")
        self._need(col, "column"); self._need_col(scope, col)
        bad = scope[scope[col].map(is_nullish)]
        return self._result(rule, sev, scope, bad, f"{col} must not be null",
                            offenders_cols=[col])

    def _rt_range(self, rule, t, df, scope, sev):
        col = rule.params.get("column")
        self._need(col, "column"); self._need_col(scope, col)
        lo = rule.params.get("min")
        hi = rule.params.get("max")
        nums = pd.to_numeric(scope[col], errors="coerce")
        mask = pd.Series(True, index=scope.index)
        if lo is not None:
            mask &= nums >= float(lo)
        if hi is not None:
            mask &= nums <= float(hi)
        bad = scope[~mask.fillna(False)]
        return self._result(rule, sev, scope, bad,
                            f"{col} must be within [{lo}, {hi}]", offenders_cols=[col])

    def _rt_unique(self, rule, t, df, scope, sev):
        cols = rule.params.get("columns") or [rule.params.get("column")]
        cols = [c for c in cols if c]
        for c in cols:
            self._need_col(scope, c)
        dup = scope[scope.duplicated(subset=cols, keep=False)].sort_values(cols)
        return self._result(rule, sev, scope, dup,
                            f"{cols} must be unique", offenders_cols=cols)

    def _rt_must_exist(self, rule, t, df, scope, sev):
        min_count = int(rule.params.get("min_count", 1))
        n = len(scope)
        status = Status.PASS if n >= min_count else Status.FAIL
        msg = (f"{n} row(s) match (>= {min_count} required)." if status == Status.PASS
               else f"Only {n} row(s) match; expected at least {min_count}.")
        return self._mk(rule, sev, status, msg, {"matched_rows": n, "min_count": min_count})

    def _rt_must_not_exist(self, rule, t, df, scope, sev):
        n = len(scope)
        status = Status.PASS if n == 0 else Status.FAIL
        msg = ("No matching rows (as required)." if status == Status.PASS
               else f"{n} row(s) match but should not exist.")
        chk = self._mk(rule, sev, status, msg, {"offending_rows": n})
        if n:
            self._attach_sample(chk, rule, scope)
        return chk

    def _rt_combine(self, rule, t, df, scope, sev):
        group_by = rule.params.get("group_by")
        expect = int(rule.params.get("expect_count", 1))
        gb = [group_by] if isinstance(group_by, str) else list(group_by or [])
        self._need(gb, "group_by")
        for c in gb:
            self._need_col(scope, c)
        sizes = scope.groupby(gb, dropna=False).size()
        bad_groups = sizes[sizes != expect]
        if bad_groups.empty:
            return self._mk(rule, sev, Status.PASS,
                            f"All {len(sizes)} group(s) collapse to {expect} row(s).",
                            {"groups": int(len(sizes))})
        offenders = bad_groups.reset_index(name="row_count")
        chk = self._mk(rule, sev, Status.FAIL,
                       f"{len(bad_groups)} group(s) do not collapse to {expect} row(s).",
                       {"groups": int(len(sizes)), "bad_groups": int(len(bad_groups))})
        self._attach_df(chk, rule, offenders)
        return chk

    def _rt_split(self, rule, t, df, scope, sev):
        group_by = rule.params.get("group_by")
        type_col = rule.params.get("type_column")
        gb = [group_by] if isinstance(group_by, str) else list(group_by or [])
        self._need(gb, "group_by")
        for c in gb:
            self._need_col(scope, c)
        if type_col:
            self._need_col(scope, type_col)
            distinct = scope.groupby(gb, dropna=False)[type_col].nunique()
            expect = int(rule.params.get("expect_distinct", 2))
            bad = distinct[distinct < expect]
            metric_name = f"distinct {type_col}"
        else:
            counts = scope.groupby(gb, dropna=False).size()
            expect = int(rule.params.get("min_count", 2))
            bad = counts[counts < expect]
            metric_name = "row count"
        if bad.empty:
            return self._mk(rule, sev, Status.PASS,
                            f"All groups split into >= {expect} ({metric_name}).",
                            {"groups": int(len(bad.index) + len(bad))})
        offenders = bad.reset_index(name=metric_name.replace(" ", "_"))
        chk = self._mk(rule, sev, Status.FAIL,
                       f"{len(bad)} group(s) not split into >= {expect} ({metric_name}).",
                       {"bad_groups": int(len(bad))})
        self._attach_df(chk, rule, offenders)
        return chk

    def _rt_valid_expr(self, rule, t, df, scope, sev):
        expr = rule.params.get("valid_expr")
        self._need(expr, "valid_expr")
        try:
            valid = scope.query(expr)
        except Exception as exc:  # noqa: BLE001
            return self._fail_rule(rule, sev, Status.ERROR, f"Invalid valid_expr: {exc}")
        bad = scope.drop(valid.index)
        return self._result(rule, sev, scope, bad, f"Rows must satisfy: {expr}")

    # --- shared result builders --------------------------------------------------
    def _result(self, rule, sev, scope, bad, condition, offenders_cols=None):
        total = len(scope)
        n_bad = len(bad)
        if n_bad == 0:
            return self._mk(rule, sev, Status.PASS,
                            f"{condition} — all {total} row(s) comply.",
                            {"checked_rows": total, "violations": 0})
        chk = self._mk(rule, sev, Status.FAIL,
                       f"{condition} — {n_bad} of {total} row(s) violate.",
                       {"checked_rows": total, "violations": n_bad})
        keys = self.ctx.mapping.table(rule.target_table)
        key_cols = keys.key_columns if keys else []
        show_cols = list(dict.fromkeys((key_cols or []) + (offenders_cols or [])))
        show = bad[show_cols] if show_cols and set(show_cols).issubset(bad.columns) else bad
        self._attach_df(chk, rule, show)
        return chk

    def _mk(self, rule, sev, status, msg, metrics) -> CheckResult:
        return self._check(
            f"[{rule.rule_id}] {rule.description or rule.rule_type}",
            table=rule.target_table, status=status, severity=sev, message=msg,
            metrics=metrics, rule_id=rule.rule_id, use_case=rule.use_case)

    def _attach_df(self, chk: CheckResult, rule, df: pd.DataFrame):
        path = self.ctx.evidence_dir / f"rule_{rule.rule_id}.csv"
        df.to_csv(path, index=False)
        chk.sample = df.head(100).to_dict("records")
        chk.sample_columns = list(df.columns)
        chk.evidence = [Evidence(f"Rule {rule.rule_id} offenders", str(path), len(df))]

    def _attach_sample(self, chk, rule, df):
        self._attach_df(chk, rule, df)

    def _fail_rule(self, rule, sev, status, msg) -> CheckResult:
        return self._mk(rule, sev, status, msg, {})

    # --- guards ------------------------------------------------------------------
    @staticmethod
    def _need(value, label):
        if not value:
            raise ValueError(f"rule param {label!r} is required")

    @staticmethod
    def _need_col(df, col):
        if col not in df.columns:
            raise ValueError(f"column {col!r} not present (have: {list(df.columns)})")
