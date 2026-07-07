"""Translate a :class:`TableMapping` into per-column :class:`ColumnNormSpec`s.

Maps declared datatypes (from the mapping workbook) onto normalization 'kinds'
so numeric/date/bool columns are compared appropriately, and carries per-column
tolerance and case-sensitivity settings.
"""

from __future__ import annotations

from .normalize import ColumnNormSpec
from ..mapping.models import TableMapping

_NUMERIC_HINTS = ("int", "num", "dec", "float", "double", "money", "real",
                  "currency", "amount", "fmv", "value")
_DATE_HINTS = ("date", "time", "timestamp", "datetime")
_BOOL_HINTS = ("bool", "bit", "flag", "logical")


def _kind_from_datatype(datatype: str | None) -> str:
    if not datatype:
        return "auto"
    dl = datatype.lower()
    if any(h in dl for h in _BOOL_HINTS):
        return "bool"
    if any(h in dl for h in _DATE_HINTS):
        return "datetime" if "time" in dl else "date"
    if any(h in dl for h in _NUMERIC_HINTS):
        return "numeric"
    return "string"


def specs_from_table(table: TableMapping,
                     default_numeric_tolerance: float | None = None) -> dict[str, ColumnNormSpec]:
    specs: dict[str, ColumnNormSpec] = {}
    for c in table.columns:
        kind = _kind_from_datatype(c.target_datatype or c.source_datatype)
        specs[c.target_column] = ColumnNormSpec(
            name=c.target_column,
            kind=kind,
            case_sensitive=c.case_sensitive,
            numeric_tolerance=c.numeric_tolerance if c.numeric_tolerance is not None
            else (default_numeric_tolerance if kind == "numeric" else None),
        )
    return specs
