"""Source-to-target mapping: models + Excel/JSON loaders."""

from __future__ import annotations

from pathlib import Path

from .models import (  # noqa: F401
    ColumnMapping, TableMapping, BusinessRule, RefIntegrityRule, MappingBook,
)
from .excel_parser import parse_mapping_workbook  # noqa: F401
from .json_loader import parse_mapping_json, mapping_book_from_dict  # noqa: F401


def load_mapping(path: str | Path) -> MappingBook:
    """Load a mapping from ``.json`` (json_loader) or ``.xlsx`` (excel_parser)."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        return parse_mapping_json(p)
    return parse_mapping_workbook(p)
