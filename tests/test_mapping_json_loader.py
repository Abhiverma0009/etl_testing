"""Round-trip: Excel mapping -> export-mapping JSON -> json_loader must produce an
equivalent MappingBook, so the Next.js app can edit mapping data as JSON with the
same semantics the Excel parser gives."""

import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "samples" / "demo_mapping.xlsx"


def _ensure_demo():
    if not XLSX.exists():
        subprocess.run([sys.executable, str(ROOT / "samples" / "build_demo.py")],
                       check=True, cwd=ROOT)


def _table_dump(book):
    return {name: asdict(t) for name, t in sorted(book.tables.items())}


def _rules_dump(book):
    return sorted((asdict(r) for r in book.business_rules), key=lambda d: d["rule_id"])


def _ref_dump(book):
    return sorted((asdict(r) for r in book.ref_integrity),
                  key=lambda d: (d["child_table"], d["parent_table"]))


def test_excel_json_roundtrip(tmp_path):
    _ensure_demo()
    from etl_test.mapping import load_mapping

    book_xlsx = load_mapping(XLSX)

    out_json = tmp_path / "demo_mapping.json"
    subprocess.run(
        [sys.executable, "-m", "etl_test.cli", "export-mapping",
         str(XLSX), "--output", str(out_json)],
        check=True, cwd=ROOT,
    )
    assert out_json.exists()

    book_json = load_mapping(out_json)

    # Structural equivalence (tables + columns + rules + ref-integrity).
    assert _table_dump(book_xlsx) == _table_dump(book_json)
    assert _rules_dump(book_xlsx) == _rules_dump(book_json)
    assert _ref_dump(book_xlsx) == _ref_dump(book_json)

    # is_key marking must survive the round-trip.
    deal_x = book_xlsx.table("DEAL_FUND_VALUED_ASSET")
    deal_j = book_json.table("DEAL_FUND_VALUED_ASSET")
    keys_x = {c.target_column for c in deal_x.columns if c.is_key}
    keys_j = {c.target_column for c in deal_j.columns if c.is_key}
    assert keys_x == keys_j == {"DEAL_ID"}
