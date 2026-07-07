"""Shared source-vs-target key comparison used by reconciliation & transformation.

Loads both sides (source columns already renamed to target names by
``Validator.load_source``), runs the comparison engine, writes evidence, and
returns a populated CheckResult plus the raw ComparisonResult for callers that
want to add aggregate checks (e.g. variance).
"""

from __future__ import annotations

from typing import Iterable

from ..core.comparison import compare, write_evidence
from ..core.result import CheckResult, Evidence, Severity, Status
from ..core.specs import specs_from_table
from ..mapping.models import TableMapping


def key_compare(validator, t: TableMapping, compare_columns: list[str] | None,
                name: str, severity: Severity,
                default_tolerance: float | None = None):
    """Returns (CheckResult, ComparisonResult|None)."""
    if not t.key_columns:
        return validator._check(
            name, table=t.target_table, status=Status.SKIPPED,
            message="No key_columns in mapping; cannot do row-level comparison."), None

    src = validator.load_source(t)
    if src is None:
        return validator._check(
            name, table=t.target_table, status=Status.SKIPPED,
            message="No source available; row-level comparison skipped."), None
    tgt = validator.load_target(t)

    # Restrict to columns that exist on both sides.
    if compare_columns is None:
        compare_columns = t.compare_columns()
    usable = [c for c in compare_columns if c in src.columns and c in tgt.columns]
    missing = [c for c in compare_columns if c not in src.columns or c not in tgt.columns]

    specs = specs_from_table(t, default_numeric_tolerance=default_tolerance)
    try:
        res = compare(src, tgt, t.key_columns, usable, specs)
    except ValueError as exc:
        return CheckResult.error(name, validator.category.value, str(exc),
                                 target_table=t.target_table, severity=severity), None

    evidence = write_evidence(res, validator.ctx.evidence_dir,
                              f"{validator.category.value}_{t.target_table}")
    status = Status.PASS if res.is_clean else Status.FAIL
    msg = _summarize(res, missing)
    sample, sample_cols = _best_sample(res)
    chk = validator._check(
        name, table=t.target_table, status=status, severity=severity,
        message=msg, metrics=res.summary_metrics(),
        sample=sample, sample_columns=sample_cols,
        evidence=[Evidence(**e) for e in evidence])
    if missing:
        chk.metrics["columns_not_compared"] = missing
    return chk, res


def _summarize(res, missing: Iterable[str]) -> str:
    parts = []
    if res.source_only:
        parts.append(f"{res.source_only} missing in target")
    if res.target_only:
        parts.append(f"{res.target_only} extra in target")
    if res.value_mismatches:
        parts.append(f"{res.value_mismatches} value mismatch(es)")
    if res.source_dup_keys or res.target_dup_keys:
        parts.append(f"dup keys s={res.source_dup_keys}/t={res.target_dup_keys}")
    if not parts:
        base = f"Reconciled {res.matched:,} keys cleanly."
    else:
        base = "; ".join(parts) + "."
    miss = list(missing)
    if miss:
        base += f" (Not compared, absent on a side: {miss})"
    return base


def _best_sample(res):
    if res.sample_mismatches:
        return res.sample_mismatches, list(res.sample_mismatches[0].keys())
    if res.sample_source_only:
        return res.sample_source_only, list(res.sample_source_only[0].keys())
    if res.sample_target_only:
        return res.sample_target_only, list(res.sample_target_only[0].keys())
    return [], []
