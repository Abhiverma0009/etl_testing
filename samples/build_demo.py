"""Generate an offline demo: a SQLite 'source', a SQLite 'target', and an Excel
mapping workbook — with deliberately seeded data issues so the dashboard shows a
realistic mix of PASS / WARN / FAIL.

Run:  python samples/build_demo.py
Then: etl-test run --suite samples/demo_suite.yaml --connections samples/demo_connections.yaml

This mirrors the Carlyle use cases at small scale (deals with public/private flag,
adjustment codes, debt/equity split, an excluded record, FK to a fund table).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)

SOURCE_DB = DATA / "source.sqlite"
TARGET_DB = DATA / "target.sqlite"
MAPPING = HERE / "demo_mapping.xlsx"


def _funds() -> pd.DataFrame:
    return pd.DataFrame([
        {"FUND_CODE": "CCOF_II", "FUND_NAME": "Carlyle Credit Opportunities II"},
        {"FUND_CODE": "CSP_IV", "FUND_NAME": "Carlyle Strategic Partners IV"},
        {"FUND_CODE": "GPE_VIII", "FUND_NAME": "Global Private Equity VIII"},
    ])


def _source_deals() -> pd.DataFrame:
    # The legacy "truth". Note: amounts as text with commas to exercise normalization.
    return pd.DataFrame([
        {"DEAL_ID": "D001", "FUND_CODE": "CCOF_II", "COMPANY": "Ultra Electronics",
         "PUBLIC_PRIVATE_FLAG": "Private", "ADJ_CODE": "27", "LINE_TYPE": "Equity",
         "FMV": "1,250,000.00", "CASH_RECEIVED": "50000", "PERIOD": "2026Q1"},
        {"DEAL_ID": "D001D", "FUND_CODE": "CCOF_II", "COMPANY": "Ultra Electronics",
         "PUBLIC_PRIVATE_FLAG": "Private", "ADJ_CODE": "27", "LINE_TYPE": "Debt",
         "FMV": "750,000.00", "CASH_RECEIVED": "0", "PERIOD": "2026Q1"},
        {"DEAL_ID": "D002", "FUND_CODE": "CSP_IV", "COMPANY": "Project Hollywood",
         "PUBLIC_PRIVATE_FLAG": "Public", "ADJ_CODE": "27", "LINE_TYPE": "Equity",
         "FMV": "3,000,000", "CASH_RECEIVED": "120000", "PERIOD": "2026Q1"},
        {"DEAL_ID": "D003", "FUND_CODE": "GPE_VIII", "COMPANY": "Genetix Bio",
         "PUBLIC_PRIVATE_FLAG": "Public", "ADJ_CODE": "27", "LINE_TYPE": "Equity",
         "FMV": "", "CASH_RECEIVED": "0", "PERIOD": "2026Q1"},  # null FMV (unrealised)
        # CP VII - Nouryon: tiny record that must be FIXED in source and NOT loaded.
        {"DEAL_ID": "D999", "FUND_CODE": "CCOF_II", "COMPANY": "Nouryon",
         "PUBLIC_PRIVATE_FLAG": "Private", "ADJ_CODE": "1", "LINE_TYPE": "Equity",
         "FMV": "0.01", "CASH_RECEIVED": "0", "PERIOD": "2026Q1"},
    ])


def _target_deals() -> pd.DataFrame:
    # The migrated result, WITH seeded defects:
    #  * D002 PUBLIC_PRIVATE_FLAG wrongly flipped to Private (IPO override missed) -> business rule FAIL + mismatch
    #  * D003 FMV defaulted to 0 instead of null -> null/zero FAIL
    #  * D999 Nouryon present though it must be excluded -> must_not_exist FAIL + row count diff
    #  * adjustment code on D001D changed to 1 -> value_equals FAIL
    return pd.DataFrame([
        {"DEAL_ID": "D001", "FUND_CODE": "CCOF_II", "COMPANY": "Ultra Electronics",
         "PUBLIC_PRIVATE_FLAG": "Private", "ADJ_CODE": "27", "LINE_TYPE": "Equity",
         "FMV": "1250000.00", "CASH_RECEIVED": "50000", "PERIOD": "2026Q1",
         "SOURCE_SYSTEM": "ILM", "LOAD_TIMESTAMP": "2026-06-01 02:00:00"},
        {"DEAL_ID": "D001D", "FUND_CODE": "CCOF_II", "COMPANY": "Ultra Electronics",
         "PUBLIC_PRIVATE_FLAG": "Private", "ADJ_CODE": "1", "LINE_TYPE": "Debt",
         "FMV": "750000.00", "CASH_RECEIVED": "0", "PERIOD": "2026Q1",
         "SOURCE_SYSTEM": "ILM", "LOAD_TIMESTAMP": "2026-06-01 02:00:00"},
        {"DEAL_ID": "D002", "FUND_CODE": "CSP_IV", "COMPANY": "Project Hollywood",
         "PUBLIC_PRIVATE_FLAG": "Private", "ADJ_CODE": "27", "LINE_TYPE": "Equity",
         "FMV": "3000000", "CASH_RECEIVED": "120000", "PERIOD": "2026Q1",
         "SOURCE_SYSTEM": "ILM", "LOAD_TIMESTAMP": "2026-06-01 02:00:00"},
        {"DEAL_ID": "D003", "FUND_CODE": "GPE_VIII", "COMPANY": "Genetix Bio",
         "PUBLIC_PRIVATE_FLAG": "Public", "ADJ_CODE": "27", "LINE_TYPE": "Equity",
         "FMV": "0", "CASH_RECEIVED": "0", "PERIOD": "2026Q1",
         "SOURCE_SYSTEM": "ILM", "LOAD_TIMESTAMP": "2026-06-01 02:00:00"},
        {"DEAL_ID": "D999", "FUND_CODE": "CCOF_II", "COMPANY": "Nouryon",
         "PUBLIC_PRIVATE_FLAG": "Private", "ADJ_CODE": "1", "LINE_TYPE": "Equity",
         "FMV": "0.01", "CASH_RECEIVED": "0", "PERIOD": "2026Q1",
         "SOURCE_SYSTEM": "ILM", "LOAD_TIMESTAMP": "2026-06-01 02:00:00"},
    ])


def _write_sqlite(path: Path, frames: dict[str, pd.DataFrame]) -> None:
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    try:
        for name, df in frames.items():
            df.to_sql(name, con, index=False)
    finally:
        con.close()


def _write_mapping() -> None:
    tables = pd.DataFrame([
        {"source_system": "ILM", "source_object": "DEALS", "target_table": "DEAL_FUND_VALUED_ASSET",
         "target_db": "", "target_schema": "", "layer": "gold", "load_type": "full",
         "key_columns": "DEAL_ID", "active": "yes"},
        {"source_system": "ILM", "source_object": "FUNDS", "target_table": "FUND",
         "target_db": "", "target_schema": "", "layer": "gold", "load_type": "full",
         "key_columns": "FUND_CODE", "active": "yes"},
    ])
    columns = pd.DataFrame([
        # DEAL table
        ["DEAL_FUND_VALUED_ASSET", "DEAL_ID", "DEAL_ID", "VARCHAR", "VARCHAR", "no", "", "", "no", "yes"],
        ["DEAL_FUND_VALUED_ASSET", "FUND_CODE", "FUND_CODE", "VARCHAR", "VARCHAR", "no", "", "", "yes", "yes"],
        ["DEAL_FUND_VALUED_ASSET", "COMPANY", "COMPANY", "VARCHAR", "VARCHAR", "yes", "", "", "yes", "yes"],
        ["DEAL_FUND_VALUED_ASSET", "PUBLIC_PRIVATE_FLAG", "PUBLIC_PRIVATE_FLAG", "VARCHAR", "VARCHAR", "no", "", "", "yes", "yes"],
        ["DEAL_FUND_VALUED_ASSET", "ADJ_CODE", "ADJ_CODE", "VARCHAR", "VARCHAR", "no", "", "", "yes", "yes"],
        ["DEAL_FUND_VALUED_ASSET", "LINE_TYPE", "LINE_TYPE", "VARCHAR", "VARCHAR", "no", "", "", "yes", "yes"],
        ["DEAL_FUND_VALUED_ASSET", "FMV", "FMV", "DECIMAL", "DECIMAL", "yes", "", "", "yes", "yes"],
        ["DEAL_FUND_VALUED_ASSET", "CASH_RECEIVED", "CASH_RECEIVED", "DECIMAL", "DECIMAL", "yes", "", "", "yes", "yes"],
        ["DEAL_FUND_VALUED_ASSET", "PERIOD", "PERIOD", "VARCHAR", "VARCHAR", "no", "", "", "yes", "yes"],
        # FUND table
        ["FUND", "FUND_CODE", "FUND_CODE", "VARCHAR", "VARCHAR", "no", "", "", "no", "yes"],
        ["FUND", "FUND_NAME", "FUND_NAME", "VARCHAR", "VARCHAR", "no", "", "", "yes", "yes"],
    ], columns=["target_table", "target_column", "source_column", "source_datatype",
                "target_datatype", "nullable", "transformation", "default_value",
                "compare", "case_sensitive"])

    rules = pd.DataFrame([
        {"rule_id": "BR001", "target_table": "DEAL_FUND_VALUED_ASSET", "rule_type": "value_equals",
         "column": "ADJ_CODE", "expected": "27", "filter": "", "allowed_values": "",
         "params": "", "severity": "P1", "use_case": "UC1",
         "description": "Adjustment code must be 27 for all deal records"},
        {"rule_id": "BR002", "target_table": "DEAL_FUND_VALUED_ASSET", "rule_type": "conditional",
         "column": "PUBLIC_PRIVATE_FLAG", "expected": "Public", "filter": "",
         "allowed_values": "", "params": '{"when": "COMPANY == \\"Project Hollywood\\""}',
         "severity": "P1", "use_case": "UC1",
         "description": "IPO company Project Hollywood must be flagged Public (override detected)"},
        {"rule_id": "BR003", "target_table": "DEAL_FUND_VALUED_ASSET", "rule_type": "must_not_exist",
         "column": "", "expected": "", "filter": "COMPANY == 'Nouryon'", "allowed_values": "",
         "params": "", "severity": "P1", "use_case": "UC2",
         "description": "CP VII Nouryon tiny record must be fixed in source and not loaded"},
        {"rule_id": "BR004", "target_table": "DEAL_FUND_VALUED_ASSET", "rule_type": "split",
         "column": "", "expected": "", "filter": "COMPANY == 'Ultra Electronics'",
         "allowed_values": "", "params": '{"group_by": "COMPANY", "type_column": "LINE_TYPE", "expect_distinct": 2}',
         "severity": "P2", "use_case": "UC2",
         "description": "Ultra Electronics must be split into Debt and Equity line items"},
    ])

    ref = pd.DataFrame([
        {"child_table": "DEAL_FUND_VALUED_ASSET", "child_columns": "FUND_CODE",
         "parent_table": "FUND", "parent_columns": "FUND_CODE", "severity": "P2",
         "description": "Every deal must reference a valid fund"},
    ])

    with pd.ExcelWriter(MAPPING, engine="openpyxl") as xw:
        tables.to_excel(xw, sheet_name="Tables", index=False)
        columns.to_excel(xw, sheet_name="Columns", index=False)
        rules.to_excel(xw, sheet_name="BusinessRules", index=False)
        ref.to_excel(xw, sheet_name="ReferentialIntegrity", index=False)


def main() -> None:
    _write_sqlite(SOURCE_DB, {"DEALS": _source_deals(), "FUNDS": _funds()})
    _write_sqlite(TARGET_DB, {"DEAL_FUND_VALUED_ASSET": _target_deals(), "FUND": _funds()})
    _write_mapping()
    print(f"Wrote {SOURCE_DB}")
    print(f"Wrote {TARGET_DB}")
    print(f"Wrote {MAPPING}")
    print("Now run: etl-test run --suite samples/demo_suite.yaml --connections samples/demo_connections.yaml")


if __name__ == "__main__":
    main()
