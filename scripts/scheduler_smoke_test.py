"""Minimal script to confirm Windows Task Scheduler can invoke the venv's
python.exe directly. Not part of the regression-suite flow — delete once the
Task Scheduler check is done.
"""
import datetime as dt
from pathlib import Path

out = Path(__file__).resolve().parent / "scheduler_smoke_test.log"
with open(out, "a", encoding="utf-8") as f:
    f.write(f"Ran OK at {dt.datetime.now().isoformat()}\n")

print("Scheduler smoke test ran successfully.")
