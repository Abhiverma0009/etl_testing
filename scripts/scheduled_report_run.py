"""Scheduled report-validation runner (T+N post quarter-end).

Designed to be invoked **daily** by Windows Task Scheduler. It only actually runs
the report suites on the target day — quarter-end + N calendar days (default
N=6) — and exits quietly otherwise, so there is nothing to reschedule each
quarter and no dependency on a job runner the locked-down VM might block.

Runs land under ``<output-root>/scheduled/`` so they appear in the app's team
run history as a distinct member "scheduled" (see the Node app's TEAM_RUNS_ROOT
convention). If DQ alerting is enabled, the scheduled run trips it exactly like a
manual run would.

Examples
--------
  # what Task Scheduler runs daily (self-guards to the T+6 date):
  .venv\\Scripts\\python.exe scripts\\scheduled_report_run.py

  # run right now regardless of date (for testing / an ad-hoc quarter close):
  .venv\\Scripts\\python.exe scripts\\scheduled_report_run.py --force

  # different offset / specific suites:
  .venv\\Scripts\\python.exe scripts\\scheduled_report_run.py --offset-days 7 --suite config/suites/gvc.yaml
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
DEFAULT_SUITES = ["config/suites/gvc.yaml", "config/suites/mda.yaml"]


def last_quarter_end(today: dt.date) -> dt.date:
    """The most recent calendar quarter-end on or before ``today``."""
    ends = [
        dt.date(today.year - 1, 12, 31),
        dt.date(today.year, 3, 31),
        dt.date(today.year, 6, 30),
        dt.date(today.year, 9, 30),
        dt.date(today.year, 12, 31),
    ]
    return max(d for d in ends if d <= today)


def target_run_date(today: dt.date, offset_days: int) -> dt.date:
    return last_quarter_end(today) + dt.timedelta(days=offset_days)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run report suites at T+N post quarter-end.")
    ap.add_argument("--suite", action="append", default=[],
                    help="Suite path (repeatable). Default: gvc + mda.")
    ap.add_argument("--offset-days", type=int, default=6,
                    help="N calendar days after quarter-end to run (default 6).")
    ap.add_argument("--force", action="store_true",
                    help="Run now regardless of the date.")
    ap.add_argument("--member", default="scheduled",
                    help="Team-member folder to write runs under (default 'scheduled').")
    ap.add_argument("--output-root", default=None,
                    help="Base output dir (default: $TEAM_RUNS_ROOT or ./output).")
    args = ap.parse_args()

    suites = args.suite or DEFAULT_SUITES
    output_root = Path(args.output_root or os.environ.get("TEAM_RUNS_ROOT")
                       or (ROOT / "output"))
    out_dir = output_root / args.member
    log_dir = ROOT / "output" / "_scheduled_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    today = dt.date.today()
    target = target_run_date(today, args.offset_days)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    if not args.force and today != target:
        (log_dir / "last_check.txt").write_text(
            f"{stamp}: today={today} target={target} (Q-end+{args.offset_days}) — skipped\n",
            encoding="utf-8")
        print(f"Not the scheduled day (today={today}, target={target}); nothing to do.")
        return 0

    if not PYTHON.exists():
        print(f"ERROR: venv python not found at {PYTHON}", file=sys.stderr)
        return 3

    print(f"Scheduled report validation — {stamp} — writing to {out_dir}")
    results: list[tuple[str, int]] = []
    for suite in suites:
        log_path = log_dir / f"run_{stamp}_{Path(suite).stem}.log"
        with open(log_path, "w", encoding="utf-8") as fh:
            proc = subprocess.run(
                [str(PYTHON), "-m", "etl_test.cli", "run",
                 "--suite", suite, "--output", str(out_dir)],
                cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT)
        results.append((suite, proc.returncode))
        print(f"  {suite}: exit {proc.returncode}  (log: {log_path.name})")

    # The wrapper's own exit code reflects whether it *ran*, not whether tests
    # passed — pass/fail lives in the run results, the dashboard and alerts, so a
    # normal quarter with real failures doesn't make Task Scheduler look broken.
    (log_dir / "last_run.txt").write_text(
        f"{stamp}: ran {len(results)} suite(s): "
        + ", ".join(f"{s}=exit{rc}" for s, rc in results) + "\n",
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
