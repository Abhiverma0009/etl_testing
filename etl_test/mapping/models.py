"""Mapping data model.

A :class:`MappingBook` is the parsed contents of one Excel mapping workbook. It
drives every validator: which tables map where, column-level compare config,
business rules, and referential-integrity relationships.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _as_list(value: Any) -> list[str]:
    """Split a delimited cell ('a, b; c') into a clean list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    for sep in (";", "|", ","):
        if sep in text:
            return [p.strip() for p in text.split(sep) if p.strip()]
    return [text]


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("y", "yes", "true", "1", "t")


@dataclass
class ColumnMapping:
    target_table: str
    target_column: str
    source_column: str | None = None
    source_datatype: str | None = None
    target_datatype: str | None = None
    nullable: bool = True
    transformation: str | None = None   # free text / expression describing the rule
    default_value: Any = None
    compare: bool = True                 # include in value comparison?
    case_sensitive: bool = False
    numeric_tolerance: float | None = None
    is_key: bool = False                 # populated from the table's key_columns


@dataclass
class TableMapping:
    target_table: str
    source_system: str | None = None
    source_object: str | None = None
    target_db: str | None = None
    target_schema: str | None = None
    layer: str | None = None             # bronze/silver/gold
    load_type: str = "full"              # full | incremental
    # Whether each side's object is a physical TABLE or a VIEW. Purely
    # descriptive for reads (the engine queries `SELECT ... FROM <name>` either
    # way), but audit-relevant: a view can't structurally drift on its own,
    # a table can. Accepts "table" | "view"; defaults to "table".
    source_object_type: str = "table"
    target_object_type: str = "table"
    key_columns: list[str] = field(default_factory=list)
    active: bool = True
    columns: list[ColumnMapping] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)

    def fq_target(self) -> str:
        parts = [p for p in (self.target_db, self.target_schema, self.target_table) if p]
        return ".".join(parts)

    def compare_columns(self) -> list[str]:
        return [c.target_column for c in self.columns
                if c.compare and c.target_column not in self.key_columns]

    def column(self, target_column: str) -> ColumnMapping | None:
        for c in self.columns:
            if c.target_column == target_column:
                return c
        return None

    def source_to_target(self) -> dict[str, str]:
        return {c.source_column: c.target_column
                for c in self.columns if c.source_column}


@dataclass
class BusinessRule:
    rule_id: str
    target_table: str
    rule_type: str                       # see validators/business_rules.py
    params: dict[str, Any] = field(default_factory=dict)
    filter: str | None = None            # pandas query restricting the scope
    severity: str = "P3"
    use_case: str | None = None
    description: str = ""
    active: bool = True


@dataclass
class RefIntegrityRule:
    child_table: str
    child_columns: list[str]
    parent_table: str
    parent_columns: list[str]
    severity: str = "P2"
    description: str = ""
    active: bool = True


@dataclass
class MappingBook:
    source_file: str
    tables: dict[str, TableMapping] = field(default_factory=dict)
    business_rules: list[BusinessRule] = field(default_factory=list)
    ref_integrity: list[RefIntegrityRule] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def table(self, name: str) -> TableMapping | None:
        return self.tables.get(name)

    def active_tables(self) -> list[TableMapping]:
        return [t for t in self.tables.values() if t.active]

    def rules_for(self, target_table: str) -> list[BusinessRule]:
        return [r for r in self.business_rules
                if r.active and r.target_table == target_table]

    def ref_rules_for(self, child_table: str) -> list[RefIntegrityRule]:
        return [r for r in self.ref_integrity
                if r.active and r.child_table == child_table]

    def finalize(self) -> "MappingBook":
        """Mark key columns on ColumnMappings and warn on keyless tables.

        Called by every loader (Excel or JSON) after tables/columns are
        populated, so both paths produce identical books. Not idempotent for
        warnings — call exactly once per load.
        """
        for t in self.tables.values():
            keyset = set(t.key_columns)
            for c in t.columns:
                c.is_key = c.target_column in keyset
            if not t.key_columns:
                self.warnings.append(
                    f"Table '{t.target_table}' has no key_columns; row-level comparison "
                    f"and reconciliation for it will be limited to count/aggregate checks."
                )
            # Normalize object types to "table" | "view" (default table on anything else).
            for side in ("source_object_type", "target_object_type"):
                val = str(getattr(t, side) or "table").strip().lower()
                if val not in ("table", "view"):
                    self.warnings.append(
                        f"Table '{t.target_table}' has {side}={val!r}; expected "
                        f"'table' or 'view'. Treating it as 'table'."
                    )
                    val = "table"
                setattr(t, side, val)
        return self
