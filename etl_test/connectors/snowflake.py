"""Snowflake connector (target EDP) via snowflake-connector-python.

Supports password and key-pair auth. Uses ``fetch_pandas_all`` when available
(fast, arrow-based) and falls back to row fetch otherwise. Identifier quoting
uses double quotes; unquoted Snowflake identifiers are upper-cased by the server,
so we quote what the caller gives us to preserve case from the mapping doc.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..exceptions import ConnectorError, MissingDriverError
from .base import Connector, Dataset

log = logging.getLogger(__name__)

try:
    import snowflake.connector as sf  # type: ignore
except Exception:  # pragma: no cover
    sf = None


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class SnowflakeConnector(Connector):
    type_name = "snowflake"

    def _connect(self) -> Any:
        if sf is None:
            raise MissingDriverError(
                "snowflake-connector-python is not installed. "
                "Run: pip install snowflake-connector-python pyarrow"
            )
        return self._connect_retrying()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(ConnectorError),
    )
    def _connect_retrying(self) -> Any:
        cfg = self.config
        params: dict[str, Any] = {
            "account": cfg.get("account"),
            "user": cfg.get("user"),
            "role": cfg.get("role"),
            "warehouse": cfg.get("warehouse"),
            "database": cfg.get("database"),
            "schema": cfg.get("schema"),
            "login_timeout": int(cfg.get("login_timeout", 30)),
            "network_timeout": int(cfg.get("network_timeout", 60)),
        }
        if not params["account"] or not params["user"]:
            raise ConnectorError(
                f"[{self.name}] Snowflake requires at least 'account' and 'user'."
            )

        # Auth precedence: explicit authenticator (SSO/OAuth) > key-pair > password.
        authenticator = cfg.get("authenticator")
        key_path = cfg.get("private_key_path")
        if authenticator:
            params["authenticator"] = authenticator
            # External-browser SSO is interactive; cache the token so a browser
            # prompt isn't triggered on every single connection.
            if str(authenticator).lower() == "externalbrowser":
                params["client_store_temporary_credential"] = True
            # OAuth / programmatic access-token flows pass a token instead of a password.
            token = cfg.get("token")
            if token:
                params["token"] = token
        elif key_path:
            params["private_key"] = self._load_private_key(key_path,
                                                           cfg.get("private_key_passphrase"))
        else:
            pwd = cfg.get("password")
            if not pwd:
                raise ConnectorError(
                    f"[{self.name}] Snowflake needs a 'password', 'private_key_path', "
                    "or 'authenticator' (use 'externalbrowser' for SSO)."
                )
            params["password"] = pwd

        params = {k: v for k, v in params.items() if v is not None}
        try:
            return sf.connect(**params)
        except Exception as exc:  # noqa: BLE001
            raise ConnectorError(f"[{self.name}] Snowflake connect failed: {exc}") from exc

    @staticmethod
    def _load_private_key(path: str, passphrase: str | None) -> bytes:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        data = Path(path).read_bytes()
        pkey = serialization.load_pem_private_key(
            data,
            password=passphrase.encode() if passphrase else None,
            backend=default_backend(),
        )
        return pkey.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def _probe(self) -> bool:
        cur = self._conn.cursor()
        try:
            cur.execute("SELECT 1")
            cur.fetchone()
            return True
        finally:
            cur.close()

    # --- query building -----------------------------------------------------------
    def _qualify(self, table: str) -> str:
        parts = [p for p in table.split(".") if p]
        return ".".join(_quote(p.strip('"')) for p in parts)

    def _base_query(self, ds: Dataset) -> str:
        if ds.query:
            return ds.query
        if not ds.table:
            raise ConnectorError(
                f"[{self.name}] dataset {ds.name!r} has neither 'table' nor 'query'."
            )
        cols = ", ".join(_quote(c) for c in ds.columns) if ds.columns else "*"
        sql = f"SELECT {cols} FROM {self._qualify(ds.table)}"
        if ds.where:
            sql += f" WHERE {ds.where}"
        return sql

    def _fetch(self, ds: Dataset) -> pd.DataFrame:
        cur = self._conn.cursor()
        try:
            cur.execute(self._base_query(ds))
            if hasattr(cur, "fetch_pandas_all"):
                try:
                    return cur.fetch_pandas_all()
                except Exception:  # noqa: BLE001 - arrow not available for this result
                    log.debug("[%s] fetch_pandas_all failed; falling back", self.name)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
            return pd.DataFrame.from_records(list(rows), columns=columns)
        finally:
            cur.close()

    def _row_count(self, ds: Dataset) -> int:
        if ds.query:
            sql = f"SELECT COUNT(*) FROM ({ds.query})"
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
        sql = ds.query if ds.query else f"SELECT * FROM {self._qualify(ds.table)} LIMIT 0"
        cur = self._conn.cursor()
        try:
            cur.execute(sql)
            return [d[0] for d in cur.description] if cur.description else []
        finally:
            cur.close()
