"""Generate blank, correctly-structured mapping workbooks for the team to fill in.

Creates config/mappings/<name>_mapping.xlsx with the four expected sheets
(Tables, Columns, BusinessRules, ReferentialIntegrity), correct headers, and one
example row per sheet (marked so it's obvious to replace/delete).

Run:  python samples/make_mapping_template.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parents[1] / "config" / "mappings"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATES = ["valdb", "gpe", "globalcredit"]


def _tables() -> pd.DataFrame:
    return pd.DataFrame([{
        "source_system": "EXAMPLE (delete this row)",
        "source_object": "SRC_TABLE_OR_VIEW",
        "source_object_type": "table",   # table | view  (source side is a table or a view)
        "target_table": "TARGET_TABLE",
        "target_object_type": "table",   # table | view  (target side is a table or a view)
        "target_db": "", "target_schema": "", "layer": "gold",
        "load_type": "full", "key_columns": "KEY_COL_1, KEY_COL_2", "active": "yes",
    }])


def _columns() -> pd.DataFrame:
    cols = ["target_table", "target_column", "source_column", "source_datatype",
            "target_datatype", "nullable", "transformation", "default_value",
            "compare", "case_sensitive", "numeric_tolerance"]
    return pd.DataFrame([
        ["TARGET_TABLE", "KEY_COL_1", "KEY_COL_1", "VARCHAR", "VARCHAR", "no", "", "", "no", "no", ""],
        ["TARGET_TABLE", "FMV", "FMV", "DECIMAL", "DECIMAL", "yes", "", "", "yes", "no", "0.01"],
    ], columns=cols)


def _rules() -> pd.DataFrame:
    return pd.DataFrame([{
        "rule_id": "BR001", "target_table": "TARGET_TABLE", "rule_type": "value_equals",
        "column": "ADJ_CODE", "expected": "27", "allowed_values": "", "filter": "",
        "params": "", "severity": "P1", "use_case": "UC1",
        "description": "EXAMPLE rule — adjustment code must be 27 (edit/delete)",
    }])


def _ref() -> pd.DataFrame:
    return pd.DataFrame([{
        "child_table": "TARGET_TABLE", "child_columns": "FUND_CODE",
        "parent_table": "FUND", "parent_columns": "FUND_CODE",
        "severity": "P2", "description": "EXAMPLE FK (edit/delete)",
    }])


def main() -> None:
    for name in TEMPLATES:
        path = OUT_DIR / f"{name}_mapping.xlsx"
        if path.exists():
            print(f"skip (exists): {path}")
            continue
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            _tables().to_excel(xw, sheet_name="Tables", index=False)
            _columns().to_excel(xw, sheet_name="Columns", index=False)
            _rules().to_excel(xw, sheet_name="BusinessRules", index=False)
            _ref().to_excel(xw, sheet_name="ReferentialIntegrity", index=False)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
