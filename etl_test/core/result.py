"""Result model shared by every validator.

A run produces one :class:`TestRunResult` holding many :class:`CheckResult`s.
Everything is JSON-serialisable so results can be persisted and fed to the HTML
reporter or a CI gate.

Status vs severity:
  * ``status`` is the outcome of the check (PASS/FAIL/WARN/ERROR).
  * ``severity`` is the business impact *if it fails* (P1..P4), taken from the
    mapping/suite. A WARN with P1 severity still warrants attention; a FAIL with
    P4 may be tolerable. The reporter surfaces both.
"""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    ERROR = "ERROR"  # the check itself blew up (connection, bad config, bug)
    SKIPPED = "SKIPPED"


class Severity(str, Enum):
    P1 = "P1"  # Showstopper
    P2 = "P2"  # Critical
    P3 = "P3"  # Major
    P4 = "P4"  # Medium

    @classmethod
    def coerce(cls, value: Any, default: "Severity" = None) -> "Severity":
        default = default or cls.P3
        if value is None:
            return default
        if isinstance(value, cls):
            return value
        text = str(value).strip().upper().replace("-", "").replace(" ", "")
        # Accept "P1", "1", "SHOWSTOPPER", etc.
        aliases = {
            "P1": cls.P1, "1": cls.P1, "SHOWSTOPPER": cls.P1, "CRITICALBLOCKER": cls.P1,
            "P2": cls.P2, "2": cls.P2, "CRITICAL": cls.P2,
            "P3": cls.P3, "3": cls.P3, "MAJOR": cls.P3,
            "P4": cls.P4, "4": cls.P4, "MEDIUM": cls.P4, "MINOR": cls.P4,
        }
        return aliases.get(text, default)


# Stable category identifiers (one per validator). Used for grouping in the
# dashboard and for the ``--tests`` CLI filter.
class Category(str, Enum):
    ROW_COUNT = "row_count"
    SCHEMA = "schema"
    DATATYPE = "datatype"
    COMPLETENESS = "completeness"
    BUSINESS_RULES = "business_rules"
    REFERENTIAL_INTEGRITY = "referential_integrity"
    TRANSFORMATION = "transformation"
    HISTORICAL = "historical"
    DEDUPLICATION = "deduplication"
    NULL_HANDLING = "null_handling"
    RECONCILIATION = "reconciliation"
    LINEAGE = "lineage"
    INCREMENTAL = "incremental"
    CROSS_SOURCE = "cross_source"
    REPORT = "report"
    GVC_REPORT = "gvc_report"  # legacy alias of REPORT (kept for old suites)


@dataclass
class Evidence:
    """A pointer to a saved evidence file (CSV/JSON) plus a short label."""
    label: str
    path: str
    rows: int | None = None


@dataclass
class CheckResult:
    """Outcome of a single check within a category."""
    name: str
    category: str
    status: Status = Status.PASS
    severity: Severity = Severity.P3
    target_table: str | None = None
    message: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    # Small inline sample (capped) shown directly in the dashboard.
    sample: list[dict[str, Any]] = field(default_factory=list)
    sample_columns: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    duration_s: float = 0.0
    rule_id: str | None = None
    use_case: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["severity"] = self.severity.value
        return d

    # --- convenience constructors -------------------------------------------------
    @classmethod
    def error(cls, name: str, category: str, message: str,
              target_table: str | None = None,
              severity: Severity = Severity.P1, **kw: Any) -> "CheckResult":
        return cls(name=name, category=category, status=Status.ERROR,
                   severity=severity, target_table=target_table,
                   message=message, **kw)


@dataclass
class TestRunResult:
    """A whole run: metadata + all check results."""
    run_id: str
    started_at: str
    category: str | None = None          # set when a run targets a single category
    suite: str | None = None
    source: str | None = None
    target: str | None = None
    mapping_file: str | None = None
    checks: list[CheckResult] = field(default_factory=list)
    finished_at: str | None = None
    host: str = field(default_factory=platform.node)
    meta: dict[str, Any] = field(default_factory=dict)

    # --- aggregates ---------------------------------------------------------------
    def add(self, check: CheckResult) -> CheckResult:
        self.checks.append(check)
        return check

    def counts(self) -> dict[str, int]:
        c = {s.value: 0 for s in Status}
        for chk in self.checks:
            c[chk.status.value] += 1
        c["TOTAL"] = len(self.checks)
        return c

    @property
    def passed(self) -> bool:
        """A run passes only if no FAIL and no ERROR checks exist."""
        return not any(
            chk.status in (Status.FAIL, Status.ERROR) for chk in self.checks
        )

    def exit_code(self) -> int:
        if any(c.status == Status.ERROR for c in self.checks):
            return 2
        if any(c.status == Status.FAIL for c in self.checks):
            return 1
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "category": self.category,
            "suite": self.suite,
            "source": self.source,
            "target": self.target,
            "mapping_file": self.mapping_file,
            "host": self.host,
            "meta": self.meta,
            "counts": self.counts(),
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
        }

    def save_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str),
                        encoding="utf-8")
        return path


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
