"""Framework exception hierarchy.

All framework errors derive from ``EtlTestError`` so callers (CLI, runner) can
distinguish framework problems from unexpected bugs. Validators catch broad
exceptions per-check and convert them into ERROR results so a single failure
never aborts a whole run.
"""

from __future__ import annotations


class EtlTestError(Exception):
    """Base class for all framework errors."""


class ConfigError(EtlTestError):
    """Invalid or missing configuration (YAML, env vars, suite definition)."""


class ConnectionConfigError(ConfigError):
    """A connection is misconfigured or references an undefined connection name."""


class ConnectorError(EtlTestError):
    """A connector failed to connect, query, or fetch data."""


class MissingDriverError(ConnectorError):
    """A required ODBC driver or Python connector package is not installed."""


class MappingError(EtlTestError):
    """The Excel mapping workbook is missing, malformed, or fails validation."""


class ValidationSetupError(EtlTestError):
    """A validator could not be set up (e.g. key columns missing from mapping)."""
