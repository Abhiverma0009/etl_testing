# Scheduling report validation (T+6 post quarter-end)

The report suites (GVC / MD&A) are meant to run at **quarter-end + 6 calendar days**.
There is no job runner on the client VM, so we use **Windows Task Scheduler** (native)
plus a small self-guarding runner script — nothing to reschedule each quarter.

## How it works

- **[`scheduled_report_run.py`](scheduled_report_run.py)** is invoked **daily** by
  Task Scheduler. It computes the most recent quarter-end + N days (default **6**)
  and only actually runs the suites on that date; every other day it exits quietly.
- Runs are written under **`output/scheduled/`**, so they appear in the app's team
  run history as a member named **`scheduled`** (and trip DQ alerting like any run).
- Per-suite logs go to `output/_scheduled_logs/`; `last_check.txt` / `last_run.txt`
  record the most recent daily check and run.

## Install the scheduled task (one-time)

Both commands use `schtasks.exe` — a native Windows executable, **not** a `.cmd`
shim — so they work on the locked-down VM. Run in a normal terminal from the repo
root. Adjust the `D:\Test Script` paths if the repo lives elsewhere.

**Option A — import the ready-made definition (recommended):**

```
schtasks /Create /TN "ETL Report Validation T+6" /XML "D:\Test Script\scripts\etl_report_task.xml" /F
```

**Option B — create it inline (no XML file):**

```
schtasks /Create /TN "ETL Report Validation T+6" ^
  /TR "\"D:\Test Script\.venv\Scripts\python.exe\" \"D:\Test Script\scripts\scheduled_report_run.py\"" ^
  /SC DAILY /ST 06:00 /F
```

(`^` is the CMD line-continuation; put it on one line in PowerShell, or use the
PowerShell backtick `` ` ``.)

## Verify / operate

```
# see it registered / its last result
schtasks /Query  /TN "ETL Report Validation T+6" /V /FO LIST

# run it right now (ignores the date guard via the task action? no — use the script):
.venv\Scripts\python.exe scripts\scheduled_report_run.py --force

# dry-run the date logic only (prints whether today is the target day):
.venv\Scripts\python.exe scripts\scheduled_report_run.py            # exits quietly if not T+6

# remove the task
schtasks /Delete /TN "ETL Report Validation T+6" /F
```

After a real (or `--force`) run, open the app → **/runs**, filter by member
**`scheduled`**, to review the results.

## Options (script flags)

| flag | default | purpose |
|---|---|---|
| `--offset-days N` | `6` | run on quarter-end + N calendar days |
| `--suite PATH` | gvc + mda | suite to run (repeatable) |
| `--force` | off | run now regardless of date (testing / ad-hoc close) |
| `--member NAME` | `scheduled` | team-member folder runs are written under |
| `--output-root DIR` | `$TEAM_RUNS_ROOT` or `./output` | base output dir |

To run against the **shared OneDrive** team folder, set `TEAM_RUNS_ROOT` in the
task's environment (or pass `--output-root`) so scheduled runs land beside the
team's, under `…/scheduled/`.

## Prerequisite

The GVC/MD&A tabs must have **real SQL** filled in (they ship as `-- TODO` stubs).
Until then a scheduled run will execute but every tab errors on the placeholder
query — the scheduling itself is ready; the report queries are the remaining input.
