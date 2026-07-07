# ETL Test Console (Next.js app)

The control-plane UI for the `etl_test` Python framework: run tests (single test
cases or whole scenarios), review results, manage connections/suites/mappings/
reports, and get Teams alerts on data-quality failures — all in the browser. It
spawns the existing `etl-test` CLI (in the repo's `.venv`) as a child process; the
Python engine is unchanged. See the [repo-root README](../README.md) for the
full system (Python CLI/scripts + Cursor agent skills) — this file covers the
app specifically.

Stack: Next.js 14 (App Router, webpack) · React 18 · Tailwind **v3** · shadcn/ui
(v3 components) · IBM Plex Sans/Mono. No database — config lives in the repo's
YAML/JSON and run history in `output/` (the same files the CLI reads/writes).

## Running it (node-direct — works on the locked-down VM, no `.cmd`)

Every command is a plain `node …` call — never `npm run` / `npx` (those resolve
to blocked `.cmd` shims). See [`TOOLING.md`](TOOLING.md) for the full explanation.

```bat
node scripts/install.js            :: install deps (like npm install)
node server.js                     :: start dev server  -> http://127.0.0.1:3000
node scripts/build.js              :: production build
set NODE_ENV=production & node server.js   :: run the production build
node scripts/add-component.js <name>       :: add a shadcn/ui component (node-direct)
```

On the dev machine you can also use `npm run dev` etc. — the scripts are wired to
the node-direct entrypoints either way.

## Configuration (`.env.local`)

Copy [`.env.local.example`](.env.local.example) to `.env.local`:

```
REPO_ROOT=D:\Test Script                          # repo root (has config/, output/, .venv)
PYTHON_EXE=D:\Test Script\.venv\Scripts\python.exe # the venv python the app spawns
HOST=127.0.0.1
PORT=3000

# Optional — team run sharing (see "Team run sharing" below):
# TEAM_RUNS_ROOT=C:\Users\<you>\OneDrive - <Company>\ETL Test Runs
# TEAM_MEMBER=<your-name>          # defaults to your OS username if omitted
```

No database credentials here. Data-source secrets stay in the repo-root `.env`,
referenced by `${VAR}` in `config/connections.yaml`, exactly as the CLI reads
them — the app only edits non-secret fields and the env-var *names*.

## Try it (offline demo, no credentials)

The repo ships a `demo` suite over seeded SQLite data:

1. Open **New run**, pick the **demo** suite, click **Run**.
2. Watch the categories stream live, then land on the run's Command Center
   (pass-rate, deltas vs the previous run, new/recurring failures, per-check
   evidence).

There's also an offline `demo_report` (under **Reports**) with a clean tab and a
deliberately broken tab, so a report run shows both PASS and FAIL with evidence.

## Pages

- **Runs** — team-wide run history (merged across `TEAM_RUNS_ROOT` members) with
  a Scenario column + filters, and the Command Center run-detail view.
- **New run** — trigger a suite, live SSE progress, redirect to the result.
- **Scenarios** — list of test scenarios; a scenario page shows its test cases
  (suites) with their latest result, lets you attach/detach cases or create a new
  one pre-assigned to the scenario, and **runs every case sequentially** with a
  live rollup, persisting a scenario-run record.
- **Connections / Suites** — edit `config/connections.yaml` and
  `config/suites/*.yaml` through forms (a suite is a "test case": source, target,
  mapping, categories, optional test scenario, optional report ids).
- **Mappings** — view tables/columns and edit business rules / referential
  integrity of the app-owned `config/mappings/*.json` (imported from Excel via
  `etl-test export-mapping`).
- **Reports** — GVC/MD&A report definitions; each tab holds an ACTUAL (Snowflake)
  and EXPECTED (legacy Access) query, key/compare columns, and measures; **Run
  report** triggers the 2-phase (structure + data) validation.
- **Alerts** — configure DQ alert rules (which statuses/severities trigger, which
  suites, the Power Automate webhook env var) and view the team-wide alert log.

## How a run works

`POST /api/runs` spawns `python -m etl_test.cli run --suite … --output …` with
`ETL_TEST_PROGRESS_JSON=1`; the CLI prints newline-delimited JSON progress on
stdout, which `runManager` parses and fans out over SSE
(`GET /api/runs/<jobId>/stream`). When the child exits, the CLI has already
written `output/<member>/runs/<id>/result.json` + refreshed `manifest.json`, so
the run detail page just reads them, and `alerts.ts` evaluates the fresh result
against `config/alerts.json` (posting to Teams if it trips). Runs are serialized
(one at a time; a second start returns HTTP 409).

**Scenario batches** (`POST /api/scenarios/<id>/run`) work the same way, just
sequentially across every test case in the scenario: `runManager.startScenarioRun`
reuses the same per-suite spawn for each case (so each case's own run/result/alert
behaves identically to a manual run), streams `case_start`/`case_complete`/
`batch_complete` over SSE (`GET /api/scenarios/runs/<batchId>/stream`), and
persists a `ScenarioRunRecord` to `output/<member>/scenario-runs/<batch>.json`
after each case completes. The same 409 guard covers batches, so a single run and
a scenario run can't overlap.

## Team run sharing

Every run this machine produces is written under
`${TEAM_RUNS_ROOT}/${TEAM_MEMBER}/...` (default: local `output/` + your OS
username — no behavior change for solo use). Point `TEAM_RUNS_ROOT` at a folder
synced by everyone's OneDrive client; each teammate's app only ever **writes**
its own subfolder, and **reads** (merges) every subfolder to build the team-wide
`/runs`, `/scenarios`, and `/alerts` views — single-writer-per-file, so nothing
for OneDrive's sync to corrupt. A run is addressed by a `<member>~<run_id>`
reference so any teammate's run is a valid link for everyone. See the
[repo-root README §2(f)](../README.md#2-using-the-nodejs-app) for the full setup
steps.
