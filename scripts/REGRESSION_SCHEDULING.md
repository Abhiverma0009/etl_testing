# Scheduling regression suites (nightly / weekly)

Runs **every suite** as a regression batch on a schedule, using Windows Task
Scheduler + the venv's `python.exe` directly (native `.exe`, so it works on the
locked-down VM — no `.bat` shim, which is what failed before).

Each suite's run appears in the app under a dedicated **`regression`** team
member (with its own **Download PDF** button, like any manual run), and a
one-page **HTML batch summary** is written for quick evidence / sign-off.

## Pieces

| File | Purpose |
|---|---|
| [`run_regression.py`](run_regression.py) | Runs all suites once, writes runs under `output/regression/`, and generates the batch HTML report. No date gate — cadence is owned by Task Scheduler. |
| [`install_regression_schedule.py`](install_regression_schedule.py) | Registers/removes the scheduled task for you (pick nightly or weekly). |

## Selecting which suites run

By default the batch runs **every** suite. To run a chosen subset, select them
in the app the natural way — **create a Scenario** (`/scenarios`) and tag the
suites (test cases) you want into it — then point the schedule at that scenario.
No code, and you can change the set anytime by editing the scenario in the app.

- `--scenario "<id or name>"` — run only suites tagged with that scenario.
- `--exclude <stem>` — drop specific suites (repeatable).

Run `run_regression.py` with no `--scenario`/`--suite` to run all suites.

## 1. Choose a schedule (one-time setup)

Run from the repo root. **Nightly at 02:00, all suites:**

```
.venv\Scripts\python.exe scripts\install_regression_schedule.py --nightly --time 02:00
```

**Nightly, only the suites in a scenario** (accepts the scenario id or its
display name from `config/scenarios.yaml`):

```
.venv\Scripts\python.exe scripts\install_regression_schedule.py --nightly --scenario "Data Quality"
```

**Weekly, Mondays at 01:30, excluding the not-ready report suites:**

```
.venv\Scripts\python.exe scripts\install_regression_schedule.py --weekly --day MON --time 01:30 --exclude gvc --exclude mda
```

(`--day` accepts MON..SUN. Add `--dry-run` to preview the command without registering.)

## 2. Verify / test

```
# confirm it's registered
schtasks /Query /TN "ETL Regression Batch" /V /FO LIST

# run the whole batch right now (don't wait for the schedule)
schtasks /Run /TN "ETL Regression Batch"
```

After it runs, open the app → **Runs**, filter by member **`regression`** to see
each suite's result and download its PDF. The batch overview is at
`output\_regression_reports\regression_<timestamp>.html` — open it in a browser
and **Print → Save as PDF** for a single evidence file.

## 3. Change or remove the schedule

Re-run the install command with different flags to change it, or remove it:

```
.venv\Scripts\python.exe scripts\install_regression_schedule.py --uninstall
```

## Running the batch manually (no scheduling)

```
# all suites
.venv\Scripts\python.exe scripts\run_regression.py

# only the suites in a scenario (id or display name)
.venv\Scripts\python.exe scripts\run_regression.py --scenario "Data Quality"

# only specific suites by path
.venv\Scripts\python.exe scripts\run_regression.py --suite config/suites/bronze_to_silver.yaml

# all except suites that still need real SQL / a live connection
.venv\Scripts\python.exe scripts\run_regression.py --exclude gvc --exclude mda --exclude snowflake_live_test
```

## Notes

- **Report suites need input first.** `gvc.yaml` / `mda.yaml` ship with `-- TODO`
  SQL stubs and `snowflake_live_test.yaml` needs a live Snowflake connection, so
  those will show as ERROR/FAIL in a full-batch run until they're filled in.
  Use `--exclude` to leave them out of nightly regression until then.
- **Exit code is 0 even when tests fail** — so Task Scheduler shows the job as
  healthy on a normal night with real test failures. Pass/fail lives in the run
  results, the app, and the batch report, not the task's exit code.
- **Shared team folder:** set `TEAM_RUNS_ROOT` in the task's environment (or pass
  `--output-root`) to write scheduled runs beside the team's on OneDrive, under
  `…/regression/`.
