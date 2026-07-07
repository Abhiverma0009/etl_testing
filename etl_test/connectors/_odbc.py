"""Shared base for ODBC connectors (MS Access and SQL Server) using pyodbc.

Handles connect/retry, identifier quoting with ``[brackets]`` (valid for both
Access and SQL Server), efficient COUNT and column introspection, and chunked
fetch into pandas.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..exceptions import ConnectorError, MissingDriverError
from .base import Connector, Dataset

log = logging.getLogger(__name__)

try:
    import pyodbc  # type: ignore
except Exception:  # pragma: no cover - import guarded so the package loads without it
    pyodbc = None


def _require_pyodbc() -> None:
    if pyodbc is None:
        raise MissingDriverError(
            "pyodbc is not installed. Run: pip install pyodbc "
            "(and ensure the matching ODBC driver is installed on this machine)."
        )


def quote_ident(name: str) -> str:
    """Quote an identifier for Access/SQL Server. Escapes embedded brackets."""
    return "[" + name.replace("]", "]]") + "]"


class OdbcConnector(Connector):
    """Common pyodbc behaviour. Subclasses supply the connection string."""

    def _connection_string(self) -> str:  # pragma: no cover - abstract-ish
        raise NotImplementedError

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(ConnectorError),
    )
    def _connect(self) -> Any:
        _require_pyodbc()
        conn_str = self._connection_string()
        try:
            conn = pyodbc.connect(conn_str, timeout=int(self.config.get("timeout", 30)))
        except pyodbc.Error as exc:  # noqa
            # Surface a friendly message for the common "driver not found" case.
            msg = str(exc)
            if "IM002" in msg or "Data source name not found" in msg:
                raise ConnectorError(
                    f"[{self.name}] ODBC driver not found. Installed drivers: "
                    f"{pyodbc.drivers()}. Check the 'driver' in connections.yaml."
                ) from exc
            raise ConnectorError(f"[{self.name}] ODBC connect failed: {msg}") from exc
        return conn

    def _probe(self) -> bool:
        cur = self._conn.cursor()
        try:
            cur.execute(self._probe_sql())
            cur.fetchone()
            return True
        finally:
            cur.close()

    def _probe_sql(self) -> str:
        return "SELECT 1"

    # --- query building -----------------------------------------------------------
    def _base_query(self, ds: Dataset, select: str | None = None) -> str:
        if ds.query:
            return ds.query
        if not ds.table:
            raise ConnectorError(
                f"[{self.name}] dataset {ds.name!r} has neither 'table' nor 'query'."
            )
        cols = select or (
            ", ".join(quote_ident(c) for c in ds.columns) if ds.columns else "*"
        )
        sql = f"SELECT {cols} FROM {self._qualify(ds.table)}"
        if ds.where:
            sql += f" WHERE {ds.where}"
        return sql

    def _qualify(self, table: str) -> str:
        # Allow already-qualified names (schema.table); quote each part.
        parts = [p for p in table.replace("[", "").replace("]", "").split(".") if p]
        return ".".join(quote_ident(p) for p in parts)

    def _fetch(self, ds: Dataset) -> pd.DataFrame:
        sql = self._base_query(ds)
        # Use a fresh cursor and build a DataFrame from rows to control dtypes and
        # avoid pandas' SQLAlchemy dependency for raw pyodbc connections.
        cur = self._conn.cursor()
        try:
            cur.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
        finally:
            cur.close()
        if not columns:
            return pd.DataFrame()
        data = [tuple(r) for r in rows]
        return pd.DataFrame.from_records(data, columns=columns)

    def _row_count(self, ds: Dataset) -> int:
        if ds.query:
            # Wrap arbitrary query as a subselect.
            sql = f"SELECT COUNT(*) FROM ({ds.query}) AS _sub"
        else:
            sql = f"SELECT COUNT(*) FROM {self._qualify(ds.table)}"
            if ds.where:
                sql += f" WHERE {ds.where}"
        cur = self._conn.cursor()
        try:
            cur.execute(sql)
            return int(cur.fetchone()[0])
        finally:
            cur.close()

    def _columns(self, ds: Dataset) -> list[str]:
        # Fetch the cheapest possible result to read description.
        if ds.query:
            sql = ds.query
        else:
            sql = f"SELECT * FROM {self._qualify(ds.table)} WHERE 1=0"
        cur = self._conn.cursor()
        try:
            cur.execute(sql)
            return [d[0] for d in cur.description] if cur.description else []
        finally:
            cur.close()
