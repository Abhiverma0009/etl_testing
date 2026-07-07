"""SQL Server connector (other legacy systems) via pyodbc.

Supports SQL auth (user/password) and Windows/trusted auth.
"""

from __future__ import annotations

from ..exceptions import ConnectorError
from ._odbc import OdbcConnector

DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"


class SqlServerConnector(OdbcConnector):
    type_name = "sqlserver"

    def _connection_string(self) -> str:
        host = self.config.get("host") or self.config.get("server")
        database = self.config.get("database")
        if not host or not database:
            raise ConnectorError(
                f"[{self.name}] SQL Server connection requires 'host' and 'database'."
            )
        port = self.config.get("port")
        server = f"{host},{port}" if port else host
        driver = self.config.get("driver", DEFAULT_DRIVER)
        parts = [f"DRIVER={{{driver}}}", f"SERVER={server}", f"DATABASE={database}"]

        trusted = str(self.config.get("trusted", "no")).strip().lower() in ("yes", "true", "1")
        if trusted:
            parts.append("Trusted_Connection=yes")
        else:
            user = self.config.get("user") or self.config.get("username")
            pwd = self.config.get("password")
            if not user:
                raise ConnectorError(
                    f"[{self.name}] SQL Server needs 'user'/'password' or trusted: yes."
                )
            parts.append(f"UID={user}")
            parts.append(f"PWD={pwd or ''}")

        if str(self.config.get("encrypt", "yes")).lower() in ("no", "false", "0"):
            parts.append("Encrypt=no")
        if str(self.config.get("trust_server_certificate", "yes")).lower() in ("yes", "true", "1"):
            parts.append("TrustServerCertificate=yes")
        return ";".join(parts) + ";"
