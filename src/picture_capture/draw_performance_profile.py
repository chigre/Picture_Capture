"""Opt-in per-page timings; per-PID files avoid cross-process locks.

Stage durations are elapsed wall times and MAY overlap in GPU/CPU pipelines.
Never sum overlapped stages to estimate total elapsed batch time.
"""
from __future__ import annotations

import json
from contextvars import ContextVar
import os
from pathlib import Path
import time
from .runtime_environment import user_data_root

_ENV = "PICTURE_CAPTURE_DRAW_PROFILE"
_CURRENT_PAGE: ContextVar[str | None] = ContextVar("draw_profile_page", default=None)


def bind_page(path: str | Path):
    return _CURRENT_PAGE.set(str(path))


def unbind_page(token) -> None:
    _CURRENT_PAGE.reset(token)



def enabled() -> bool:
    return os.environ.get(_ENV, "").strip().lower() in {"1", "true", "yes"}


def _directory() -> Path:
    return user_data_root() / "draw_profiles"


def record_page(image_path: str | Path, page_index: int, stages: dict[str, float],
                *, mode: str = "ordinary", stage_group: str = "page") -> None:
    if not enabled():
        return
    try:
        folder = _directory()
        folder.mkdir(parents=True, exist_ok=True)
        row = {
            "time": time.time(), "pid": os.getpid(),
            "page_index": int(page_index), "page": (
                _CURRENT_PAGE.get() if str(image_path) == "<substage>" else str(image_path)
            ),
            "mode": mode, "stage_group": stage_group,
            "stages_ms": {str(k): round(max(0.0, float(v)) * 1000, 3)
                          for k, v in stages.items()},
        }
        with (folder / f"{os.getpid()}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError):
        pass


def recent_profiles(since: float, *, pages: set[str] | None = None) -> list[dict]:
    rows: list[dict] = []
    try:
        files = list(_directory().glob("*.jsonl"))
    except OSError:
        return rows
    for path in files:
        try:
            if path.stat().st_mtime < since:
                continue
            for line in path.read_text(encoding="utf-8").splitlines()[-2000:]:
                try:
                    record = json.loads(line)
                    if float(record.get("time", 0)) < since:
                        continue
                    if pages is not None and str(record.get("page")) not in pages:
                        continue
                    rows.append(record)
                except (ValueError, TypeError):
                    continue
        except OSError:
            continue
    return sorted(rows, key=lambda row: (row["time"], row.get("page_index", 0)))


def summarize(records: list[dict]) -> dict[str, float]:
    sums: dict[str, float] = {}
    for record in records:
        for key, milliseconds in record.get("stages_ms", {}).items():
            sums[key] = sums.get(key, 0.0) + float(milliseconds)
    return sums
