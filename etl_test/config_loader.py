"""Load and validate YAML configuration, resolving ``${ENV_VAR}`` placeholders.

Two config files:
  * ``connections.yaml`` -> named connection definitions (secrets via ${ENV}).
  * ``suite.yaml``       -> which tests to run against which tables + thresholds.

Secrets are NEVER stored in YAML; the YAML references environment variables that
are loaded from a git-ignored ``.env`` via python-dotenv.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from .exceptions import ConfigError, ConnectionConfigError

try:  # optional: .env is convenience, not required
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def load_env(env_file: str | Path | None = None) -> None:
    """Load .env into os.environ if python-dotenv is available."""
    if load_dotenv is None:
        return
    if env_file:
        load_dotenv(env_file, override=False)
    else:
        load_dotenv(override=False)  # finds .env in cwd / parents


def _resolve_env(value: Any) -> Any:
    """Recursively replace ``${VAR}`` / ``${VAR:-default}`` in strings."""
    if isinstance(value, str):
        def repl(m: re.Match) -> str:
            var, default = m.group(1), m.group(2)
            env_val = os.environ.get(var)
            if env_val is None:
                if default is not None:
                    return default
                raise ConfigError(
                    f"Environment variable '{var}' is referenced in config but not set. "
                    f"Add it to your .env (see .env.example)."
                )
            return env_val
        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


def load_yaml(path: str | Path, resolve_env: bool = True) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Config file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse YAML {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Top-level YAML in {p} must be a mapping/object.")
    return _resolve_env(raw) if resolve_env else raw


class Connections:
    """Holds named connection configs from connections.yaml."""

    def __init__(self, data: dict[str, Any]):
        conns = data.get("connections", data)
        if not isinstance(conns, dict) or not conns:
            raise ConnectionConfigError(
                "connections.yaml must define a non-empty 'connections:' mapping."
            )
        self._conns = conns

    @classmethod
    def from_file(cls, path: str | Path) -> "Connections":
        # Load WITHOUT resolving ${VAR} — resolution is lazy, per-connection, in
        # get(), so an unset env var on a connection you don't use never blocks a
        # run (e.g. running an Access-only hop with no Snowflake creds set).
        return cls(load_yaml(path, resolve_env=False))

    def names(self) -> list[str]:
        return list(self._conns.keys())

    def get(self, name: str) -> dict[str, Any]:
        if name not in self._conns:
            raise ConnectionConfigError(
                f"Connection '{name}' not defined. Known: {', '.join(self.names()) or '(none)'}"
            )
        # Resolve ${VAR} only for the connection actually requested.
        cfg = dict(_resolve_env(self._conns[name]))
        if "type" not in cfg:
            raise ConnectionConfigError(
                f"Connection '{name}' missing required 'type' "
                f"(one of: access, snowflake, sqlserver, files)."
            )
        cfg.setdefault("name", name)
        return cfg


def load_suite(path: str | Path) -> dict[str, Any]:
    """Load and lightly validate a suite definition.

    A suite must define a target and either a mapping (for data validation) or
    ``reports:`` (for a report-only run). ``tables:`` is optional — when omitted,
    the run covers all active tables in the mapping.
    """
    data = load_yaml(path)
    if not data.get("mapping") and not data.get("reports"):
        raise ConfigError(
            f"Suite {path} must define 'mapping:' (path to the mapping .xlsx/.json) "
            f"or 'reports:' (a list of report ids).")
    if not data.get("target"):
        raise ConfigError(f"Suite {path} must define 'target:' (a connection name).")
    return data
