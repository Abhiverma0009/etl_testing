import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "samples" / "demo_mapping.xlsx"


def _ensure_demo():
    if not MAPPING.exists():
        subprocess.run([sys.executable, str(ROOT / "samples" / "build_demo.py")],
                       check=True, cwd=ROOT)


def test_parse_demo_mapping():
    _ensure_demo()
    from etl_test.mapping.excel_parser import parse_mapping_workbook
    book = parse_mapping_workbook(MAPPING)
    assert "DEAL_FUND_VALUED_ASSET" in book.tables
    deal = book.tables["DEAL_FUND_VALUED_ASSET"]
    assert deal.key_columns == ["DEAL_ID"]
    assert "FMV" in [c.target_column for c in deal.columns]
    # business rules parsed, including JSON params
    rule_ids = {r.rule_id for r in book.business_rules}
    assert {"BR001", "BR002", "BR003", "BR004"}.issubset(rule_ids)
    br002 = next(r for r in book.business_rules if r.rule_id == "BR002")
    assert "when" in br002.params
    # referential integrity parsed
    assert any(r.child_table == "DEAL_FUND_VALUED_ASSET" for r in book.ref_integrity)


def test_missing_workbook_raises():
    from etl_test.exceptions import MappingError
    from etl_test.mapping.excel_parser import parse_mapping_workbook
    with pytest.raises(MappingError):
        parse_mapping_workbook(ROOT / "does_not_exist.xlsx")
