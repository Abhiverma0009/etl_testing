"""Extract test cases / requirements from Excel or CSV into Markdown.

Raw .xlsx/.csv is not directly readable by Cursor's agent as structured data (xlsx
is binary; CSV works but a faithful Markdown table is easier for an LLM to reason
over column-by-column). This dumps every sheet/file to a Markdown table under
output/_extracted/<name>.md — which Cursor CAN read and hand to either:

  - the `test-case-to-suite` rule (input: an existing test-case/scenario sheet)
  - the `jira-to-test-cases` rule (input: a Jira export of user stories)

It does NOT interpret the content — it just makes it readable; the sheet/column
layout is preserved as-is, no filename- or content-based special-casing.

Usage
-----
  .venv\\Scripts\\python.exe scripts\\extract_test_cases.py "docs\\Historical Load.xlsx"
  .venv\\Scripts\\python.exe scripts\\extract_test_cases.py docs\\           # all .xlsx/.csv in a folder
  .venv\\Scripts\\python.exe scripts\\extract_test_cases.py "docs\\jira_export.csv"
  .venv\\Scripts\\python.exe scripts\\extract_test_cases.py a.xlsx b.csv --out output\\_extracted
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "output" / "_extracted"
EXCEL_EXT = {".xlsx", ".xlsm"}
CSV_EXT = {".csv", ".tsv"}


def _iter_inputs(paths: list[str]):
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for ext in EXCEL_EXT | CSV_EXT:
                yield from sorted(path.glob(f"*{ext}"))
        elif path.suffix.lower() in EXCEL_EXT | CSV_EXT:
            yield path
        else:
            print(f"  ! skipping (not .xlsx/.xlsm/.csv/.tsv): {path}", file=sys.stderr)


def _dump_frame(name: str, df: pd.DataFrame, parts: list[str]) -> None:
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all").fillna("")
    parts.append(f"## Sheet: {name}  ({len(df)} rows × {len(df.columns)} cols)")
    parts.append("")
    parts.append("_(empty)_" if df.empty else df.to_markdown(index=False))
    parts.append("")


def extract_file(src: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    parts: list[str] = [f"# Extracted from: {src.name}", ""]
    if src.suffix.lower() in EXCEL_EXT:
        # Everything as text so ids/codes/quarters aren't mangled.
        sheets = pd.read_excel(src, sheet_name=None, dtype=str)
        parts.append(f"_{len(sheets)} sheet(s). Faithful dump — interpret with the "
                     "appropriate Cursor rule._")
        parts.append("")
        for name, df in sheets.items():
            _dump_frame(name, df, parts)
    else:
        sep = "\t" if src.suffix.lower() == ".tsv" else ","
        df = pd.read_csv(src, dtype=str, sep=sep)
        parts.append("_Faithful dump — interpret with the appropriate Cursor rule._")
        parts.append("")
        _dump_frame(src.stem, df, parts)
    out_file = out_dir / f"{src.stem}.md"
    out_file.write_text("\n".join(parts), encoding="utf-8")
    return out_file


def main() -> int:
    ap = argparse.ArgumentParser(description="Dump Excel/CSV test-case or Jira-export sheets to Markdown.")
    ap.add_argument("paths", nargs="+", help="File(s) or folder(s) containing .xlsx/.xlsm/.csv/.tsv")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help=f"Output dir (default {DEFAULT_OUT}).")
    args = ap.parse_args()

    out_dir = Path(args.out)
    files = list(_iter_inputs(args.paths))
    if not files:
        print("No .xlsx/.xlsm/.csv/.tsv files found in the given path(s).", file=sys.stderr)
        return 1

    for f in files:
        try:
            out_file = extract_file(f, out_dir)
            print(f"Extracted {f.name} -> {out_file}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! failed on {f}: {exc}", file=sys.stderr)
    print(f"\nNext: in Cursor, point the agent at {out_dir} and ask it to convert "
          "(test-case-to-suite) or draft test cases from it (jira-to-test-cases).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
