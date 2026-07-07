"""Report validation — legacy (EXPECTED) vs new (ACTUAL), tab by tab.

A report (GVC, MD&A, …) is a set of *tabs*. Each tab is defined by two SQL
queries returning the same shape:

  * **ACTUAL**  — the new Snowflake query (the migrated report layer), and
  * **EXPECTED** — the legacy MS Access ValDB query (the source of truth).

The validator compares the two datasets key-by-key (row-level diff) and, when a
tab declares ``measures``, reconciles aggregate totals within tolerance. This is
a *data-layer* check (the report's underlying dataset); visual/PowerPoint layout
is out of scope.

Tab spec shape (produced by :func:`etl_test.reporting.reports.load_reports`, or
inline in a suite's ``options.report_specs`` / legacy ``options.gvc_reports``)::

  - name: "Q01 - Fund Performance"
    actual:   { connection: snowflake_gold, table|query|path, columns?, where? }
    expected: { connection: access_valdb,   table|query|path, columns?, where? }
    key_columns:     [FUND_CODE, PERIOD]
    compare_columns: [NAV, IRR]          # optional; default = shared non-key cols
    measures:                            # optional aggregate totals to reconcile
      - { label: "Total NAV", column: NAV, tolerance: 0.0001 }

Back-compat: ``report``/``gold`` are accepted as aliases for ``actual``/
``expected`` so pre-existing GVC suites keep working unchanged.
"""

from __future__ import annotations

from ..connectors.base import Dataset
from ..core.comparison import compare, write_evidence
from ..core.normalize import ColumnNormSpec, coerce_numeric
from ..core.result import Category, CheckResult, Evidence, Severity, Status
from .base import Validator, timed_check


class ReportValidator(Validator):
    category = Category.REPORT

    # Options key holding the flattened tab specs. Legacy suites use "gvc_reports".
    specs_key = "report_specs"

    def _specs(self) -> list[dict]:
        return self.ctx.opt(self.specs_key) or self.ctx.opt("gvc_reports") or []

    def validate(self, tables):
        specs = self._specs()
        if not specs:
            return [self._check("Report tabs", status=Status.SKIPPED,
                                message="No report tabs configured "
                                        "(suite 'reports:' or options.report_specs).")]
        results = []
        for spec in specs:
            try:
                results.extend(self._one(spec))
            except Exception as exc:  # noqa: BLE001
                results.append(CheckResult.error(
                    f"Report tab [{_label(spec)}]", self.category.value, str(exc)))
        return results

    # --- side resolution ---------------------------------------------------------
    @staticmethod
    def _side(spec: dict, *keys: str) -> dict:
        """Return the first present side dict among ``keys`` (e.g. actual/report)."""
        for k in keys:
            if spec.get(k):
                return spec[k]
        raise KeyError(
            f"Report tab [{_label(spec)}] is missing a "
            f"{'/'.join(keys)} side definition.")

    def _resolve_ds(self, side: dict) -> tuple[object, Dataset]:
        conn_name = side.get("connection", "target")
        if conn_name == "target":
            conn = self.ctx.target
        elif conn_name == "source":
            if self.ctx.source is None:
                raise ValueError("tab references 'source' but no source is configured.")
            conn = self.ctx.source
        else:
            conn = self.ctx.connector(conn_name)
        ds = Dataset(
            name=side.get("name", conn_name),
            table=side.get("table"),
            query=side.get("query"),
            columns=side.get("columns"),
            where=side.get("where"),
            options={"path": side.get("path")} if side.get("path") else {},
        )
        return conn, ds

    @timed_check
    def _row_level(self, spec, actual_df, expected_df) -> CheckResult:
        name = f"Report data [{_label(spec)}]"
        keys = spec.get("key_columns")
        if not keys:
            return self._check(name, status=Status.SKIPPED,
                               message="No key_columns configured for this tab.")
        compare_cols = spec.get("compare_columns")
        specs_map = {c: ColumnNormSpec(name=c, numeric_tolerance=spec.get("tolerance"))
                     for c in (compare_cols or [])}
        # compare(left=ACTUAL/new, right=EXPECTED/legacy):
        #   source_only = ACTUAL rows absent from EXPECTED (Snowflake extras),
        #   target_only = EXPECTED rows absent from ACTUAL (Snowflake misses).
        res = compare(actual_df, expected_df, keys, compare_cols, specs_map)
        evidence = write_evidence(res, self.ctx.evidence_dir,
                                  f"report_{_slug(_label(spec))}")
        status = Status.PASS if res.is_clean else Status.FAIL
        msg = ("Snowflake report matches the legacy report." if status == Status.PASS
               else f"{res.source_only} Snowflake row(s) not in legacy, "
                    f"{res.target_only} legacy row(s) missing from Snowflake, "
                    f"{res.value_mismatches} value mismatch(es).")
        return self._check(
            name, status=status,
            severity=Severity.coerce(spec.get("severity"), Severity.P2),
            message=msg, metrics=res.summary_metrics(),
            sample=res.sample_mismatches or res.sample_source_only,
            sample_columns=list((res.sample_mismatches or res.sample_source_only or [{}])[0].keys())
            if (res.sample_mismatches or res.sample_source_only) else [],
            evidence=[Evidence(**e) for e in evidence])

    @timed_check
    def _measures(self, spec, actual_df, expected_df) -> CheckResult:
        name = f"Report measures [{_label(spec)}]"
        measures = spec.get("measures") or []
        rows = []
        breaches = 0
        for m in measures:
            col = m.get("column")
            label = m.get("label", col)
            tol = float(m.get("tolerance", spec.get("variance_threshold", 0.0001)))
            a_sum = coerce_numeric(actual_df[col]).sum() \
                if col in actual_df.columns else None
            e_sum = coerce_numeric(expected_df[col]).sum() \
                if col in expected_df.columns else None
            if a_sum is None or e_sum is None:
                rows.append({"measure": label, "column": col, "snowflake": a_sum,
                             "legacy": e_sum, "variance": None, "within": False,
                             "note": "column missing on a side"})
                breaches += 1
                continue
            denom = abs(e_sum) if e_sum else (abs(a_sum) if a_sum else 0.0)
            var = 0.0 if denom == 0 else abs(a_sum - e_sum) / denom
            within = var <= tol
            breaches += 0 if within else 1
            rows.append({"measure": label, "column": col, "snowflake": a_sum,
                         "legacy": e_sum, "variance": var, "within": within})
        status = Status.PASS if breaches == 0 else Status.FAIL
        return self._check(
            name, status=status,
            severity=Severity.coerce(spec.get("severity"), Severity.P2),
            message=(f"All {len(rows)} measure(s) reconcile." if status == Status.PASS
                     else f"{breaches} of {len(rows)} measure(s) breach tolerance."),
            metrics={"measures": len(rows), "breaches": breaches},
            sample=rows, sample_columns=["measure", "column", "snowflake", "legacy",
                                         "variance", "within"])

    @timed_check
    def _structure(self, spec, actual_df, expected_df) -> CheckResult:
        """Phase 1: verify the two report sides line up *structurally* before any
        row-level data comparison — column parity (headers), that the configured
        key/compare columns exist on both sides, and overall row-count parity.

        Returns FAIL only for hard structural breaks (a configured key/compare
        column missing on a side) so Phase 2 can be gated; column drift on
        non-configured columns and a row-count delta are WARN by default (report
        tabs legitimately roll forward late funds). Set ``row_count_gate: fail``
        on the tab to make a count delta a hard block instead."""
        name = f"Report structure [{_label(spec)}]"
        keys = list(spec.get("key_columns") or [])
        compare_cols = list(spec.get("compare_columns") or [])
        required = list(dict.fromkeys(keys + compare_cols))

        a_cols = list(actual_df.columns)
        e_cols = list(expected_df.columns)
        a_map = {c.casefold(): c for c in a_cols}
        e_map = {c.casefold(): c for c in e_cols}

        missing_actual = [c for c in required if c.casefold() not in a_map]
        missing_expected = [c for c in required if c.casefold() not in e_map]
        # Present on both sides but the header case differs (Snowflake upper-cases
        # unquoted identifiers) — a warning because the row-level compare is
        # case-sensitive on column names and could otherwise silently skip it.
        case_mismatch = [c for c in required
                         if c.casefold() in a_map and c.casefold() in e_map
                         and a_map[c.casefold()] != e_map[c.casefold()]]

        only_actual = [c for c in a_cols if c.casefold() not in e_map]
        only_expected = [c for c in e_cols if c.casefold() not in a_map]

        a_rows, e_rows = len(actual_df), len(expected_df)
        row_delta = abs(a_rows - e_rows)
        row_tol = int(spec.get("row_count_tolerance", 0))
        row_gate = str(spec.get("row_count_gate", "warn")).lower()  # warn | fail | off
        row_ok = row_delta <= row_tol

        metrics = {
            "actual_columns": len(a_cols), "expected_columns": len(e_cols),
            "actual_rows": a_rows, "expected_rows": e_rows, "row_delta": row_delta,
            "columns_only_in_snowflake": only_actual,
            "columns_only_in_legacy": only_expected,
        }

        hard, soft = [], []
        if missing_actual:
            hard.append(f"required column(s) missing from Snowflake: {missing_actual}")
        if missing_expected:
            hard.append(f"required column(s) missing from legacy: {missing_expected}")
        if row_gate == "fail" and not row_ok:
            hard.append(f"row count differs: Snowflake {a_rows} vs legacy {e_rows}")
        if case_mismatch:
            soft.append(f"column case differs on {case_mismatch} (may skip value compare)")
        if only_actual:
            soft.append(f"{len(only_actual)} extra column(s) in Snowflake: {only_actual}")
        if only_expected:
            soft.append(f"{len(only_expected)} column(s) only in legacy: {only_expected}")
        if row_gate == "warn" and not row_ok:
            soft.append(f"row count differs: Snowflake {a_rows} vs legacy {e_rows}")

        sev = Severity.coerce(spec.get("severity"), Severity.P2)
        if hard:
            return self._check(name, status=Status.FAIL, severity=sev,
                               message="Structure mismatch — " + "; ".join(hard),
                               metrics=metrics)
        if soft:
            return self._check(name, status=Status.WARN, severity=sev,
                               message="Structure OK with warnings — " + "; ".join(soft),
                               metrics=metrics)
        return self._check(name, status=Status.PASS, severity=sev,
                           message=f"Structure matches: {len(a_cols)} columns, "
                                   f"{a_rows} rows on both sides.",
                           metrics=metrics)

    def _gated(self, spec, base_name: str) -> CheckResult:
        return self._check(base_name, status=Status.SKIPPED,
                           severity=Severity.coerce(spec.get("severity"), Severity.P2),
                           message="Skipped — Phase 1 structure check failed; "
                                   "fix the report structure before data validation.")

    def _one(self, spec) -> list[CheckResult]:
        actual_conn, actual_ds = self._resolve_ds(self._side(spec, "actual", "report"))
        expected_conn, expected_ds = self._resolve_ds(self._side(spec, "expected", "gold"))
        actual_df = actual_conn.fetch_dataframe(actual_ds)
        expected_df = expected_conn.fetch_dataframe(expected_ds)

        out: list[CheckResult] = []
        gate_on = spec.get("gate_on_structure", True)
        structure = None
        if spec.get("structure_check", True):
            structure = self._structure(spec, actual_df, expected_df)
            out.append(structure)

        # Phase 2 (data) — gated by Phase 1 when structure hard-FAILs.
        gated = bool(gate_on and structure is not None and structure.status == Status.FAIL)
        if gated:
            out.append(self._gated(spec, f"Report data [{_label(spec)}]"))
            if spec.get("measures"):
                out.append(self._gated(spec, f"Report measures [{_label(spec)}]"))
        else:
            out.append(self._row_level(spec, actual_df, expected_df))
            if spec.get("measures"):
                out.append(self._measures(spec, actual_df, expected_df))
        return out


class GvcReportValidator(ReportValidator):
    """Legacy alias: registered under the ``gvc_report`` category for old suites
    that still set ``options.gvc_reports`` and list ``gvc_report`` in ``tests``."""
    category = Category.GVC_REPORT
    specs_key = "gvc_reports"


def _label(spec: dict) -> str:
    return str(spec.get("name", "?"))


def _slug(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(s))[:50]
