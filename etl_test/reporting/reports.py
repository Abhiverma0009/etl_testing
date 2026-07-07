"""Report definition loading.

A report file (``config/reports/<id>.json``) describes one report (GVC, MD&A, …)
as a list of *tabs*, each a legacy-vs-new query pair::

  {
    "id": "gvc_q4_2025",
    "name": "GVC Reporting WB",
    "type": "GVC",
    "expected_connection": "access_valdb",     # per-report default (legacy side)
    "actual_connection":   "snowflake_gold",   # per-report default (new side)
    "tabs": [
      { "name": "Q01 - Fund Performance",
        "key_columns": ["FUND_CODE", "PERIOD"],
        "compare_columns": ["NAV", "IRR"],
        "measures": [ { "label": "Total NAV", "column": "NAV", "tolerance": 0.0001 } ],
        "actual":   { "query": "SELECT ... FROM GOLD...." },
        "expected": { "query": "SELECT ... FROM legacy Access ..." } }
    ]
  }

:func:`load_reports` flattens the tabs of the requested reports into the flat
"spec" list that :class:`etl_test.validators.report.ReportValidator` consumes
(one spec per tab), resolving each report's default connections onto any side
that doesn't name its own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_REPORTS_DIR = "config/reports"


def _resolve_side(spec: dict, *keys: str, default_conn: str | None) -> dict:
    """Return the side dict for the first present key, with a default connection."""
    side: dict = {}
    for k in keys:
        if spec.get(k):
            side = dict(spec[k])
            break
    if default_conn and "connection" not in side:
        side["connection"] = default_conn
    return side


def report_path(report_id: str, reports_dir: str | Path = DEFAULT_REPORTS_DIR) -> Path:
    """Path to a report file, accepting either an id or a direct .json path."""
    p = Path(report_id)
    if p.suffix == ".json":
        return p
    return Path(reports_dir) / f"{report_id}.json"


def load_report_file(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Report definition not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_report(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn one report dict into a list of per-tab validator specs."""
    report_id = data.get("id") or data.get("name") or "report"
    report_name = data.get("name", report_id)
    default_actual = data.get("actual_connection")
    default_expected = data.get("expected_connection")
    specs: list[dict[str, Any]] = []
    for tab in data.get("tabs", []):
        tab_name = tab.get("name", "?")
        spec = dict(tab)
        spec["name"] = f"{report_name} · {tab_name}"
        spec["report_id"] = report_id
        spec["report_name"] = report_name
        spec["tab"] = tab_name
        spec["actual"] = _resolve_side(tab, "actual", "report", default_conn=default_actual)
        spec["expected"] = _resolve_side(tab, "expected", "gold", default_conn=default_expected)
        specs.append(spec)
    return specs


def load_reports(ids: list[str], reports_dir: str | Path = DEFAULT_REPORTS_DIR
                 ) -> list[dict[str, Any]]:
    """Load & flatten the given report ids into a single list of tab specs."""
    specs: list[dict[str, Any]] = []
    for rid in ids or []:
        specs.extend(flatten_report(load_report_file(report_path(rid, reports_dir))))
    return specs
