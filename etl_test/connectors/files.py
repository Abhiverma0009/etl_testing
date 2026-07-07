"""Flat-file connector (AlpInvest / Anaplan feeds): CSV, TSV, Excel.

A "dataset" names a file path or glob (relative to ``base_dir``). Multiple files
matching a glob are concatenated (multi-file feed ingestion) with an added
``__source_file`` column for lineage/traceability. Reading is dtype-safe: by
default everything is read as string then coerced during normalization, which
avoids pandas guessing types differently across files.
"""

from __future__ import annotations

import glob
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from ..exceptions import ConnectorError
from .base import Connector, Dataset

log = logging.getLogger(__name__)


class FileConnector(Connector):
    type_name = "files"

    def _connect(self) -> Any:
        base = self.config.get("base_dir", ".")
        if not Path(base).exists():
            raise ConnectorError(f"[{self.name}] base_dir does not exist: {base}")
        return {"base_dir": base}

    def _resolve_paths(self, ds: Dataset) -> list[Path]:
        base = Path(self._conn["base_dir"])
        pattern = ds.options.get("path") or ds.table or ds.name
        if not pattern:
            raise ConnectorError(f"[{self.name}] dataset {ds.name!r} has no file path/pattern.")
        p = Path(pattern)
        search = str(p if p.is_absolute() else base / pattern)
        matches = sorted(glob.glob(search))
        if not matches:
            raise ConnectorError(f"[{self.name}] no files matched: {search}")
        return [Path(m) for m in matches]

    def _read_one(self, path: Path, ds: Dataset) -> pd.DataFrame:
        opts = ds.options
        suffix = path.suffix.lower()
        # read_* kwargs the user may override
        as_string = opts.get("dtype_str", True)
        read_kwargs: dict[str, Any] = {}
        if as_string:
            read_kwargs["dtype"] = str
        if suffix in (".xlsx", ".xls", ".xlsm"):
            df = self._read_excel(path, opts, read_kwargs)
        elif suffix in (".tsv",):
            df = pd.read_csv(path, sep="\t", encoding=opts.get("encoding", "utf-8"),
                             keep_default_na=True, na_values=opts.get("na_values"),
                             **read_kwargs)
        else:  # .csv and unknown -> csv
            df = pd.read_csv(path, sep=opts.get("sep", ","),
                             encoding=opts.get("encoding", "utf-8"),
                             keep_default_na=True, na_values=opts.get("na_values"),
                             **read_kwargs)
        df["__source_file"] = path.name
        return df

    def _read_excel(self, path: Path, opts: dict, read_kwargs: dict) -> pd.DataFrame:
        """Read one Excel workbook.

        ``sheet`` may be:
          * an int index or a tab name (default: first sheet)
          * a list of tab names/indexes -> each is read and concatenated (union),
            with a ``__sheet`` column recording which tab each row came from
            (needed for Global Credit fund files that use 4-5 tabs feeding one table)
          * "*" or None -> read ALL tabs and concatenate
        """
        sheet = opts.get("sheet", 0)
        header = opts.get("header", 0)

        if sheet in ("*", "all", None):
            book = pd.read_excel(path, sheet_name=None, header=header, **read_kwargs)
            frames = []
            for name, part in book.items():
                part["__sheet"] = str(name)
                frames.append(part)
            return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()

        if isinstance(sheet, (list, tuple)):
            frames = []
            for sh in sheet:
                part = pd.read_excel(path, sheet_name=sh, header=header, **read_kwargs)
                part["__sheet"] = str(sh)
                frames.append(part)
            return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()

        df = pd.read_excel(path, sheet_name=sheet, header=header, **read_kwargs)
        if opts.get("tag_sheet"):
            df["__sheet"] = str(sheet)
        return df

    def _fetch(self, ds: Dataset) -> pd.DataFrame:
        paths = self._resolve_paths(ds)
        frames = [self._read_one(p, ds) for p in paths]
        df = pd.concat(frames, ignore_index=True, sort=False) if len(frames) > 1 else frames[0]

        if ds.columns:
            missing = [c for c in ds.columns if c not in df.columns]
            if missing:
                raise ConnectorError(
                    f"[{self.name}] requested columns missing from file(s): {missing}. "
                    f"Available: {list(df.columns)}"
                )
            keep = list(ds.columns)
            for meta in ("__source_file", "__sheet"):
                if meta in df.columns and meta not in keep:
                    keep.append(meta)
            df = df[keep]

        if ds.where:
            # pandas query() for file sources (SQL-like 'where' is not supported here).
            try:
                df = df.query(ds.where)
            except Exception as exc:  # noqa: BLE001
                raise ConnectorError(
                    f"[{self.name}] 'where' for file sources must be a pandas query "
                    f"expression; got {ds.where!r}: {exc}"
                ) from exc
        return df

    def _probe(self) -> bool:
        return Path(self._conn["base_dir"]).exists()

    def _close(self) -> None:
        pass
