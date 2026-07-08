"""Parse an Excel mapping workbook into a :class:`MappingBook`.

Expected sheets (case-insensitive names; extra columns are ignored, missing
optional columns default sensibly). The parser validates structure and raises
``MappingError`` with an actionable message, or collects soft issues into
``MappingBook.warnings``.

Sheets
------
Tables               : one row per target table
Columns              : one row per target column
BusinessRules        : one row per rule (optional)
ReferentialIntegrity : one row per FK relationship (optional)

This schema is a *starting contract*; adjust the column aliases below to match the
client's real mapping document when available.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from ..exceptions import MappingError
from .models import (
    BusinessRule, ColumnMapping, MappingBook, RefIntegrityRule, TableMapping,
    _as_bool, _as_list,
)

log = logging.getLogger(__name__)

# Accept a few aliases per logical sheet name.
SHEET_ALIASES = {
    "tables": ["tables", "table", "table mapping", "tablemapping"],
    "columns": ["columns", "column", "column mapping", "columnmapping", "fields"],
    "business_rules": ["businessrules", "business rules", "rules", "business_rules"],
    "ref_integrity": ["referentialintegrity", "referential integrity",
                      "ref_integrity", "relationships", "foreignkeys", "foreign keys"],
}


def _norm(s: Any) -> str:
    return str(s).strip().lower().replace("_", "").replace(" ", "")


def _find_sheet(xls: pd.ExcelFile, logical: str) -> str | None:
    wanted = {_norm(a) for a in SHEET_ALIASES[logical]}
    for sheet in xls.sheet_names:
        if _norm(sheet) in wanted:
            return sheet
    return None


def _read_sheet(xls: pd.ExcelFile, sheet: str) -> pd.DataFrame:
    df = xls.parse(sheet, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    # Drop fully-empty rows.
    df = df.dropna(how="all")
    return df


class _Row:
    """Case-insensitive row accessor with aliases."""

    def __init__(self, row: pd.Series):
        self._map = {_norm(k): v for k, v in row.items()}

    def get(self, *names: str, default: Any = None) -> Any:
        for n in names:
            v = self._map.get(_norm(n))
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                if isinstance(v, str) and v.strip() == "":
                    continue
                return v
        return default


def _require_columns(df: pd.DataFrame, sheet: str, required: list[str]) -> None:
    have = {_norm(c) for c in df.columns}
    missing = [r for r in required if _norm(r) not in have]
    if missing:
        raise MappingError(
            f"Sheet '{sheet}' is missing required column(s): {missing}. "
            f"Found columns: {list(df.columns)}"
        )


def parse_mapping_workbook(path: str | Path) -> MappingBook:
    p = Path(path)
    if not p.exists():
        raise MappingError(f"Mapping workbook not found: {p}")
    try:
        xls = pd.ExcelFile(p)
    except Exception as exc:  # noqa: BLE001
        raise MappingError(f"Could not open mapping workbook {p}: {exc}") from exc

    book = MappingBook(source_file=str(p))

    tables_sheet = _find_sheet(xls, "tables")
    columns_sheet = _find_sheet(xls, "columns")
    if not tables_sheet:
        raise MappingError(
            f"Workbook {p} has no 'Tables' sheet. Sheets present: {xls.sheet_names}"
        )

    _parse_tables(_read_sheet(xls, tables_sheet), book, tables_sheet)

    if columns_sheet:
        _parse_columns(_read_sheet(xls, columns_sheet), book, columns_sheet)
    else:
        book.warnings.append(
            "No 'Columns' sheet found; value comparisons will fall back to all "
            "shared columns and key-only checks."
        )

    rules_sheet = _find_sheet(xls, "business_rules")
    if rules_sheet:
        _parse_rules(_read_sheet(xls, rules_sheet), book, rules_sheet)

    ref_sheet = _find_sheet(xls, "ref_integrity")
    if ref_sheet:
        _parse_ref(_read_sheet(xls, ref_sheet), book, ref_sheet)

    return book.finalize()


def _parse_tables(df: pd.DataFrame, book: MappingBook, sheet: str) -> None:
    _require_columns(df, sheet, ["target_table"])
    for _, raw in df.iterrows():
        r = _Row(raw)
        target_table = r.get("target_table", "target table", "target")
        if not target_table:
            continue
        target_table = str(target_table).strip()
        tm = TableMapping(
            target_table=target_table,
            source_system=_str_or_none(r.get("source_system", "source system")),
            source_object=_str_or_none(r.get("source_object", "source object",
                                              "source_table", "source")),
            target_db=_str_or_none(r.get("target_db", "target database", "database")),
            target_schema=_str_or_none(r.get("target_schema", "schema")),
            layer=_str_or_none(r.get("layer", "medallion")),
            load_type=str(r.get("load_type", "load type", default="full")).strip().lower(),
            source_object_type=str(r.get("source_object_type", "source object type",
                                         "source type", default="table")).strip().lower(),
            target_object_type=str(r.get("target_object_type", "target object type",
                                         "object type", "target type", default="table")).strip().lower(),
            key_columns=_as_list(r.get("key_columns", "key columns", "keys",
                                       "business_key", "primary_key")),
            active=_as_bool(r.get("active", "active_flag", "enabled", default="yes"),
                            default=True),
        )
        if target_table in book.tables:
            book.warnings.append(f"Duplicate table row for '{target_table}'; last one wins.")
        book.tables[target_table] = tm


def _parse_columns(df: pd.DataFrame, book: MappingBook, sheet: str) -> None:
    _require_columns(df, sheet, ["target_table", "target_column"])
    orphan_tables: set[str] = set()
    for _, raw in df.iterrows():
        r = _Row(raw)
        tt = r.get("target_table", "target table")
        tc = r.get("target_column", "target column", "target")
        if not tt or not tc:
            continue
        tt, tc = str(tt).strip(), str(tc).strip()
        cm = ColumnMapping(
            target_table=tt,
            target_column=tc,
            source_column=_str_or_none(r.get("source_column", "source column", "source")),
            source_datatype=_str_or_none(r.get("source_datatype", "source datatype",
                                               "source_type")),
            target_datatype=_str_or_none(r.get("target_datatype", "target datatype",
                                               "target_type", "datatype")),
            nullable=_as_bool(r.get("nullable", default="yes"), default=True),
            transformation=_str_or_none(r.get("transformation", "transform", "rule")),
            default_value=r.get("default_value", "default"),
            compare=_as_bool(r.get("compare", "compare?", default="yes"), default=True),
            case_sensitive=_as_bool(r.get("case_sensitive", "case sensitive"), default=False),
            numeric_tolerance=_float_or_none(r.get("numeric_tolerance", "tolerance")),
        )
        table = book.tables.get(tt)
        if table is None:
            orphan_tables.add(tt)
            continue
        table.columns.append(cm)
    if orphan_tables:
        book.warnings.append(
            f"Columns sheet references tables not in the Tables sheet "
            f"(ignored): {sorted(orphan_tables)}"
        )


def _parse_rules(df: pd.DataFrame, book: MappingBook, sheet: str) -> None:
    _require_columns(df, sheet, ["rule_id", "target_table", "rule_type"])
    for _, raw in df.iterrows():
        r = _Row(raw)
        rid = r.get("rule_id", "rule id", "id")
        tt = r.get("target_table", "target table")
        rtype = r.get("rule_type", "rule type", "type")
        if not rid or not tt or not rtype:
            continue
        params = _parse_params(r, book)
        book.business_rules.append(BusinessRule(
            rule_id=str(rid).strip(),
            target_table=str(tt).strip(),
            rule_type=str(rtype).strip().lower(),
            params=params,
            filter=_str_or_none(r.get("filter", "scope", "where")),
            severity=str(r.get("severity", default="P3")).strip(),
            use_case=_str_or_none(r.get("use_case", "use case", "uc")),
            description=str(r.get("description", "desc", default="")).strip(),
            active=_as_bool(r.get("active", default="yes"), default=True),
        ))


def _parse_params(r: _Row, book: MappingBook) -> dict[str, Any]:
    """Build a rule's params dict.

    Priority: an explicit ``params`` JSON cell, merged with convenience columns
    (column, expected, allowed_values, etc.).
    """
    params: dict[str, Any] = {}
    raw_params = r.get("params", "parameters")
    if raw_params:
        try:
            parsed = json.loads(str(raw_params))
            if isinstance(parsed, dict):
                params.update(parsed)
        except json.JSONDecodeError:
            book.warnings.append(
                f"Rule params not valid JSON, ignored: {raw_params!r}"
            )
    # Convenience columns.
    for key, aliases in {
        "column": ("column", "target_column", "field"),
        "expected": ("expected", "expected_value"),
        "allowed_values": ("allowed_values", "allowed", "domain"),
        "value": ("value",),
        "columns": ("columns",),
    }.items():
        v = r.get(*aliases)
        if v is not None and key not in params:
            if key in ("allowed_values", "columns"):
                params[key] = _as_list(v)
            else:
                params[key] = v
    return params


def _parse_ref(df: pd.DataFrame, book: MappingBook, sheet: str) -> None:
    _require_columns(df, sheet, ["child_table", "parent_table"])
    for _, raw in df.iterrows():
        r = _Row(raw)
        child = r.get("child_table", "child table", "child")
        parent = r.get("parent_table", "parent table", "parent")
        if not child or not parent:
            continue
        child_cols = _as_list(r.get("child_columns", "child columns", "child_column",
                                    "child_cols", "fk_columns"))
        parent_cols = _as_list(r.get("parent_columns", "parent columns",
                                     "parent_column", "parent_cols", "pk_columns"))
        if not child_cols or not parent_cols:
            book.warnings.append(
                f"Referential rule {child}->{parent} missing child/parent columns; skipped."
            )
            continue
        book.ref_integrity.append(RefIntegrityRule(
            child_table=str(child).strip(),
            child_columns=child_cols,
            parent_table=str(parent).strip(),
            parent_columns=parent_cols,
            severity=str(r.get("severity", default="P2")).strip(),
            description=str(r.get("description", default="")).strip(),
            active=_as_bool(r.get("active", default="yes"), default=True),
        ))


# --- small helpers ----------------------------------------------------------------
def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _float_or_none(v: Any) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
