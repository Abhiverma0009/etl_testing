# Carlyle ValDB → Snowflake — Migration Test Console

The single source of truth for validating the **Carlyle Valuation Data Migration**
(Hexaware). It proves that data moved from the legacy **MS Access ValDB** (and the
GPE/ILM, Global Credit and AlpInvest feeds) into the **Snowflake EDP** — across the
Bronze → Silver → Gold medallion layers — is **consistent, complete and correct**,
and that the **GVC** and **MD&A** reports built on the new data still match the
legacy reports. Because migrated data feeds higher-management reporting, this app is
the QA team's authoritative record of what was tested and what passed.

**This is a three-part system, and this README is the map to all three:**

| Part | What it is | Where |
|---|---|---|
| **The Node.js app** | A browser control-plane — run tests, review results, manage config, no hand-editing YAML. | [`Testing Orchestrator App/`](Testing%20Orchestrator%20App/) — [§2 Using the app](#2-using-the-nodejs-app) |
| **The Python engine & scripts** | The actual test engine (`etl_test`), plus standalone scripts for scheduling and Excel/CSV ingestion. Runs headless via CLI too. | [`etl_test/`](etl_test/), [`scripts/`](scripts/) — [§3 Using the Python CLI & scripts](#3-using-the-python-cli--scripts) |
| **The Cursor agent skills** | Two paired rules that turn Jira stories into draft test cases, and test cases into runnable config — so QA authoring doesn't mean hand-writing YAML. | [`.cursor/rules/`](.cursor/rules/) — [§4 Using the Cursor agent skills](#4-using-the-cursor-agent-skills) |

They compose into one pipeline:

```
Jira story ──[jira-to-test-cases skill]──▶ draft test cases ──[test-case-to-suite skill]──▶
config/scenarios.yaml + config/suites/*.yaml ──[Node.js app or CLI]──▶ live run ──▶ Command Center / Teams alert
```

You don't have to use all three — you can hand-write suite YAML and skip the skills
entirely, or drive everything from the CLI without the app. But together they cover
requirements → test authoring → execution → reporting end to end.

---

## 1. Domain model & architecture

### What we're testing

- **Grain:** Deal → Fund → Valued Asset. The two core Gold tables are
  **`VALUATION_DEAL_FUND`** and **`VALUATION_DEAL_FUND_VALUED_ASSET`**.
- **Investment levels:** `MF` (Main Fund) and `CO1` (Fund with Coinvestment) are
  in scope; `CO2` is excluded; `CO3` exists for some families.
- **Medallion layers (Snowflake):** `STAGING → BRONZE → SILVER → GOLD`, each a
  connection that differs only by schema. Reporting is served from a **Sigma
  Override** 3-schema model: `REPORTING`, `DATA_OVERRIDES`, plus production Gold.
- **Sources:** GPE/ILM (Snowflake views), Global Credit (CSP/CEMOF/CAP Excel
  workbooks), AlpInvest (Excel), and legacy ValDB (MS Access). Each source reaches
  Gold through its own hop suites.
- **Golden source:** ILM for active funds (1987+); ValDB for inactive funds, GC
  CSP III/IV, CEMOF II, and AlpInvest.
- **Key business rules encoded** (from the requirements workbook): Global Credit
  rules 121-172 (fund ∈ {CSP,CEMOF,CAP}; level MF/CO1; D/E flag; R/U/P status;
  mandatory keys; duplicate prevention 165), AlpInvest rules 78-120 (strategy ∈
  {Fund,Secondary,Mezzanine,Co-Investment}; currency ∈ {EURM,USDM,CHFM,JPYM};
  Valuation-ID keying; dedup 111), the debt/equity roll-up ("any Equity security ⇒
  whole valued asset is Equity"), and null≠zero handling for FMV.

### How the pieces fit together

```
┌────────────────── Next.js app (Testing Orchestrator App/) ────────────────┐
│  Pages: /runs  /runs/new  /scenarios  /connections  /suites  /mappings     │
│         /reports  /alerts             (App Router, Tailwind v3, shadcn/ui) │
│                                                                            │
│  /api/runs, /api/scenarios/*  ──spawn──▶  python.exe -m etl_test.cli …┐    │
│      ▲  SSE progress  ◀──────── JSON-lines on stdout ──────────────────┘   │
│  runManager (child process + EventEmitter, sequential batches)             │
│  alerts.ts (Teams webhook)  ·  flat-file stores (fs + yaml, no database)   │
└────────────────────────────────────────────────────────────────────────────┘
        │ reads / writes plain files                          │ writes
        ▼                                                      ▼
  config/  connections.yaml  scenarios.yaml  suites/*.yaml    output/
           mappings/*.json   reports/*.json  alerts.json       <member>/
        │                                                        manifest.json
        │                                                        runs/<id>/result.json
        │                                                        runs/<id>/evidence/*.csv
        │                                                        scenario-runs/<batch>.json
        │                                                        alerts.json
        ▼                                                      ▲
┌──────────────────────── Python engine (etl_test/) ─────────┴──────────────┐
│  connectors/  access · snowflake · sqlserver · files · sqlite + factory    │
│  mapping/     Excel + JSON loaders → MappingBook (tables/columns/rules/FK)  │
│  core/        normalize (null≠zero, tolerance) · comparison (key diff) ·    │
│               runner (isolates each check, emits progress, writes result)   │
│  validators/  15 data validators + report validator (2-phase)              │
│  reporting/   manifest builder · report-definition loader                  │
└──────────────────────────────────────────────────────────────────────────┬─┘
        ▲ scheduled invocation (Task Scheduler, T+6)                       │
   scripts/scheduled_report_run.py ── scripts/extract_test_cases.py ◀──────┘
                                        (Excel/CSV → Markdown, feeds the skills)
```

- **Persistence is flat files, no database.** The app reads/writes the exact files
  the Python CLI consumes; run history *is* the CLI's output. Zero native binaries
  in the persistence layer (this matters on the locked-down client VM).
- **Team run sharing, single-writer-per-folder.** Every run this machine produces
  lands under `${TEAM_RUNS_ROOT}/${TEAM_MEMBER}/...` (defaults: local `output/` +
  your OS username — no behavior change for solo use). Point `TEAM_RUNS_ROOT` at a
  folder synced by everyone's OneDrive client and each teammate **only ever writes
  their own subfolder** — the app reads (merges) every subfolder to build the
  team-wide `/runs`, `/scenarios`, and `/alerts` views. Because no two machines
  ever write the same file, there's nothing for OneDrive's sync to race or
  corrupt — unlike a single shared SQLite file on OneDrive, which *is* a real
  corruption risk (SQLite needs real file locks; OneDrive is an
  eventually-consistent sync client, not a live shared filesystem). Run links use
  a `<member>~<run_id>` reference so any teammate's run is addressable from
  anyone's browser.
- **Runtime resilience:** runs (and scenario batches) are serialized per machine
  (one at a time, 409 on overlap); progress is also appended to
  `runs/<id>/progress.ndjson` so a reconnecting client can replay after a dev
  hot-reload.
- **Restricted-VM friendly:** all Node tooling is invoked as plain `node <script>.js`
  (see [`Testing Orchestrator App/TOOLING.md`](Testing%20Orchestrator%20App/TOOLING.md))
  — never through a `.cmd` shim — and Python is spawned as a direct `python.exe`
  call, so nothing depends on the blocked `.cmd` execution.
- **Where AI fits (and doesn't):** every pass/fail decision is deterministic
  pandas/business-rule logic — never an LLM judgment call. Cursor (or Claude) only
  *drafts content a human reviews* — test-case text, report SQL — via the two
  agent skills in §4. It never writes to `config/` on its own authority; a human
  always reviews before a draft becomes a runnable suite.

### Capabilities

**15 data validators**, run per medallion hop against a mapping: `row_count`,
`schema`, `datatype`, `completeness`, `business_rules`, `referential_integrity`,
`transformation`, `historical`, `deduplication`, `null_handling`, `reconciliation`,
`lineage`, `incremental`, `cross_source`.

**Report validation (`report`)** — for GVC / MD&A, in **two phases per tab**.
*Phase 1 · structure* verifies the report lines up before touching data: column
parity, that configured key/compare columns exist on both sides, and row-count
parity. *Phase 2 · data* does the key-level row diff (missing/extra deals, value
mismatches within tolerance) plus measure reconciliation. Each tab compares the
**new Snowflake query (ACTUAL)** against the **legacy Access ValDB query
(EXPECTED)**; a hard Phase-1 failure **gates** Phase 2 to SKIPPED so you fix
structure before drowning in row noise. (`gvc_report` is a back-compat alias.)

**Test scenarios** — QA planning is two levels: a **test scenario** groups multiple
**test cases** (a test case = one suite). The `/scenarios` page lists them, shows
each scenario's test cases with their latest result, lets you attach/detach/create
cases from the scenario page itself, and **runs every case in a scenario at once**
(sequentially, continuing past failures) with a persisted, team-visible batch record.

**Data Quality (DQ) + alerting** — the `dq_report` suite runs the DQ-relevant
validators over curated Gold tables. When a run trips the rules in
`config/alerts.json`, the app posts a summary to a **Teams channel via a Power
Automate HTTP webhook** and records it under `/alerts`.

**Scheduled runs** — report suites can run automatically at **quarter-end + 6
days** via Windows Task Scheduler + a self-guarding Python runner (no job runner
needed on the locked-down VM) — see [§3](#3-using-the-python-cli--scripts).

---

## 2. Using the Node.js app

The day-to-day interface. It spawns the Python engine as a child process — you
never touch a terminal for a normal test run.

### One-time setup

Prerequisites (once per machine): **Python 3.11+** and **Node.js LTS** installed
(so `python` and `node` are on `PATH`), plus the **MS Access ODBC driver** if you
use Access sources.

```powershell
# Python engine + connectors (dedicated venv used by both the CLI and the app).
# The [connectors] extra pulls in snowflake-connector-python[secure-local-storage]
# (Snowflake + SSO token caching) and pyarrow. Calling python.exe directly means
# no Activate.ps1 — handy on locked-down VMs where script execution is blocked.
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[connectors]"

# Credentials — never in YAML/JSON, only in .env (git-ignored)
copy .env.example .env      # then fill SNOWFLAKE_*, ACCESS_DB_PATH, feed dirs
#   add TEAMS_WEBHOOK_URL=<your Power Automate URL> to enable DQ alerts

# Web app (node-direct — no npm/npx .cmd shims; works on the restricted VM)
cd "Testing Orchestrator App"
copy .env.local.example .env.local   # then set REPO_ROOT + PYTHON_EXE to YOUR paths
node scripts\install.js     # installs React + all app deps (this IS `npm install`, node-direct)
node server.js              # dev server on http://localhost:3000
#   node scripts\build.js && set NODE_ENV=production && node server.js   # prod
```

`.env.local` lives **inside** `Testing Orchestrator App/` (not the repo root) and
holds no secrets — just per-machine paths. `REPO_ROOT` is this repo's folder and
`PYTHON_EXE` is `<REPO_ROOT>\.venv\Scripts\python.exe`; each teammate sets their
own. `node scripts\install.js` already runs `npm install` the node-direct way, so
there's no separate `npm install` step (that would go through the blocked
`npm.cmd` shim).

Drivers: the **MS Access ODBC driver** is required for Access sources; Snowflake
uses its own Python connector; SQL Server needs an ODBC driver. Full app-specific
detail (page-by-page, node-direct tooling rationale) lives in
[`Testing Orchestrator App/README.md`](Testing%20Orchestrator%20App/README.md).

**Snowflake SSO:** for external-browser SSO, set the connection's **Authenticator**
to `externalbrowser` (Connections page, or `authenticator: externalbrowser` in
`connections.yaml`) and leave Password blank. The `[secure-local-storage]` extra
installed above caches the SSO token so the browser prompt doesn't reappear on
every connection.

### Walkthroughs

**a) Validate a medallion hop.** `/suites` → pick or add a suite (source, target,
mapping, which categories, optionally a test scenario). `/runs/new` → choose the
suite → **Run** → watch live per-category progress → land on the run's Command
Center with pass-rate, deltas vs the previous run, new/recurring failures, and
per-check evidence + remediation.

**b) Plan & run a test scenario.** `/scenarios` → **Add scenario** (name +
description). Attach test cases either from `/suites` (edit a suite → **Test
scenario** dropdown) or directly from the scenario page (**Add existing** to
attach suites already defined, or **New test case** to create one pre-assigned to
this scenario). Back on `/scenarios/<id>` → **Run all** → every test case runs
sequentially with live per-case pass/fail, a rollup, and links to each run; the
batch is saved under "Scenario run history" and each case shows in `/runs` with
the Scenario column.

**c) Test a GVC / MD&A report.** `/reports` → open a report (28 GVC tabs / 17
MD&A tabs seeded) → for each tab set the **ACTUAL** Snowflake query and the
**EXPECTED** legacy Access query, key columns / compare columns / measures →
**Run report**. The run shows a *Report structure* check (Phase 1) plus *Report
data* / *Report measures* checks (Phase 2) per tab, grouped by report. Query
bodies ship as `TODO` stubs — the real SQL has to come from the GVC/MD&A
workbooks (Access saved query → SQL View is the most reliable source), optionally
drafted with Cursor's help and always human-reviewed before use.

**d) DQ run → Teams alert.** Set `TEAMS_WEBHOOK_URL` in `.env`, enable alerting on
`/alerts` (pick trigger tokens, e.g. FAIL/ERROR/P1). Run `dq_report` from
`/runs/new`. On failure a summary posts to Teams via Power Automate and appears
under `/alerts`. *Power Automate setup:* a flow with **"When an HTTP request is
received"** → **"Post message in a channel"**, mapping the JSON fields (`title`,
`text`, `run_id`, `suite`, `failed`, `checks`) the app posts.

**e) Manage config in-app.** `/connections` (non-secret fields + the *name* of
each secret env var), `/suites`, `/mappings` (tables/columns/business rules/FK),
and `/reports` are all form-driven. Edits write the same files the CLI reads, so
the *next* run reflects them immediately.

**f) Turn on team run sharing.** Everyone adds the same shared OneDrive folder
locally (e.g. via a shared Teams channel's Files tab → "Add shortcut to My
OneDrive"), then each person copies `Testing Orchestrator App/.env.local.example`
to `.env.local` and sets `TEAM_RUNS_ROOT` to that folder's local path on their own
machine (the absolute path differs per person; the shared folder it points at is
the same). Restart the app. `/runs`, `/scenarios`, and `/alerts` now show every
teammate's activity (with a Member column). No suite/mapping/report config is
shared this way — only run history; keep `config/` in sync between teammates
separately if needed.

---

## 3. Using the Python CLI & scripts

Everything the app does, it does by driving this engine — you can drive it
directly too, headlessly, for CI or ad-hoc work.

### `etl_test` CLI

```powershell
.\.venv\Scripts\python.exe -m etl_test.cli list-tests
.\.venv\Scripts\python.exe -m etl_test.cli test-connection snowflake_gold
.\.venv\Scripts\python.exe -m etl_test.cli run --suite config/suites/bronze_to_silver.yaml
.\.venv\Scripts\python.exe -m etl_test.cli run --suite config/suites/gvc.yaml         # report suite
.\.venv\Scripts\python.exe -m etl_test.cli export-mapping config/mappings/valdb_mapping.xlsx
```

Exit code: `0` pass · `1` a check failed · `2` a check errored (CI gate).

### `scripts/` — standalone helpers (not run through the app)

| Script | Purpose | Run it |
|---|---|---|
| [`extract_test_cases.py`](scripts/extract_test_cases.py) | Dumps an Excel workbook or CSV (a test-case sheet, or a Jira export) to readable Markdown under `output/_extracted/`, since raw `.xlsx`/tabular data isn't directly usable by an LLM. Feeds the Cursor skills in §4. | `.\.venv\Scripts\python.exe scripts\extract_test_cases.py "docs\My Test Cases.xlsx"` (or point it at a folder, or a `.csv`) |
| [`scheduled_report_run.py`](scripts/scheduled_report_run.py) | Runs the GVC/MD&A report suites automatically at **quarter-end + 6 calendar days**; safe to invoke daily via Task Scheduler since it self-guards to the target date (`--force` to run immediately). See [`scripts/SCHEDULING.md`](scripts/SCHEDULING.md) for the full Task Scheduler setup (native `schtasks.exe`, no `.cmd`). | `.\.venv\Scripts\python.exe scripts\scheduled_report_run.py --force` |
| [`samples/build_demo.py`](samples/build_demo.py) | Builds the offline SQLite demo (source/target with seeded defects) + the demo mapping workbook. | `.\.venv\Scripts\python.exe samples\build_demo.py` |
| [`samples/make_mapping_template.py`](samples/make_mapping_template.py) | Generates a blank, correctly-structured mapping workbook (`Tables`/`Columns`/`BusinessRules`/`ReferentialIntegrity` sheets with example rows) for the team to fill in for a new source. | `.\.venv\Scripts\python.exe samples\make_mapping_template.py` |

---

## 4. Using the Cursor agent skills

Two rules under `.cursor/rules/` — Cursor's agent loads them automatically based
on what you ask for; you don't invoke them by name. Both only ever **draft
content for human review** — neither runs a test or decides pass/fail, and
neither writes to `config/` without you asking.

### `jira-to-test-cases` — draft test scenarios & cases from requirements

**Use when:** you have Jira stories describing a source system and need QA test
scenarios + cases drafted before they become runnable config.

**Inputs needed from you:**
1. The Jira story content — paste it in chat, save it under `docs/jira/`, or
   export multiple stories from Jira (Issue Navigator → Export → CSV/Excel) and
   run `scripts/extract_test_cases.py` on the export first (it now reads `.csv`
   too, not just `.xlsx`).
2. Which source system the story is about (GPE/ILM, Global Credit, AlpInvest,
   ValDB, or a new one) — the skill will ask if it's not obvious.
3. Optionally, which medallion hop, if the story is scoped to one stage.

**How to use it:** in Cursor, *"Draft test scenarios and test cases from this
Jira story: [paste it, or `@docs/jira/GC-101.md`]."* It writes a draft to
`output/_drafted/<name>.md` — test cases grouped by scenario, with an
**Assumptions & Open Questions** section flagging anything it inferred rather
than read directly from the story. It never invents connection/table names not
already in `config/`; if the story is about a source system that doesn't exist
yet, it says so explicitly.

### `test-case-to-suite` — convert test cases into runnable config

**Use when:** you have test cases (from the skill above, a manual Excel test
matrix, or a Jira/Zephyr export) and want them turned into `config/scenarios.yaml`
+ suite/mapping/report config the app can run.

**Inputs needed from you:**
1. The test-case content — a draft from the skill above, or an Excel/CSV file
   (run `scripts/extract_test_cases.py` on it first, same as above).
2. Confirmation on anything it flags as ambiguous or missing from `config/`.

**How to use it:** *"Convert the test cases in `@output/_extracted/GC Source
E2E.md` into scenarios and suites."* It classifies each test case (structural
check → a suite category; a specific rule → a mapping business rule; a report tab
→ report JSON), groups cases sharing a hop into one suite file, creates/tags the
test scenario, and reports back a conversion table (test case → artifact → file
→ any gaps). Everything it writes shows up immediately in the app under
`/scenarios`, `/suites`, `/mappings`, `/reports` for you to review before running.

**The full pipeline in one request:** you can ask for both in sequence — *"Draft
test cases from this Jira story, then convert them into suites"* — and Cursor
will chain the two rules in the same turn, still stopping at each artifact for
you to review before it becomes authoritative.

---

## 5. Layout

```
etl_test/            Python engine (connectors, mapping, core, validators, reporting, cli)
config/
  connections.yaml   named connections (secrets as ${ENV})
  scenarios.yaml      test-scenario registry (name/description; membership lives on the suite)
  suites/*.yaml       one validation hop, report run, or DQ run per file (a "test case")
  mappings/*.json     app-owned mapping books (tables, columns, business rules, FK)
  reports/*.json      report definitions (GVC/MD&A tabs: ACTUAL vs EXPECTED queries)
  alerts.json         DQ alert rules (Teams via Power Automate)
output/               <member>/{manifest.json, runs/<id>/{result.json, evidence/*.csv},
                       scenario-runs/<batch>.json, alerts.json}; _extracted/, _drafted/ (skill I/O)
scripts/              extract_test_cases.py, scheduled_report_run.py, SCHEDULING.md, Task Scheduler XML
docs/                 input material (e.g. docs/jira/*.md, Jira/Excel exports) for the Cursor skills
.cursor/rules/         jira-to-test-cases.mdc, test-case-to-suite.mdc
Testing Orchestrator App/   Next.js control-plane app (server.js, scripts/, src/) — see its own README
samples/              offline SQLite demo (build_demo.py), mapping template generator
tests/                pytest (offline e2e + unit + report validator + lineage regression)
```

---

## 6. Offline demo & tests

```powershell
.\.venv\Scripts\python.exe samples\build_demo.py          # SQLite source/target + seeded defects
.\.venv\Scripts\python.exe -m etl_test.cli run --suite samples\demo_suite.yaml
.\.venv\Scripts\python.exe -m pytest -q                    # engine + report-validator + lineage tests
```

The demo report `config/reports/demo_report.json` (offline, uses the demo SQLite)
has a clean tab and a deliberately broken tab so a report run shows PASS + FAIL
and its evidence drill-downs.

---

## 7. Notes & limitations

- Comparison is **in-memory (pandas)**; per-connection `max_rows` caps guard
  against OOM — narrow with a `where`, raise the cap, or allow sampling for huge
  tables.
- `historical`, `incremental`, `cross_source` need extra config (a baseline
  snapshot or second source) and SKIP cleanly with a clear message when it's
  absent.
- **A data source (or target) may be a table or a view** — every connector reads via
  `SELECT ... FROM <name>`, which is identical for both in Snowflake/SQL Server/Access,
  so a view is referenced by name exactly like a table. A mapping row can record which
  side is a view via `source_object_type` / `target_object_type` (`table` | `view`,
  default `table`) — descriptive metadata for audit clarity; it doesn't change reads.
- Report tab SQL and some mapping column/table names are seeded from the
  requirements documentation; confirm them against the live Snowflake objects
  before a real run.
- Secrets live only in `.env`. The connections UI edits the env-var *name*,
  never a value; the Teams webhook URL is read from the env var named in
  `config/alerts.json`.
- The Cursor skills draft content; they never decide test outcomes and never
  write to `config/` without an explicit ask — always review before running
  what they produce.
