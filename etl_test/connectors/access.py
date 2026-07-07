"""MS Access connector (legacy Val DB) via pyodbc + the Access ODBC driver.

Requires the "Microsoft Access Driver (*.mdb, *.accdb)" ODBC driver (present on
this machine). Supports an optional database password.
"""

from __future__ import annotations

from pathlib import Path

from ..exceptions import ConnectorError
from ._odbc import OdbcConnector

DEFAULT_DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"


class AccessConnector(OdbcConnector):
    type_name = "access"

    def _connection_string(self) -> str:
        db_path = self.config.get("path") or self.config.get("database")
        if not db_path:
            raise ConnectorError(
                f"[{self.name}] Access connection requires 'path' to the .accdb/.mdb file."
            )
        if not Path(db_path).exists():
            raise ConnectorError(f"[{self.name}] Access DB file not found: {db_path}")
        driver = self.config.get("driver", DEFAULT_DRIVER)
        parts = [f"DRIVER={{{driver}}}", f"DBQ={db_path}"]
        pwd = self.config.get("password")
        if pwd:
            parts.append(f"PWD={pwd}")
        return ";".join(parts) + ";"

    def _probe_sql(self) -> str:
        # Access has no bare "SELECT 1"; it needs a FROM. MSysObjects always exists.
        return "SELECT TOP 1 1 FROM MSysObjects"
