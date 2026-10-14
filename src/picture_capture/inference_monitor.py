"""Per-process inference events for verifying actual OCR hardware selection.

Each PID writes its own JSONL to avoid competing writers on Windows spawn.
Initialization records are *not* proof of CUDA kernels executing; the UI
labels them as confirmed predictor configuration, not measured GPU utilization.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time

from .runtime_environment import user_data_root


def _root() -> Path:
    return user_data_root() / "inference_events"


def record_model_event(kind: str, device: str, mkldnn: str, threads: int) -> None:
    try:
        root = _root()
        root.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": time.time(), "pid": os.getpid(), "kind": str(kind),
            "device": str(device), "mkldnn": str(mkldnn),
            "cpu_threads": int(threads),
        }
        with (root / f"{os.getpid()}.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError):
        pass  # Diagnostic writes must never abort a patient's dictionary page.


def recent_model_events(since: float) -> list[dict]:
    events: list[dict] = []
    try:
        files = list(_root().glob("*.jsonl"))
    except OSError:
        return events
    for path in files:
        try:
            if path.stat().st_mtime < since:
                continue
            for line in path.read_text(encoding="utf-8").splitlines()[-300:]:
                row = json.loads(line)
                if float(row.get("timestamp", 0)) >= since:
                    events.append(row)
        except (OSError, ValueError, TypeError):
            continue
    return sorted(events, key=lambda row: float(row["timestamp"]))
