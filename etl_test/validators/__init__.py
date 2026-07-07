"""Validators — one module per test category.

Each validator subclasses :class:`~etl_test.validators.base.Validator` and is
registered in :data:`VALIDATORS` keyed by its :class:`~etl_test.core.result.Category`.
"""

from __future__ import annotations

from ..core.result import Category
from .base import Validator, ValidationContext  # noqa: F401

from .row_count import RowCountValidator
from .schema import SchemaValidator
from .datatype import DataTypeValidator
from .completeness import CompletenessValidator
from .business_rules import BusinessRulesValidator
from .referential_integrity import ReferentialIntegrityValidator
from .transformation import TransformationValidator
from .historical import HistoricalValidator
from .deduplication import DeduplicationValidator
from .null_handling import NullHandlingValidator
from .reconciliation import ReconciliationValidator
from .lineage import LineageValidator
from .incremental import IncrementalValidator
from .cross_source import CrossSourceValidator
from .report import ReportValidator, GvcReportValidator

VALIDATORS: dict[str, type[Validator]] = {
    Category.ROW_COUNT.value: RowCountValidator,
    Category.SCHEMA.value: SchemaValidator,
    Category.DATATYPE.value: DataTypeValidator,
    Category.COMPLETENESS.value: CompletenessValidator,
    Category.BUSINESS_RULES.value: BusinessRulesValidator,
    Category.REFERENTIAL_INTEGRITY.value: ReferentialIntegrityValidator,
    Category.TRANSFORMATION.value: TransformationValidator,
    Category.HISTORICAL.value: HistoricalValidator,
    Category.DEDUPLICATION.value: DeduplicationValidator,
    Category.NULL_HANDLING.value: NullHandlingValidator,
    Category.RECONCILIATION.value: ReconciliationValidator,
    Category.LINEAGE.value: LineageValidator,
    Category.INCREMENTAL.value: IncrementalValidator,
    Category.CROSS_SOURCE.value: CrossSourceValidator,
    Category.REPORT.value: ReportValidator,
    Category.GVC_REPORT.value: GvcReportValidator,  # legacy alias
}


def all_categories() -> list[str]:
    return list(VALIDATORS.keys())
