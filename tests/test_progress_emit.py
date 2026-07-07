"""The runner emits newline-delimited JSON progress on stdout when
ETL_TEST_PROGRESS_JSON=1, so the Next.js app can stream it as SSE. Standalone use
(env var unset) must stay quiet."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "samples" / "demo_suite.yaml"


def _ensure_demo():
    if not (ROOT / "samples" / "demo_mapping.xlsx").exists():
        subprocess.run([sys.executable, str(ROOT / "samples" / "build_demo.py")],
                       check=True, cwd=ROOT)


def _parse_events(stdout: str) -> list[dict]:
    events = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "event" in obj:
            events.append(obj)
    return events


def test_progress_events_emitted(tmp_path):
    _ensure_demo()
    env = {**os.environ, "ETL_TEST_PROGRESS_JSON": "1"}
    proc = subprocess.run(
        [sys.executable, "-m", "etl_test.cli", "run", "--suite", str(SUITE),
         "--output", str(tmp_path)],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    events = _parse_events(proc.stdout)
    kinds = [e["event"] for e in events]

    assert kinds[0] == "run_start"
    assert kinds[-1] == "run_complete"
    assert "category_start" in kinds
    assert "category_complete" in kinds

    complete = events[-1]
    assert complete["result_path"] and Path(complete["result_path"]).exists()
    assert "counts" in complete and complete["counts"]["TOTAL"] > 0

    # Every category that started also completed.
    started = [e["category"] for e in events if e["event"] == "category_start"]
    completed = [e["category"] for e in events if e["event"] == "category_complete"]
    assert set(started).issubset(set(completed))


def test_no_progress_without_env_var(tmp_path):
    _ensure_demo()
    env = {k: v for k, v in os.environ.items() if k != "ETL_TEST_PROGRESS_JSON"}
    proc = subprocess.run(
        [sys.executable, "-m", "etl_test.cli", "run", "--suite", str(SUITE),
         "--output", str(tmp_path)],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    assert _parse_events(proc.stdout) == []
