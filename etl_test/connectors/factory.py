"""Build connectors from configuration and parse ``conn:object`` references."""

from __future__ import annotations

from typing import Any

from ..config_loader import Connections
from ..exceptions import ConnectionConfigError
from .base import Connector, Dataset

_REGISTRY: dict[str, type[Connector]] = {}


def _register() -> None:
    # Imported lazily so the package still imports when optional drivers are absent.
    from .access import AccessConnector
    from .snowflake import SnowflakeConnector
    from .sqlserver import SqlServerConnector
    from .files import FileConnector
    from .sqlite import SqliteConnector

    for cls in (AccessConnector, SnowflakeConnector, SqlServerConnector,
                FileConnector, SqliteConnector):
        _REGISTRY[cls.type_name] = cls


def make_connector(config: dict[str, Any]) -> Connector:
    if not _REGISTRY:
        _register()
    ctype = str(config.get("type", "")).strip().lower()
    if ctype not in _REGISTRY:
        raise ConnectionConfigError(
            f"Unknown connection type {ctype!r}. "
            f"Supported: {', '.join(sorted(_REGISTRY))}."
        )
    return _REGISTRY[ctype](config)


def connector_for(name: str, connections: Connections) -> Connector:
    return make_connector(connections.get(name))


def parse_ref(ref: str) -> tuple[str, str | None]:
    """Parse a ``connection:object`` CLI reference.

    Returns ``(connection_name, object_or_none)``. The object part may itself
    contain colons only if quoted; we split on the first colon.
    """
    if ":" in ref:
        conn, obj = ref.split(":", 1)
        return conn.strip(), obj.strip() or None
    return ref.strip(), None


def dataset_from_ref(ref: str, columns: list[str] | None = None,
                     where: str | None = None) -> tuple[str, Dataset]:
    """Build a (connection_name, Dataset) from a ``conn:table`` reference."""
    conn, obj = parse_ref(ref)
    ds = Dataset(name=obj or conn, table=obj, columns=columns, where=where)
    return conn, ds
