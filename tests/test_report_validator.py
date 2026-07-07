"""Report validator + report-file loader tests (legacy EXPECTED vs new ACTUAL).

Builds two SQLite databases standing in for the legacy Access ValDB report query
(EXPECTED) and the new Snowflake report query (ACTUAL), then runs the generalized
report validator over a two-tab report: one clean tab and one with a seeded row +
measure mismatch.
"""

import json
import sqlite3
from pathlib import Path

from etl_test.config_loader import Connections
from etl_test.core.runner import run_validation
from etl_test.mapping.models import MappingBook
from etl_test.reporting.reports import flatten_report, load_reports


def _mk(path: Path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE TAB (FUND_CODE TEXT, PERIOD TEXT, NAV REAL, IRR REAL)")
    con.executemany("INSERT INTO TAB VALUES (?,?,?,?)", rows)
    con.commit()
    con.close()


def _connections(tmp_path: Path) -> Connections:
    cfg = tmp_path / "connections.yaml"
    cfg.write_text(
        "connections:\n"
        f"  report_new:\n    type: sqlite\n    path: {tmp_path / 'new.sqlite'}\n"
        f"  report_legacy:\n    type: sqlite\n    path: {tmp_path / 'legacy.sqlite'}\n",
        encoding="utf-8",
    )
    return Connections.from_file(cfg)


def _report_file(tmp_path: Path) -> Path:
    data = {
        "id": "demo_report",
        "name": "Demo Report WB",
        "type": "GVC",
        "actual_connection": "report_new",
        "expected_connection": "report_legacy",
        "tabs": [
            {
                "name": "Clean Tab",
                "key_columns": ["FUND_CODE", "PERIOD"],
                "compare_columns": ["NAV", "IRR"],
                "measures": [{"label": "Total NAV", "column": "NAV", "tolerance": 0.0001}],
                "actual": {"query": "SELECT FUND_CODE, PERIOD, NAV, IRR FROM TAB WHERE PERIOD='2026Q1'"},
                "expected": {"query": "SELECT FUND_CODE, PERIOD, NAV, IRR FROM TAB WHERE PERIOD='2026Q1'"},
            },
            {
                "name": "Broken Tab",
                "key_columns": ["FUND_CODE", "PERIOD"],
                "compare_columns": ["NAV", "IRR"],
                "measures": [{"label": "Total NAV", "column": "NAV", "tolerance": 0.0001}],
                "actual": {"query": "SELECT FUND_CODE, PERIOD, NAV, IRR FROM TAB WHERE PERIOD='2026Q2'"},
                "expected": {"query": "SELECT FUND_CODE, PERIOD, NAV, IRR FROM TAB WHERE PERIOD='2026Q2'"},
            },
        ],
    }
    p = tmp_path / "demo_report.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_flatten_resolves_default_connections(tmp_path):
    data = json.loads(_report_file(tmp_path).read_text(encoding="utf-8"))
    specs = flatten_report(data)
    assert len(specs) == 2
    assert specs[0]["actual"]["connection"] == "report_new"
    assert specs[0]["expected"]["connection"] == "report_legacy"
    assert specs[0]["name"] == "Demo Report WB · Clean Tab"
    assert specs[0]["report_id"] == "demo_report"


def test_report_validator_flags_mismatch(tmp_path):
    # Clean tab (2026Q1) identical on both sides.
    # Broken tab (2026Q2): ACTUAL has a NAV drift + an extra row vs EXPECTED.
    _mk(tmp_path / "legacy.sqlite", [
        ("F1", "2026Q1", 100.0, 0.1),
        ("F2", "2026Q1", 200.0, 0.2),
        ("F1", "2026Q2", 150.0, 0.15),
    ])
    _mk(tmp_path / "new.sqlite", [
        ("F1", "2026Q1", 100.0, 0.1),
        ("F2", "2026Q1", 200.0, 0.2),
        ("F1", "2026Q2", 175.0, 0.15),   # NAV drift 150 -> 175
        ("F9", "2026Q2", 50.0, 0.05),    # extra row not in legacy
    ])
    connections = _connections(tmp_path)
    specs = load_reports([str(_report_file(tmp_path))])

    run, json_path = run_validation(
        connections=connections, mapping=MappingBook(source_file="(reports only)"),
        categories=["report"], target_name="report_new", source_name=None,
        table_names=None, options={"report_specs": specs},
        output_dir=tmp_path / "out", suite_name="report_demo",
    )

    by = {c.name: c for c in run.checks}
    assert not [c for c in run.checks if c.status.value == "ERROR"], \
        [(c.name, c.message) for c in run.checks if c.status.value == "ERROR"]

    # Phase 1 structure: Clean tab lines up exactly (PASS); Broken tab has a
    # row-count delta but identical columns, so WARN (not a hard block).
    assert by["Report structure [Demo Report WB · Clean Tab]"].status.value == "PASS"
    assert by["Report structure [Demo Report WB · Broken Tab]"].status.value == "WARN"

    # Clean tab: row-level + measures both PASS.
    assert by["Report data [Demo Report WB · Clean Tab]"].status.value == "PASS"
    assert by["Report measures [Demo Report WB · Clean Tab]"].status.value == "PASS"
    # Broken tab: structure only WARNed, so Phase 2 still runs -> FAIL.
    assert by["Report data [Demo Report WB · Broken Tab]"].status.value == "FAIL"
    assert by["Report measures [Demo Report WB · Broken Tab]"].status.value == "FAIL"
    assert run.exit_code() == 1

    # No spurious "No tables selected" error for a report-only run.
    assert "No tables selected" not in by
    assert json_path.exists()


def test_structure_gate_skips_data_on_missing_column(tmp_path):
    """A configured compare column missing from a side is a hard structural
    break: Phase 1 FAILs and Phase 2 (data + measures) is gated to SKIPPED."""
    _mk(tmp_path / "legacy.sqlite", [("F1", "2026Q1", 100.0, 0.1)])
    _mk(tmp_path / "new.sqlite", [("F1", "2026Q1", 100.0, 0.1)])
    connections = _connections(tmp_path)

    report = {
        "id": "gate_report", "name": "Gate Report",
        "actual_connection": "report_new", "expected_connection": "report_legacy",
        "tabs": [{
            "name": "Missing Col Tab",
            "key_columns": ["FUND_CODE", "PERIOD"],
            "compare_columns": ["NAV", "IRR"],
            "measures": [{"label": "Total NAV", "column": "NAV", "tolerance": 0.0001}],
            # ACTUAL omits NAV entirely — a structural regression.
            "actual": {"query": "SELECT FUND_CODE, PERIOD, IRR FROM TAB"},
            "expected": {"query": "SELECT FUND_CODE, PERIOD, NAV, IRR FROM TAB"},
        }],
    }
    p = tmp_path / "gate_report.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    specs = load_reports([str(p)])

    run, _ = run_validation(
        connections=connections, mapping=MappingBook(source_file="(reports only)"),
        categories=["report"], target_name="report_new", source_name=None,
        table_names=None, options={"report_specs": specs},
        output_dir=tmp_path / "out", suite_name="gate",
    )
    by = {c.name: c for c in run.checks}
    assert by["Report structure [Gate Report · Missing Col Tab]"].status.value == "FAIL"
    assert by["Report data [Gate Report · Missing Col Tab]"].status.value == "SKIPPED"
    assert by["Report measures [Gate Report · Missing Col Tab]"].status.value == "SKIPPED"
    # A structural FAIL still fails the run overall.
    assert run.exit_code() == 1
