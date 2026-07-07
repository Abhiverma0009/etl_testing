"""Transformation / derivation accuracy.

Focuses on columns that are *transformed* between source and target (i.e. their
mapping declares a ``transformation`` expression, or source_column != target_column).
For these columns it runs a key-based source-vs-target comparison so that any
incorrectly applied transformation surfaces as a value mismatch.

Columns that are pure 1:1 copies are left to the reconciliation validator; this
keeps the transformation report focused on derivation logic.
"""

from __future__ import annotations

from ..core.result import Category, Severity, Status
from .base import Validator
from ._keycompare import key_compare


class TransformationValidator(Validator):
    category = Category.TRANSFORMATION

    def validate(self, tables):
        results = []
        tol = self.ctx.opt("numeric_tolerance")
        for t in tables:
            transformed = [
                c.target_column for c in t.columns
                if c.compare and c.target_column not in t.key_columns and (
                    (c.transformation and str(c.transformation).strip())
                    or (c.source_column and c.source_column != c.target_column)
                )
            ]
            if not transformed:
                results.append(self._check(
                    f"Transformation [{t.target_table}]", table=t.target_table,
                    status=Status.SKIPPED,
                    message="No transformed/renamed columns declared for this table."))
                continue
            sev = Severity.coerce(t.options.get("severity"), Severity.P2)
            chk, _ = key_compare(self, t, transformed,
                                 f"Transformation [{t.target_table}]", sev,
                                 default_tolerance=tol)
            chk.metrics["transformed_columns"] = transformed
            results.append(chk)
        return results
