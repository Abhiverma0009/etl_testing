"""Run orchestration.

Builds a :class:`ValidationContext`, executes the requested validator categories
over the selected tables, isolates failures per category, persists JSON results,
and refreshes the run manifest.

Optionally emits newline-delimited JSON progress events to **stdout** (gated by
the ``ETL_TEST_PROGRESS_JSON=1`` env var) so a parent process — e.g. the Next.js
app spawning this CLI — can stream live progress. Logging goes to stderr, so the
two streams never interleave. Standalone/CI use is unaffected (nothing prints
unless the env var is set).
"""

from __future__ import annotations

import json as _json
import logging
import os
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from ..config_loader import Connections
from ..connectors.base import Connector
from ..connectors.factory import make_connector
from ..mapping.models import MappingBook, TableMapping
from ..reporting import build_manifest
from .result import CheckResult, TestRunResult, new_run_id, utcnow_iso

log = logging.getLogger(__name__)


def _emit(event: dict) -> None:
    """Print a progress event as one JSON line when progress streaming is enabled."""
    if os.environ.get("ETL_TEST_PROGRESS_JSON") != "1":
        return
    try:
        print(_json.dumps(event, default=str), flush=True)
    except Exception:  # pragma: no cover - never let progress emission break a run
        pass


def select_tables(mapping: MappingBook, names: Iterable[str] | None) -> list[TableMapping]:
    if not names:
        return mapping.active_tables()
    wanted = {n.strip() for n in names}
    selected = [t for t in mapping.tables.values() if t.target_table in wanted]
    found = {t.target_table for t in selected}
    missing = wanted - found
    if missing:
        log.warning("Requested tables not found in mapping (ignored): %s", sorted(missing))
    return selected


def run_validation(
    *,
    connections: Connections,
    mapping: MappingBook,
    categories: list[str],
    target_name: str,
    source_name: str | None,
    table_names: list[str] | None,
    options: dict[str, Any],
    output_dir: Path,
    suite_name: str | None = None,
) -> tuple[TestRunResult, Path]:
    from ..validators import VALIDATORS  # late import to avoid cycles

    run_id = new_run_id()
    output_dir = Path(output_dir)
    run_dir = output_dir / "runs" / run_id
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    run = TestRunResult(
        run_id=run_id, started_at=utcnow_iso(), suite=suite_name,
        source=source_name, target=target_name, mapping_file=mapping.source_file,
        meta={"categories": categories, "tables": table_names or "ALL",
              "mapping_warnings": mapping.warnings},
    )

    # Connector cache + resolver for config-driven validators.
    cache: dict[str, Connector] = {}

    def resolve(name: str) -> Connector:
        if name not in cache:
            cache[name] = make_connector(connections.get(name))
        return cache[name]

    target = resolve(target_name)
    source = resolve(source_name) if source_name else None

    tables = select_tables(mapping, table_names)
    # Report validators operate on their own query pairs, not mapping tables, so a
    # report-only run legitimately has no tables. Only flag the empty selection
    # when a table-driven category was requested.
    TABLELESS = {"report", "gvc_report"}
    if not tables and (set(categories) - TABLELESS):
        run.add(CheckResult.error(
            "No tables selected", "row_count",
            "No active tables matched the selection; nothing to validate."))

    from ..validators.base import ValidationContext
    ctx = ValidationContext(
        target=target, mapping=mapping, evidence_dir=evidence_dir,
        source=source, options=options, resolver=resolve,
    )

    _emit({"event": "run_start", "run_id": run_id, "categories": list(categories),
           "tables": [t.target_table for t in tables],
           "source": source_name, "target": target_name, "suite": suite_name})

    try:
        for cat in categories:
            vcls = VALIDATORS.get(cat)
            if vcls is None:
                run.add(CheckResult.error(f"Unknown category {cat}", cat,
                                          f"No validator registered for {cat!r}."))
                _emit({"event": "category_complete", "run_id": run_id,
                       "category": cat, "counts": {"ERROR": 1}, "checks": 1})
                continue
            log.info("Running validator: %s", cat)
            _emit({"event": "category_start", "run_id": run_id, "category": cat})
            validator = vcls(ctx)
            checks = validator.run_safely(tables)
            for chk in checks:
                run.add(chk)
            cc = Counter(c.status.value for c in checks)
            _emit({"event": "category_complete", "run_id": run_id, "category": cat,
                   "counts": dict(cc), "checks": len(checks)})
    finally:
        for conn in cache.values():
            conn.close()

    run.finished_at = utcnow_iso()

    # Make evidence paths relative to the run dir so links are portable
    # (resolved by the app as runs/<id>/evidence/<file>.csv).
    _relativize_evidence(run, run_dir)

    json_path = run_dir / "result.json"
    run.save_json(json_path)
    build_manifest(output_dir)                   # refresh the run index
    log.info("Results: %s", json_path)

    _emit({"event": "run_complete", "run_id": run_id, "result_path": str(json_path),
           "passed": run.passed, "counts": run.counts(), "exit_code": run.exit_code()})
    return run, json_path


def _relativize_evidence(run: TestRunResult, run_dir: Path) -> None:
    import os
    for chk in run.checks:
        for ev in chk.evidence:
            try:
                ev.path = os.path.relpath(ev.path, run_dir).replace("\\", "/")
            except (ValueError, TypeError):
                pass
