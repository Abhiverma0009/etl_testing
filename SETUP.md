# Teammate VM Setup

Step-by-step setup for running the ETL Test Console on a new (locked-down) VM.
Everything runs with plain `python` / `node` calls — no `npm`/`npx` `.cmd` shims,
which are blocked on the restricted VMs.

> **Where to run these:** open **PowerShell** in the repo root (the folder that
> contains `config/`, `etl_test/`, `Testing Orchestrator App/`, and `pyproject.toml`).

---

## 0. Prerequisites (install from the company portal)

| Component | Notes |
|-----------|-------|
| **Python 3.11+** | From the company portal. Confirm with `python --version`. |
| **Node.js LTS** | From the company portal. Confirm with `node --version`. |
| **Microsoft Access Database Engine 2016 Redistributable (64-bit)** | ODBC driver — **only** needed if you read from the Access ValDB. Skip if you only use Snowflake. See step 1. |

Also: get the repo folder onto the VM (git clone or copy), e.g.
`C:\Users\<you>\OneDrive - Carlyle\Documents\Dev\etl_testing`.

---

## 1. ODBC driver (Access sources only)

The Snowflake connector is pure-Python and needs **no** ODBC. This step is only
required to read the legacy MS Access ValDB. The company portal does **not** carry
this driver, so install it manually from Microsoft:

1. **Download** "Microsoft Access Database Engine 2016 Redistributable" from
   Microsoft: <https://www.microsoft.com/en-us/download/details.aspx?id=54920>.
   Choose **`AccessDatabaseEngine_X64.exe`** (the 64-bit build — it must match the
   64-bit Python you installed, *not* your Office bitness).
2. **Install.** Double-click the downloaded `.exe` and follow the prompts.
   - **If you hit** *"You cannot install the 64-bit version … because you currently
     have 32-bit Office products installed"*, that's the known Office-bitness clash.
     Install silently from PowerShell to bypass the check instead:
     ```powershell
     # cd to wherever the file downloaded, e.g. your Downloads folder
     .\AccessDatabaseEngine_X64.exe /quiet
     ```
   - This is a normal per-machine install; if the VM blocks it, you'll need whoever
     manages the VM to run it (or push it through the portal/SCCM).
3. **Verify** (after step 2's venv exists):
   ```powershell
   .\.venv\Scripts\python.exe -c "import pyodbc; print([d for d in pyodbc.drivers() if 'Access' in d])"
   ```
   Expected: `['Microsoft Access Driver (*.mdb, *.accdb)']`. An empty list means
   the driver isn't installed or is the wrong bitness.

---

## 2. Python engine

From the repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[connectors]"
```

The `[connectors]` extra installs `snowflake-connector-python[secure-local-storage]`
(Snowflake + SSO token caching) and `pyarrow`. We call `.venv\Scripts\python.exe`
directly, so there's **no `Activate.ps1`** to run (handy where PowerShell script
execution is blocked).

Then create the credentials file:

```powershell
copy .env.example .env
```

Open `.env` and fill in:
- `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`
- `SNOWFLAKE_AUTHENTICATOR=externalbrowser` (already the default — **SSO**; leave
  `SNOWFLAKE_PASSWORD=` empty)
- `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`
- `ACCESS_DB_PATH` and the feed dirs, if you use those sources

> Keep the `SNOWFLAKE_PASSWORD=` line even when empty — the config references it,
> so the line must exist (an empty value is fine for SSO).

---

## 3. Web app

```powershell
cd "Testing Orchestrator App"
copy .env.local.example .env.local
```

Open `.env.local` and set the **two paths for this machine**:

```
REPO_ROOT=C:\Users\<you>\OneDrive - Carlyle\Documents\Dev\etl_testing
PYTHON_EXE=C:\Users\<you>\OneDrive - Carlyle\Documents\Dev\etl_testing\.venv\Scripts\python.exe
```

(`.env.local` lives **inside** `Testing Orchestrator App/`, not the repo root, and
holds no secrets — just per-machine paths.)

Install deps and start the app:

```powershell
node scripts\install.js     # installs React + all app deps — this IS `npm install`, node-direct
node server.js              # http://localhost:3000
```

Do **not** run `npm install` separately — `node scripts\install.js` already does
it the node-direct way, avoiding the blocked `npm.cmd` shim.

Open **http://localhost:3000**.

---

## 4. Snowflake SSO — how it works

SSO is already wired into `config/connections.yaml`: every Snowflake connection
uses `authenticator: ${SNOWFLAKE_AUTHENTICATOR:-externalbrowser}`, so with the
default `.env` you get external-browser SSO across all of them — **no per-connection
edit needed**.

- The **first** run that hits Snowflake opens a browser window for SSO login. The
  token is then cached (via `secure-local-storage`), so it won't prompt every time.
- To switch a machine back to **password auth**, set `SNOWFLAKE_AUTHENTICATOR=`
  (empty) in `.env` and fill `SNOWFLAKE_PASSWORD`.

You do **not** need to touch the app's Connections page for SSO — the default
already covers it. (You *can* edit a single connection there if ever needed; the
app writes to the same `connections.yaml`.)

---

## 5. Smoke test (no credentials needed)

Verify the install works end-to-end against the bundled offline demo:

```powershell
# From the repo root
.\.venv\Scripts\python.exe -m etl_test.cli run --suite samples/demo_suite.yaml
```

Or in the app: open http://localhost:3000 → **New run** → pick `demo` → **Run**.
A run that lands on the Command Center means the app ↔ Python bridge works.

---

## Quick reference — full command list

```powershell
# --- prerequisites: Python 3.11+, Node LTS, (Access ODBC driver if needed) ---

# Python engine + connectors
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[connectors]"
copy .env.example .env            # fill SNOWFLAKE_ACCOUNT/USER, keep authenticator=externalbrowser

# Web app
cd "Testing Orchestrator App"
copy .env.local.example .env.local  # set REPO_ROOT + PYTHON_EXE
node scripts\install.js
node server.js                    # http://localhost:3000
```
