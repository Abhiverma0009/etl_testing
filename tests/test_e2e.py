"""Offline end-to-end test: build the demo SQLite source/target + mapping, run the
full suite through the runner, and assert the seeded defects are caught and the
run manifest is produced."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _build_demo():
    subprocess.run([sys.executable, str(ROOT / "samples" / "build_demo.py")],
                   check=True, cwd=ROOT)


def test_full_suite_e2e(tmp_path):
    _build_demo()
    from etl_test.config_loader import Connections
    from etl_test.mapping import load_mapping
    from etl_test.core.runner import run_validation
    from etl_test.validators import all_categories

    connections = Connections.from_file(ROOT / "samples" / "demo_connections.yaml")
    mapping = load_mapping(ROOT / "samples" / "demo_mapping.xlsx")

    # Mirror the per-table options from the demo suite.
    deal = mapping.table("DEAL_FUND_VALUED_ASSET")
    deal.options.update({"group_by": ["FUND_CODE"], "null_not_zero": ["FMV"],
                         "completeness": [{"column": "PERIOD",
                                           "expected_values": ["2026Q1"]}]})
    mapping.table("FUND").options.update({"lineage_columns": []})

    run, json_path = run_validation(
        connections=connections, mapping=mapping,
        categories=all_categories(),
        target_name="demo_target", source_name="demo_source",
        table_names=None,
        options={"variance_threshold": 0.0001,
                 "lineage_columns": ["SOURCE_SYSTEM", "LOAD_TIMESTAMP"]},
        output_dir=tmp_path, suite_name="e2e",
    )

    import json as _json
    assert json_path.exists()
    # New layout: manifest.json index + runs/<id>/result.json (no HTML dashboard).
    assert not (tmp_path / "dashboard.html").exists()
    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    ids = [r["run_id"] for r in manifest["runs"]]
    assert run.run_id in ids
    entry = next(r for r in manifest["runs"] if r["run_id"] == run.run_id)
    assert (tmp_path / entry["path"]).exists()          # runs/<id>/result.json
    assert entry["path"].startswith("runs/")
    # Evidence paths in the saved JSON must be relative (portable links).
    saved = _json.loads(json_path.read_text(encoding="utf-8"))
    for chk in saved["checks"]:
        for ev in chk.get("evidence", []):
            assert not ev["path"].startswith(("/", "\\")) and ":" not in ev["path"][:3]

    # No validator should have crashed.
    errors = [c for c in run.checks if c.status.value == "ERROR"]
    assert not errors, f"unexpected ERRORs: {[(c.name, c.message) for c in errors]}"

    by_name = {c.name: c for c in run.checks}

    def status(substr):
        for n, c in by_name.items():
            if substr in n:
                return c.status.value
        raise AssertionError(f"no check matching {substr!r}")

    # Seeded defects must be caught.
    assert status("BR001") == "FAIL"          # adjustment code != 27
    assert status("BR002") == "FAIL"          # public/private flag flipped
    assert status("BR003") == "FAIL"          # Nouryon must not exist
    assert status("Zero-vs-null") == "FAIL"   # null source -> zero target
    assert status("Reconciliation [DEAL") == "FAIL"

    # Clean things must pass.
    assert status("Aggregate variance [DEAL") == "PASS"
    assert status("Reconciliation [FUND") == "PASS"
    assert status("Deduplication [DEAL") == "PASS"
    assert run.exit_code() == 1               # FAIL present, no ERROR
