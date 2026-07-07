"""Connector abstraction.

Every source (Access, Snowflake, SQL Server, files) implements :class:`Connector`
so validators are source-agnostic. Connectors return pandas DataFrames.

Design notes / edge cases handled by subclasses:
  * Lazy connect: the underlying connection opens on first use and is reused.
  * Retries with backoff for transient connection/query failures (tenacity).
  * Chunked fetch with a configurable safety cap: if a table exceeds ``max_rows``
    the connector raises (or, when ``allow_truncation`` is set, warns and returns
    a capped sample) so we never silently OOM.
  * ``list_columns`` and ``get_row_count`` allow lightweight checks (schema, count)
    without pulling full data.
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

import pandas as pd

from ..exceptions import ConnectorError

log = logging.getLogger(__name__)

# Hard ceiling for in-memory pandas comparison. Configurable per connection.
DEFAULT_MAX_ROWS = 5_000_000


@dataclass
class Dataset:
    """A logical object to read from a connector.

    ``name`` is a table name, file path/glob, or a free-form label. Exactly one of
    ``table`` or ``query`` is used by the connector; ``query`` takes precedence.
    """
    name: str
    table: str | None = None
    query: str | None = None
    columns: list[str] | None = None
    where: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def label(self) -> str:
        return self.name or self.table or (self.query[:40] if self.query else "<dataset>")


class Connector(abc.ABC):
    """Base connector. Subclasses implement the private ``_`` methods."""

    type_name: str = "base"

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.name = config.get("name", self.type_name)
        self.max_rows = int(config.get("max_rows", DEFAULT_MAX_ROWS))
        self.allow_truncation = bool(config.get("allow_truncation", False))
        self._conn: Any = None

    # --- lifecycle ----------------------------------------------------------------
    def connect(self) -> None:
        if self._conn is None:
            try:
                self._conn = self._connect()
            except ConnectorError:
                raise
            except Exception as exc:  # noqa: BLE001 - wrap any driver error
                raise ConnectorError(
                    f"[{self.name}] failed to connect: {exc}"
                ) from exc

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._close()
            except Exception:  # pragma: no cover - best effort
                log.debug("[%s] error during close", self.name, exc_info=True)
            finally:
                self._conn = None

    def __enter__(self) -> "Connector":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- public API ---------------------------------------------------------------
    def test_connection(self) -> bool:
        """Open a connection and run a trivial probe. Raises on failure."""
        self.connect()
        return self._probe()

    def fetch_dataframe(self, ds: Dataset) -> pd.DataFrame:
        """Read a dataset into a DataFrame, enforcing the row cap."""
        self.connect()
        try:
            df = self._fetch(ds)
        except ConnectorError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ConnectorError(
                f"[{self.name}] failed to read {ds.label()!r}: {exc}"
            ) from exc

        if len(df) > self.max_rows:
            if self.allow_truncation:
                log.warning(
                    "[%s] %r returned %d rows > max_rows=%d; truncating "
                    "(allow_truncation=true). Results are a SAMPLE, not exhaustive.",
                    self.name, ds.label(), len(df), self.max_rows,
                )
                df = df.head(self.max_rows)
            else:
                raise ConnectorError(
                    f"[{self.name}] {ds.label()!r} returned {len(df):,} rows which exceeds "
                    f"max_rows={self.max_rows:,}. Increase max_rows for this connection, "
                    f"narrow with a 'where' filter, or set allow_truncation: true to sample."
                )
        return df

    def get_row_count(self, ds: Dataset) -> int:
        self.connect()
        try:
            return self._row_count(ds)
        except ConnectorError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ConnectorError(
                f"[{self.name}] failed to count {ds.label()!r}: {exc}"
            ) from exc

    def list_columns(self, ds: Dataset) -> list[str]:
        self.connect()
        try:
            return self._columns(ds)
        except ConnectorError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ConnectorError(
                f"[{self.name}] failed to list columns for {ds.label()!r}: {exc}"
            ) from exc

    # --- to be implemented by subclasses -----------------------------------------
    @abc.abstractmethod
    def _connect(self) -> Any: ...

    @abc.abstractmethod
    def _fetch(self, ds: Dataset) -> pd.DataFrame: ...

    def _close(self) -> None:
        if hasattr(self._conn, "close"):
            self._conn.close()

    def _probe(self) -> bool:
        # Default: assume connect() succeeding is enough. SQL connectors override.
        return True

    def _row_count(self, ds: Dataset) -> int:
        # Generic fallback: fetch and count. SQL connectors override for efficiency.
        return len(self._fetch(ds))

    def _columns(self, ds: Dataset) -> list[str]:
        # Generic fallback: read zero/one row. Subclasses may override.
        probe = Dataset(name=ds.name, table=ds.table, query=ds.query,
                        columns=ds.columns, where=ds.where, options=ds.options)
        df = self._fetch(probe)
        return list(df.columns)

    # --- helpers ------------------------------------------------------------------
    @staticmethod
    def _select_columns(columns: Iterable[str] | None) -> str:
        if not columns:
            return "*"
        return ", ".join(columns)
