"""SQLite connector.

Primarily for offline demos and unit tests (a stand-in for a real SQL source so
the framework can be exercised end-to-end without Access/Snowflake). Uses the
stdlib ``sqlite3`` module, so it has no extra dependencies.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from ..exceptions import ConnectorError
from .base import Connector, Dataset


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class SqliteConnector(Connector):
    type_name = "sqlite"

    def _connect(self) -> Any:
        path = self.config.get("path") or self.config.get("database")
        if not path:
            raise ConnectorError(f"[{self.name}] sqlite connection requires 'path'.")
        if path != ":memory:" and not Path(path).exists():
            raise ConnectorError(f"[{self.name}] sqlite file not found: {path}")
        return sqlite3.connect(path)

    def _base_query(self, ds: Dataset) -> str:
        if ds.query:
            return ds.query
        if not ds.table:
            raise ConnectorError(f"[{self.name}] dataset {ds.name!r} needs 'table' or 'query'.")
        cols = ", ".join(_quote(c) for c in ds.columns) if ds.columns else "*"
        sql = f"SELECT {cols} FROM {_quote(ds.table)}"
        if ds.where:
            sql += f" WHERE {ds.where}"
        return sql

    def _fetch(self, ds: Dataset) -> pd.DataFrame:
        return pd.read_sql_query(self._base_query(ds), self._conn)

    def _row_count(self, ds: Dataset) -> int:
        if ds.query:
            sql = f"SELECT COUNT(*) FROM ({ds.query})"
        else:
            sql = f"SELECT COUNT(*) FROM {_quote(ds.table)}"
            if ds.where:
                sql += f" WHERE {ds.where}"
        cur = self._conn.execute(sql)
        return int(cur.fetchone()[0])

    def _columns(self, ds: Dataset) -> list[str]:
        sql = ds.query if ds.query else f"SELECT * FROM {_quote(ds.table)} LIMIT 0"
        cur = self._conn.execute(sql)
        return [d[0] for d in cur.description] if cur.description else []

    def _probe(self) -> bool:
        self._conn.execute("SELECT 1").fetchone()
        return True
