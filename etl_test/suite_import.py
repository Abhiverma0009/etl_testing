"""Import test cases (suites) and scenarios from an Excel workbook.

Lets a QA lead prepare test cases in Excel and load them into the app in one
shot. Mirrors ``export-mapping``: the app uploads a workbook and shells out to
``etl-test import-suites``; this module does the parsing and file writing so the
Node app needs no Excel library.

Workbook sheets (case-insensitive names, extra columns ignored)
---------------------------------------------------------------
TestCases (required) — one row per test case (suite):
    name       (required)  unique test-case name -> config/suites/<name>.yaml
    scenario               scenario id or display name to group under
    source                 source connection name (blank = none)
    target     (required)  target connection name
    mapping                mapping name (must already exist under config/mappings)
    tests                  comma/;/| list of test categories (blank = all)
    reports                comma/;/| list of report ids (for report test cases)
    options                JSON object of run options, e.g. {"variance_threshold": 0.0001}
    tables                 JSON array of per-table options

Scenarios (optional) — one row per scenario:
    id         (required)  scenario id (short key)
    name                   display name
    description            free text

Connections and mappings are referenced by name and must already exist; unknown
references are reported as warnings (the suite is still written so it can be
fixed later). Scenarios referenced by a test case but not otherwise defined are
auto-created.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from .config_loader import Connections
from .exceptions import EtlTestError
from .mapping.excel_parser import _norm, _read_sheet, _Row
from .validators import all_categories

SHEET_ALIASES = {
    "testcases": ["testcases", "test cases", "suites", "suite", "cases", "test case"],
    "scenarios": ["scenarios", "scenario"],
}

_SCENARIOS_HEADER = (
    "# Test scenarios — the top level of QA planning. Each scenario groups\n"
    "# multiple test cases (suites in config/suites/*.yaml, tagged with\n"
    "# `scenario: <id>`). Managed in the app and by `etl-test import-suites`.\n"
)


def _find_sheet(xls: pd.ExcelFile, logical: str) -> str | None:
    wanted = {_norm(a) for a in SHEET_ALIASES[logical]}
    for sheet in xls.sheet_names:
        if _norm(sheet) in wanted:
            return sheet
    return None


def _split_list(v: Any) -> list[str]:
    if v is None:
        return []
    return [part.strip() for part in re.split(r"[,;|]", str(v)) if part.strip()]


def _slug(s: str) -> str:
    out = re.sub(r"[^A-Za-z0-9]+", "_", str(s).strip().lower()).strip("_")
    return out or "scenario"


def _safe_name(s: str) -> str:
    """Filename-safe test-case name (the suite file stem)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s).strip()).strip("._-")


def _parse_json_cell(raw: Any, kind: str, name: str, warnings: list[str]):
    """Parse an options JSON cell; warn and fall back on bad JSON."""
    default = {} if kind == "object" else []
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        val = json.loads(str(raw))
    except Exception:
        warnings.append(f"{name}: '{kind}' cell is not valid JSON — ignored.")
        return default
    if kind == "object" and not isinstance(val, dict):
        warnings.append(f"{name}: 'options' must be a JSON object — ignored.")
        return {}
    return val


def _parse_tables_cell(raw: Any, name: str, warnings: list[str]) -> list:
    """The 'tables' cell scopes a test case to specific target tables. Accepts
    either a simple comma/;/|-separated list of table names (the common case,
    e.g. a target-only format check on one table) OR a JSON array for advanced
    per-table options (e.g. [{"name": "T", "options": {...}}])."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return []
    if isinstance(raw, list):
        return raw
    s = str(raw).strip()
    if s.startswith("["):
        try:
            val = json.loads(s)
        except Exception:
            warnings.append(f"{name}: 'tables' JSON is invalid — ignored.")
            return []
        if not isinstance(val, list):
            warnings.append(f"{name}: 'tables' JSON must be an array — ignored.")
            return []
        return val
    return _split_list(s)  # plain "TABLE_A, TABLE_B" -> ["TABLE_A", "TABLE_B"]


def _resolve_mapping(name: str, mappings_dir: Path) -> str | None:
    """Prefer the live Excel workbook, then the exported JSON. Returns a repo-
    relative path or None if neither exists."""
    for ext in ("xlsx", "xlsm", "json"):
        if (mappings_dir / f"{name}.{ext}").exists():
            return f"config/mappings/{name}.{ext}"
    return None


def import_suites(
    xlsx_path: str | Path,
    *,
    suites_dir: str = "config/suites",
    scenarios_path: str = "config/scenarios.yaml",
    connections_path: str = "config/connections.yaml",
    mappings_dir: str = "config/mappings",
) -> dict:
    p = Path(xlsx_path)
    if not p.exists():
        raise EtlTestError(f"Workbook not found: {p}")
    try:
        xls = pd.ExcelFile(p)
    except Exception as exc:  # noqa: BLE001
        raise EtlTestError(f"Could not open workbook {p}: {exc}") from exc

    tc_sheet = _find_sheet(xls, "testcases")
    if not tc_sheet:
        raise EtlTestError(
            "No 'TestCases' sheet found. Expected a sheet named TestCases "
            f"(or Suites). Sheets present: {xls.sheet_names}")

    warnings: list[str] = []
    suites_dirp = Path(suites_dir)
    mappings_dirp = Path(mappings_dir)
    suites_dirp.mkdir(parents=True, exist_ok=True)

    # Known connection names (for reference validation only — never fatal).
    known_conns: set[str] = set()
    try:
        known_conns = set(Connections.from_file(connections_path).names())
    except Exception:
        warnings.append(f"Could not read {connections_path}; skipped connection checks.")

    # ---- scenarios: existing file + optional Scenarios sheet ----
    scenarios: dict[str, dict] = {}
    scen_file = Path(scenarios_path)
    if scen_file.exists():
        try:
            doc = yaml.safe_load(scen_file.read_text(encoding="utf-8")) or {}
            scenarios = dict(doc.get("scenarios") or {})
        except Exception:
            warnings.append(f"Could not parse {scenarios_path}; starting fresh.")

    # Snapshot so we can tell whether anything actually changed (and which ids
    # are brand new) regardless of whether the change came from the Scenarios
    # sheet or from auto-creating a referenced scenario.
    original_scenarios = json.loads(json.dumps(scenarios))
    pre_ids = set(scenarios)

    scen_sheet = _find_sheet(xls, "scenarios")
    if scen_sheet:
        for _, row in _read_sheet(xls, scen_sheet).iterrows():
            r = _Row(row)
            sid = r.get("id", "scenario_id")
            if not sid:
                continue
            sid = _slug(sid)
            entry: dict[str, Any] = {}
            nm = r.get("name")
            desc = r.get("description", "desc")
            if nm:
                entry["name"] = str(nm)
            if desc:
                entry["description"] = str(desc)
            scenarios[sid] = {**scenarios.get(sid, {}), **entry}

    id_set = set(scenarios)
    name_to_id = {str(v.get("name", "")).lower(): k for k, v in scenarios.items() if v.get("name")}

    def resolve_scenario(value: Any) -> str | None:
        if not value or not str(value).strip():
            return None
        v = str(value).strip()
        if v in id_set:
            return v
        if v.lower() in name_to_id:
            return name_to_id[v.lower()]
        new_id = _slug(v)
        base, i = new_id, 2
        while new_id in id_set:
            new_id = f"{base}_{i}"; i += 1
        scenarios[new_id] = {"name": v}
        id_set.add(new_id)
        name_to_id[v.lower()] = new_id
        return new_id

    # ---- test cases ----
    valid_categories = set(all_categories())
    created: list[str] = []
    updated: list[str] = []
    seen: set[str] = set()

    for _, row in _read_sheet(xls, tc_sheet).iterrows():
        r = _Row(row)
        raw_name = r.get("name", "test case", "case", "suite")
        if not raw_name:
            continue
        name = _safe_name(raw_name)
        if not name:
            warnings.append(f"Row with name '{raw_name}' produced an empty name — skipped.")
            continue
        if name in seen:
            warnings.append(f"Duplicate test case '{name}' in sheet — later row wins.")
        seen.add(name)

        target = r.get("target")
        if not target:
            warnings.append(f"{name}: no 'target' — skipped (target connection is required).")
            continue
        target = str(target).strip()
        if known_conns and target not in known_conns:
            warnings.append(f"{name}: target '{target}' is not a known connection.")

        source = r.get("source")
        source = str(source).strip() if source else None
        if source and known_conns and source not in known_conns:
            warnings.append(f"{name}: source '{source}' is not a known connection.")

        # tests categories (validate; drop unknown)
        tests = []
        for t in _split_list(r.get("tests", "test", "categories")):
            if t in valid_categories:
                tests.append(t)
            else:
                warnings.append(f"{name}: unknown test category '{t}' — dropped.")

        reports = _split_list(r.get("reports", "report"))
        options = _parse_json_cell(r.get("options"), "object", name, warnings)
        tables = _parse_tables_cell(r.get("tables"), name, warnings)

        mapping_path = None
        map_name = r.get("mapping")
        if map_name:
            map_name = str(map_name).strip()
            # accept a bare name or an already-qualified path
            bare = re.sub(r"^config/mappings/", "", map_name)
            bare = re.sub(r"\.(xlsx|xlsm|json)$", "", bare, flags=re.I)
            mapping_path = _resolve_mapping(bare, mappings_dirp)
            if not mapping_path:
                warnings.append(f"{name}: mapping '{map_name}' not found under config/mappings.")

        scenario_id = resolve_scenario(r.get("scenario", "test scenario"))

        exp = r.get("expected", "expected result", "expected_outcome")
        is_negative = bool(exp) and str(exp).strip().lower() in (
            "fail", "negative", "neg", "true", "1", "yes")

        # Build the suite doc (no 'name' key — the filename is the name), in a
        # readable, native-looking key order; omit empties.
        doc: dict[str, Any] = {}
        if scenario_id:
            doc["scenario"] = scenario_id
        doc["connections"] = connections_path
        if mapping_path:
            doc["mapping"] = mapping_path
        if source:
            doc["source"] = source
        doc["target"] = target
        if is_negative:
            doc["expected"] = "fail"
        if options:
            doc["options"] = options
        if tests:
            doc["tests"] = tests
        if tables:
            doc["tables"] = tables
        if reports:
            doc["reports"] = reports

        out_path = suites_dirp / f"{name}.yaml"
        existed = out_path.exists()
        out_path.write_text(
            yaml.safe_dump(doc, sort_keys=False, default_flow_style=False, allow_unicode=True),
            encoding="utf-8")
        (updated if existed else created).append(name)

    # ---- persist scenarios if the set changed (sheet-defined or auto-created) ----
    scenarios_created = [i for i in scenarios if i not in pre_ids]
    if scenarios != original_scenarios:
        scen_file.parent.mkdir(parents=True, exist_ok=True)
        body = yaml.safe_dump({"scenarios": scenarios}, sort_keys=False, allow_unicode=True)
        scen_file.write_text(_SCENARIOS_HEADER + body, encoding="utf-8")

    return {
        "created_suites": created,
        "updated_suites": updated,
        "scenarios_created": scenarios_created,
        "warnings": warnings,
        "count": len(created) + len(updated),
    }
