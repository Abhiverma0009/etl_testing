"""Validator base class + shared data-loading helpers.

A :class:`ValidationContext` carries the source/target connectors, the parsed
mapping, the evidence directory, and free-form options (thresholds, baselines).

Validators implement :meth:`Validator.validate` and return a list of
``CheckResult``. The base class wraps each table iteration so an exception in one
table becomes a single ERROR check rather than aborting the whole category.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..connectors.base import Connector, Dataset
from ..core.result import Category, CheckResult, Severity, Status
from ..mapping.models import MappingBook, TableMapping

log = logging.getLogger(__name__)


@dataclass
class ValidationContext:
    target: Connector
    mapping: MappingBook
    evidence_dir: Path
    source: Connector | None = None
    options: dict[str, Any] = field(default_factory=dict)
    # extra named connectors (e.g. baselines, report extracts, second source)
    extra: dict[str, Connector] = field(default_factory=dict)
    # optional callable(name) -> Connector, used by config-driven validators to
    # open additional named connections from connections.yaml on demand.
    resolver: Any = None

    def opt(self, key: str, default: Any = None) -> Any:
        return self.options.get(key, default)

    def connector(self, name: str) -> Connector:
        """Resolve a named connector (from ``extra`` or via ``resolver``)."""
        if name in self.extra:
            return self.extra[name]
        if self.resolver is not None:
            conn = self.resolver(name)
            self.extra[name] = conn  # cache
            return conn
        raise KeyError(
            f"Connector {name!r} is not available. Provide it via connections.yaml "
            f"so config-driven validators can open it."
        )


class Validator:
    category: Category = None  # type: ignore[assignment]

    def __init__(self, ctx: ValidationContext):
        self.ctx = ctx

    # Subclasses override this.
    def validate(self, tables: list[TableMapping]) -> list[CheckResult]:
        raise NotImplementedError

    # --- helpers shared by subclasses --------------------------------------------
    def _check(self, name: str, table: str | None = None,
               severity: Severity = Severity.P3, **kw: Any) -> CheckResult:
        return CheckResult(name=name, category=self.category.value,
                           target_table=table, severity=severity, **kw)

    def load_target(self, table: TableMapping, columns: list[str] | None = None,
                    where: str | None = None) -> pd.DataFrame:
        opts = dict(table.options.get("target_options") or {})
        # A target that is a file/Excel object can name its path here.
        tgt_object = opts.pop("object", None) or table.fq_target() or table.target_table
        ds = Dataset(name=table.target_table, table=tgt_object,
                     columns=columns, where=where or table.options.get("target_where"),
                     options=opts)
        return self.ctx.target.fetch_dataframe(ds)

    def load_source(self, table: TableMapping, columns: list[str] | None = None,
                    where: str | None = None) -> pd.DataFrame | None:
        """Load the source side and rename source columns to target names.

        Returns None if the table has no source connector / source_object (e.g. a
        target-only table), so source-dependent validators can SKIP cleanly.
        """
        if self.ctx.source is None or not table.source_object:
            return None
        opts = dict(table.options.get("source_options") or {})
        # For file sources: options may carry {path: "GC_*.xlsx", sheet: [...]}.
        # source_object stays the logical name / default path.
        src_object = opts.pop("object", None) or table.source_object
        ds = Dataset(name=table.source_object, table=src_object,
                     columns=columns, where=where or table.options.get("source_where"),
                     options=opts)
        df = self.ctx.source.fetch_dataframe(ds)
        rename = {src: tgt for src, tgt in table.source_to_target().items()
                  if src in df.columns}
        if rename:
            df = df.rename(columns=rename)
        return df

    def run_safely(self, tables: list[TableMapping]) -> list[CheckResult]:
        """Entry point used by the runner. Never raises."""
        results: list[CheckResult] = []
        try:
            results = self.validate(tables)
        except Exception as exc:  # noqa: BLE001
            log.exception("Validator %s crashed", self.category.value)
            results.append(CheckResult.error(
                name=f"{self.category.value} (category-level failure)",
                category=self.category.value,
                message=f"Validator raised an unexpected error: {exc}",
            ))
        return results

    @staticmethod
    def _timed():
        return time.perf_counter()


def timed_check(fn):
    """Decorator: time a method returning a CheckResult and set duration_s."""
    def wrapper(self, *args, **kwargs):
        t0 = time.perf_counter()
        result = fn(self, *args, **kwargs)
        if isinstance(result, CheckResult):
            result.duration_s = round(time.perf_counter() - t0, 4)
        return result
    return wrapper
