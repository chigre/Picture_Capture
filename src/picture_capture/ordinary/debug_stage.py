"""Read-only ordinary marker provenance snapshots for Layout replay."""
from __future__ import annotations

from typing import Any
from ..models import Entry


def _record_ordinary_debug_stage(
    trace: dict[str, Any] | None,
    stage: str,
    entries: list[Entry],
    **details: Any,
) -> None:
    """Snapshot each materialized marker at the actual production seam.

    Enabled ONLY for a user-initiated read-only diagnostic run. Never writes
    project files, mutates role objects or changes detection decisions.
    """
    if trace is None:
        return
    rows = [{
        "x": int(item.x), "y": int(item.y),
        "source": str(getattr(item, "ocr_source", "") or ""),
        "issue_type": str(getattr(item, "issue_type", "") or ""),
        "oversized": bool(getattr(item, "ocr_oversized_cjk", False)),
    } for item in entries]
    stages = trace.setdefault("stages", [])
    current_keys = {(item["x"], item["y"]) for item in rows}
    previous = stages[-1]["entries"] if stages else []
    previous_keys = {(item["x"], item["y"]) for item in previous}
    stages.append({
        "stage": stage, "count": len(rows), "entries": rows,
        "added": [item for item in rows
                  if (item["x"], item["y"]) not in previous_keys],
        "removed": [item for item in previous
                    if (item["x"], item["y"]) not in current_keys],
        **details,
    })
    replay_trace = trace.get("_layout_replay_trace")
    if replay_trace is not None:
        from .unified_diagnostics import STAGE_DESCRIPTIONS
        replay_trace.add_entries(
            stages[-1], description=STAGE_DESCRIPTIONS.get(stage, stage),
        )


