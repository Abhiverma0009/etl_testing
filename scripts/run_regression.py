"""Regression batch runner — runs every suite and writes a combined report.

Designed to be invoked by Windows Task Scheduler (nightly or weekly) via the
venv's python.exe directly, e.g.::

    .venv\\Scripts\\python.exe scripts\\run_regression.py

Each suite is executed headlessly through the same CLI a manual run uses
(``etl_test.cli run``). Runs are written under ``<output-root>/regression/`` so
they appear in the app's team run history as a member named **regression**
(each with its own downloadable PDF), exactly like manual runs. After the batch
finishes, a single self-contained HTML summary is written to
``output/_regression_reports/regression_<timestamp>.html`` for quick evidence /
sign-off without opening the app.

Unlike ``scheduled_report_run.py`` (which self-guards to a quarter-end date),
this runner has **no date gate** — the schedule is owned entirely by Task
Scheduler, so ``/SC DAILY`` gives nightly regression and ``/SC WEEKLY`` weekly.

Examples
--------
  # run the whole regression batch now (what Task Scheduler invokes):
  .venv\\Scripts\\python.exe scripts\\run_regression.py

  # only specific suites:
  .venv\\Scripts\\python.exe scripts\\run_regression.py --suite config/suites/bronze_to_silver.yaml

  # all suites except the report stubs that still need real SQL:
  .venv\\Scripts\\python.exe scripts\\run_regression.py --exclude gvc --exclude mda
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
SUITES_DIR = ROOT / "config" / "suites"
SCENARIOS_PATH = ROOT / "config" / "scenarios.yaml"

# The "Results:   <path>" line the CLI prints on a successful run.
_RESULT_LINE = re.compile(r"^Results:\s+(.+result\.json)\s*$", re.MULTILINE)


def _load_yaml(path: Path) -> dict:
    import yaml  # provided by the engine's deps; only needed for --scenario
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def read_scenarios() -> dict:
    """Map scenario id -> display name from config/scenarios.yaml."""
    try:
        data = _load_yaml(SCENARIOS_PATH)
    except FileNotFoundError:
        return {}
    return {sid: (meta or {}).get("name", sid)
            for sid, meta in (data.get("scenarios") or {}).items()}


def resolve_scenario(value: str, scenarios: dict) -> str:
    """Accept a scenario id OR its display name (case-insensitive) and return
    the id. Falls back to the raw value so an id not listed in scenarios.yaml
    still works."""
    v = value.strip().lower()
    for sid, name in scenarios.items():
        if v == sid.lower() or v == str(name).lower():
            return sid
    return value


def suite_scenario(path: Path) -> str | None:
    """The `scenario:` id a suite YAML is tagged with (None if untagged)."""
    try:
        data = _load_yaml(path)
    except Exception:
        return None
    s = data.get("scenario")
    return str(s) if s else None


def discover_suites(explicit: list[str], exclude: list[str],
                    scenario: str | None) -> list[Path]:
    """The suite files to run: explicit --suite list if given, else every suite
    tagged with ``scenario`` if given, else every config/suites/*.yaml — minus
    any whose stem is in ``exclude``."""
    if explicit:
        suites = [Path(s) for s in explicit]
    elif scenario:
        sid = resolve_scenario(scenario, read_scenarios())
        suites = sorted(s for s in SUITES_DIR.glob("*.yaml")
                        if suite_scenario(s) == sid)
    else:
        suites = sorted(SUITES_DIR.glob("*.yaml"))
    excluded = {e.lower() for e in exclude}
    return [s for s in suites if s.stem.lower() not in excluded]


def run_one(suite: Path, out_dir: Path, log_dir: Path, stamp: str) -> dict:
    """Run a single suite via the CLI, capturing its output to a log file.
    Returns a summary dict (suite, exit code, result.json path if found)."""
    log_path = log_dir / f"{stamp}_{suite.stem}.log"
    proc = subprocess.run(
        [str(PYTHON), "-m", "etl_test.cli", "run",
         "--suite", str(suite), "--output", str(out_dir)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    log_path.write_text(output, encoding="utf-8")
    m = _RESULT_LINE.search(output)
    return {
        "suite": suite.stem,
        "suite_path": str(suite),
        "exit_code": proc.returncode,
        "result_json": m.group(1).strip() if m else None,
        "log": log_path.name,
    }


def load_counts(result_json: str | None) -> dict:
    """Read PASS/WARN/FAIL/ERROR/SKIPPED counts + passed flag from a run's
    result.json. Returns an all-zero, errored=True shape if unreadable."""
    if not result_json:
        return {"passed": None, "counts": {}, "readable": False}
    try:
        import json
        data = json.loads(Path(result_json).read_text(encoding="utf-8"))
        return {"passed": data.get("passed"),
                "counts": data.get("counts", {}),
                "run_id": data.get("run_id"),
                "readable": True}
    except Exception:
        return {"passed": None, "counts": {}, "readable": False}


def write_html_summary(path: Path, rows: list[dict], stamp: str, member: str,
                       scenario_label: str | None = None) -> None:
    """Self-contained (no external assets) HTML overview of the batch —
    openable in any browser and printable to PDF for evidence."""
    def cell(v) -> str:
        return html.escape(str(v if v is not None else "—"))

    total = {k: 0 for k in ("PASS", "WARN", "FAIL", "ERROR", "SKIPPED", "TOTAL")}
    body_rows = []
    for r in rows:
        c = r["counts"]
        for k in total:
            total[k] += int(c.get(k, 0) or 0)
        if r["passed"] is True:
            verdict, color = "PASS", "#087443"
        elif r["passed"] is False:
            verdict, color = "FAIL", "#b42318"
        else:
            verdict, color = "ERROR", "#5925dc"
        body_rows.append(
            f"<tr>"
            f"<td class='suite'>{cell(r['suite'])}</td>"
            f"<td><span class='pill' style='background:{color}'>{verdict}</span></td>"
            f"<td class='num'>{cell(c.get('PASS', 0))}</td>"
            f"<td class='num'>{cell(c.get('WARN', 0))}</td>"
            f"<td class='num'>{cell(c.get('FAIL', 0))}</td>"
            f"<td class='num'>{cell(c.get('ERROR', 0))}</td>"
            f"<td class='num'>{cell(c.get('SKIPPED', 0))}</td>"
            f"<td class='num'>{cell(c.get('TOTAL', 0))}</td>"
            f"</tr>"
        )

    suites_run = len(rows)
    suites_failed = sum(1 for r in rows if r["passed"] is not True)
    overall = "PASS" if suites_failed == 0 else "FAIL"
    overall_color = "#087443" if suites_failed == 0 else "#b42318"

    doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Regression batch {html.escape(stamp)}</title>
<style>
  body {{ font-family: Segoe UI, Arial, sans-serif; color:#101828; margin:32px; font-size:13px; }}
  h1 {{ font-size:20px; margin:0 0 2px; }}
  .sub {{ color:#475467; margin-bottom:18px; }}
  .banner {{ display:inline-block; padding:6px 14px; border-radius:6px; color:#fff;
             font-weight:700; background:{overall_color}; margin-bottom:16px; }}
  table {{ border-collapse:collapse; width:100%; }}
  th, td {{ border:1px solid #e4e7ec; padding:7px 10px; text-align:left; }}
  th {{ background:#f7f8fa; font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:#667085; }}
  td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td.suite {{ font-weight:600; }}
  .pill {{ display:inline-block; padding:2px 8px; border-radius:4px; color:#fff; font-size:11px; font-weight:700; }}
  tfoot td {{ font-weight:700; background:#f7f8fa; }}
  .note {{ color:#667085; margin-top:16px; font-size:12px; }}
</style></head><body>
<h1>ETL Regression Batch Report</h1>
<div class="sub">Generated {html.escape(dt.datetime.now().strftime('%Y-%m-%d %H:%M'))} ·
  {('scenario: ' + html.escape(scenario_label) + ' · ') if scenario_label else ''}{suites_run} suite(s) · {suites_failed} not passing</div>
<div class="banner">{overall}</div>
<table>
  <thead><tr>
    <th>Suite (test case)</th><th>Result</th>
    <th class="num">Pass</th><th class="num">Warn</th><th class="num">Fail</th>
    <th class="num">Error</th><th class="num">Skipped</th><th class="num">Total</th>
  </tr></thead>
  <tbody>
    {''.join(body_rows)}
  </tbody>
  <tfoot><tr>
    <td>Total</td><td></td>
    <td class="num">{total['PASS']}</td><td class="num">{total['WARN']}</td>
    <td class="num">{total['FAIL']}</td><td class="num">{total['ERROR']}</td>
    <td class="num">{total['SKIPPED']}</td><td class="num">{total['TOTAL']}</td>
  </tr></tfoot>
</table>
<div class="note">Per-suite detail and a downloadable PDF for each run are in the app under
  <b>Runs → member &ldquo;{html.escape(member)}&rdquo;</b>. To save this overview as PDF: open in a
  browser and Print &rarr; Save as PDF.</div>
</body></html>"""
    path.write_text(doc, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run all suites as a regression batch.")
    ap.add_argument("--suite", action="append", default=[],
                    help="Suite path (repeatable). Default: every config/suites/*.yaml.")
    ap.add_argument("--scenario", default=None,
                    help="Run only suites tagged with this scenario (id or display "
                         "name from config/scenarios.yaml). Ignored if --suite is given.")
    ap.add_argument("--exclude", action="append", default=[],
                    help="Suite stem to skip (repeatable), e.g. --exclude gvc.")
    ap.add_argument("--member", default="regression",
                    help="Team-member folder runs are written under (default 'regression').")
    ap.add_argument("--output-root", default=None,
                    help="Base output dir (default: $TEAM_RUNS_ROOT or ./output).")
    args = ap.parse_args()

    if not PYTHON.exists():
        print(f"ERROR: venv python not found at {PYTHON}", file=sys.stderr)
        return 3

    suites = discover_suites(args.suite, args.exclude, args.scenario)
    scenario_label = None
    if args.scenario and not args.suite:
        scenarios = read_scenarios()
        sid = resolve_scenario(args.scenario, scenarios)
        scenario_label = scenarios.get(sid, sid)
        if not suites:
            available = ", ".join(f"{name} ({sid})" for sid, name in scenarios.items()) or "(none)"
            print(f"No suites tagged with scenario '{args.scenario}'. "
                  f"Available scenarios: {available}", file=sys.stderr)
            return 2
    if not suites:
        print("No suites to run.", file=sys.stderr)
        return 2

    output_root = Path(args.output_root or os.environ.get("TEAM_RUNS_ROOT")
                       or (ROOT / "output"))
    out_dir = output_root / args.member
    log_dir = ROOT / "output" / "_regression_logs"
    report_dir = ROOT / "output" / "_regression_reports"
    log_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    scope = f"scenario '{scenario_label}'" if scenario_label else "all suites"
    print(f"Regression batch {stamp} - {scope}, {len(suites)} suite(s) -> {out_dir}")

    rows: list[dict] = []
    for suite in suites:
        res = run_one(suite, out_dir, log_dir, stamp)
        res.update(load_counts(res["result_json"]))
        c = res["counts"]
        verdict = "PASS" if res["passed"] is True else ("FAIL" if res["passed"] is False else "ERROR")
        print(f"  {suite.stem:<28} {verdict:<5} "
              f"(P{c.get('PASS', 0)}/W{c.get('WARN', 0)}/F{c.get('FAIL', 0)}/"
              f"E{c.get('ERROR', 0)}/S{c.get('SKIPPED', 0)})  log={res['log']}")
        rows.append(res)

    report_path = report_dir / f"regression_{stamp}.html"
    write_html_summary(report_path, rows, stamp, args.member, scenario_label)

    failed = sum(1 for r in rows if r["passed"] is not True)
    (report_dir / "last_run.txt").write_text(
        f"{stamp}: {len(rows)} suite(s), {failed} not passing. Report: {report_path.name}\n",
        encoding="utf-8")
    print(f"\nBatch report: {report_path}")
    print(f"Open the app (Runs -> member '{args.member}') for per-suite detail and PDFs.")

    # Exit 0 so a normal regression night with real test failures doesn't make
    # Task Scheduler flag the task as broken — pass/fail lives in the results,
    # the app, and this report. Non-zero only on infrastructure failure above.
    return 0


if __name__ == "__main__":
    sys.exit(main())
