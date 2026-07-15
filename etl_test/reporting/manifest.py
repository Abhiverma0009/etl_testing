"""Run manifest: a fast index of recent runs.

Scans ``output/runs/*/result.json`` and writes ``output/manifest.json`` (newest
first). The Next.js app's run-history list reads this index directly instead of
opening every result.json on each request. (The HTML dashboard that previously
also lived in this package has been retired — the UI is now the Next.js app.)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MAX_RUNS = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_manifest(output_dir: str | Path, max_runs: int = DEFAULT_MAX_RUNS) -> Path:
    """Scan output/runs/*/result.json and write manifest.json (newest first)."""
    output_dir = Path(output_dir)
    runs_dir = output_dir / "runs"
    entries: list[dict[str, Any]] = []
    if runs_dir.exists():
        for jpath in runs_dir.glob("*/result.json"):
            try:
                data = json.loads(jpath.read_text(encoding="utf-8"))
            except Exception:
                continue
            rel = jpath.relative_to(output_dir).as_posix()
            entries.append({
                "run_id": data.get("run_id"),
                "started_at": data.get("started_at"),
                "finished_at": data.get("finished_at"),
                "passed": data.get("passed"),
                "counts": data.get("counts", {}),
                "source": data.get("source"),
                "target": data.get("target"),
                "suite": data.get("suite"),
                "category": data.get("category"),
                # The categories this run actually executed. Indexed here so the
                # app can tell a report run from a data run without opening every
                # result.json. Populated for existing runs too — the manifest is
                # rebuilt from scratch on every run.
                "categories": (data.get("meta") or {}).get("categories") or [],
                "path": rel,
            })
    entries.sort(key=lambda d: d.get("started_at") or "", reverse=True)
    manifest = {
        "generated": _now_iso(),
        "count": len(entries),
        "shown": min(len(entries), max_runs),
        "runs": entries[:max_runs],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return out
