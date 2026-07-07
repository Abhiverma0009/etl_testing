"""Regression test: an explicit per-table `lineage_columns: []` must opt that
table OUT of the lineage check (SKIPPED), not silently fall back to the
suite-level default. `[] or default` in Python treats an empty list the same as
"unset", which previously made this override a no-op — caught while testing the
demo suite against a real Snowflake target."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_empty_lineage_columns_opts_table_out(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "samples" / "build_demo.py")],
                   check=True, cwd=ROOT)
    from etl_test.config_loader import Connections
    from etl_test.mapping import load_mapping
    from etl_test.core.runner import run_validation

    connections = Connections.from_file(ROOT / "samples" / "demo_connections.yaml")
    mapping = load_mapping(ROOT / "samples" / "demo_mapping.xlsx")
    # FUND opts out via an empty list; DEAL_FUND_VALUED_ASSET uses the suite default.
    mapping.table("FUND").options.update({"lineage_columns": []})

    run, _ = run_validation(
        connections=connections, mapping=mapping, categories=["lineage"],
        target_name="demo_target", source_name="demo_source", table_names=None,
        options={"lineage_columns": ["SOURCE_SYSTEM", "LOAD_TIMESTAMP"]},
        output_dir=tmp_path, suite_name="lineage_opt_out_test",
    )

    by_name = {c.name: c for c in run.checks}
    assert by_name["Lineage [FUND]"].status.value == "SKIPPED"
    assert by_name["Lineage [DEAL_FUND_VALUED_ASSET]"].status.value == "PASS"
