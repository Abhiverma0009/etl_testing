"""MS Access connector (legacy Val DB) via pyodbc + the Access ODBC driver.
 
Requires the "Microsoft Access Driver (*.mdb, *.accdb)" ODBC driver (present on
this machine). Supports an optional database password.
"""
 
from __future__ import annotations
 
import logging
from pathlib import Path
 
from ..exceptions import ConnectorError
from ._odbc import OdbcConnector
 
log = logging.getLogger(__name__)
 
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
 
    def _probe(self) -> bool:
        # A raw "SELECT ... FROM MSysObjects" needs read permission on the system
        # catalog, which secured Access DBs commonly revoke (ODBC error -1907:
        # "no read permission on 'MSysObjects'"). Probe via the ODBC catalog API
        # (SQLTables) instead, and if even that is locked down, fall back to
        # trusting a successful open — connect() has already validated the driver,
        # file path and password, and the data tables are read independently.
        cur = self._conn.cursor()
        try:
            cur.tables()
            cur.fetchone()
            return True
        except Exception:  # noqa: BLE001 - catalog locked; open already proved reachability
            log.debug(
                "[%s] catalog probe unavailable (locked-down Access DB); "
                "relying on successful connection open.",
                self.name, exc_info=True,
            )
            return True
        finally:
            cur.close()