"""Register (or remove) the Windows Task Scheduler job that runs the regression
batch — a friendly wrapper around ``schtasks`` so you don't hand-write the
command (and don't hit the .bat/^-escaping problems).

It points the task at the venv's ``python.exe`` running ``run_regression.py``
directly (native .exe — works on the locked-down VM). Choose nightly or weekly.

Examples
--------
  # nightly at 02:00 (default):
  .venv\\Scripts\\python.exe scripts\\install_regression_schedule.py --nightly

  # weekly, Mondays at 01:30:
  .venv\\Scripts\\python.exe scripts\\install_regression_schedule.py --weekly --day MON --time 01:30

  # see what it WOULD run without registering:
  .venv\\Scripts\\python.exe scripts\\install_regression_schedule.py --nightly --dry-run

  # remove the scheduled task:
  .venv\\Scripts\\python.exe scripts\\install_regression_schedule.py --uninstall
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
RUNNER = ROOT / "scripts" / "run_regression.py"
TASK_NAME = "ETL Regression Batch"
VALID_DAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}


def build_runner_args(scenario: str | None, exclude: list[str]) -> str:
    """The run_regression.py arguments baked into the scheduled command."""
    parts: list[str] = []
    if scenario:
        parts.append(f'--scenario "{scenario}"')  # quoted: names can have spaces
    for stem in exclude:
        parts.append(f"--exclude {stem}")
    return (" " + " ".join(parts)) if parts else ""


def build_create_cmd(cadence: str, time: str, day: str, runner_args: str) -> list[str]:
    # /TR is a single argument holding the fully-quoted program + script (+ any
    # runner args); passing it as one list element lets subprocess handle the
    # outer quoting and schtasks parse the inner quotes — no CMD ^ line-
    # continuation or shim needed.
    tr = f'"{PYTHON}" "{RUNNER}"{runner_args}'
    cmd = ["schtasks", "/Create", "/TN", TASK_NAME, "/TR", tr, "/ST", time, "/F"]
    if cadence == "weekly":
        cmd += ["/SC", "WEEKLY", "/D", day]
    else:
        cmd += ["/SC", "DAILY"]
    return cmd


def main() -> int:
    ap = argparse.ArgumentParser(description="Install/remove the regression schedule.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--nightly", action="store_true", help="Run every day (default).")
    g.add_argument("--weekly", action="store_true", help="Run once a week.")
    ap.add_argument("--day", default="MON", help="Weekly day of week (MON..SUN, default MON).")
    ap.add_argument("--time", default="02:00", help="Start time HH:MM 24h (default 02:00).")
    ap.add_argument("--scenario", default=None,
                    help="Schedule only the suites in this scenario (id or name). "
                         "Omit to run all suites.")
    ap.add_argument("--exclude", action="append", default=[],
                    help="Suite stem to skip (repeatable), e.g. --exclude gvc.")
    ap.add_argument("--uninstall", action="store_true", help="Remove the scheduled task.")
    ap.add_argument("--dry-run", action="store_true", help="Print the schtasks command; don't run it.")
    args = ap.parse_args()

    if args.uninstall:
        cmd = ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
        print("Running:", " ".join(cmd))
        if args.dry_run:
            return 0
        return subprocess.run(cmd).returncode

    if not RUNNER.exists():
        print(f"ERROR: runner not found at {RUNNER}", file=sys.stderr)
        return 3

    day = args.day.upper()
    cadence = "weekly" if args.weekly else "nightly"
    if cadence == "weekly" and day not in VALID_DAYS:
        print(f"ERROR: --day must be one of {sorted(VALID_DAYS)}", file=sys.stderr)
        return 2

    runner_args = build_runner_args(args.scenario, args.exclude)
    cmd = build_create_cmd(cadence, args.time, day, runner_args)
    when = f"weekly on {day} at {args.time}" if cadence == "weekly" else f"nightly at {args.time}"
    scope = f"scenario '{args.scenario}'" if args.scenario else "all suites"
    print(f"Scheduling '{TASK_NAME}' - {when} - {scope}")
    print("Running:", " ".join(cmd))
    if args.dry_run:
        return 0
    rc = subprocess.run(cmd).returncode
    if rc == 0:
        print(f"\nDone. Verify with:  schtasks /Query /TN \"{TASK_NAME}\" /V /FO LIST")
        print(f"Run now to test:    schtasks /Run /TN \"{TASK_NAME}\"")
    return rc


if __name__ == "__main__":
    sys.exit(main())
