"""Manual review selection, variant exclusion and sidecar override reads.

Pure in-memory mutation and read-only sidecar ingestion. Legacy core supplies
current manual-selection path resolver and JSON decoder at every invocation.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any


def enforce_position_variant_exclusivity(review_candidates: list[dict[str, Any]]) -> int:
    """Ensure at most one Y variant is selected for each physical headword."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in review_candidates:
        group_id = str(item.get("position_group_id", ""))
        if group_id:
            groups.setdefault(group_id, []).append(item)
    changed = 0
    for rows in groups.values():
        selected = [row for row in rows if row.get("selected")]
        if len(selected) <= 1:
            continue
        # A manually chosen variant wins; otherwise keep the refined default.
        manual = [row for row in selected if row.get("manual_override")]
        if manual:
            keeper = manual[-1]
        else:
            keeper = next((row for row in selected if row.get("position_variant") == "refined"), selected[0])
        for row in selected:
            if row is keeper:
                continue
            row["selected"] = False
            changed += 1
    return changed


def load_manual_selection_overrides(cache_path: Path | None, *, path_fn: Any, json_loads_fn: Any) -> dict[str, dict[str, Any]]:
    if cache_path is None:
        return {}
    path = path_fn(cache_path)
    if not path.exists():
        return {}
    try:
        raw = json_loads_fn(path.read_text(encoding="utf-8"))
        overrides = raw.get("overrides", {}) if isinstance(raw, dict) else {}
        return {str(k): dict(v) for k, v in overrides.items() if isinstance(v, dict)}
    except Exception:
        return {}


def apply_manual_selection_overrides(
    review_candidates: list[dict[str, Any]], overrides: dict[str, dict[str, Any]],
) -> None:
    for item in review_candidates:
        override = overrides.get(str(item.get("candidate_id", "")))
        if not override:
            continue
        if "selected" in override:
            item["selected"] = bool(override["selected"])
        if override.get("word") is not None:
            item["word"] = str(override.get("word") or "")
        if override.get("engine"):
            item["final_engine"] = str(override["engine"])
        item["manual_override"] = True
        item["decision_reason"] = "manual_override"
        issues = list(item.get("issue_types", []) or [])
        if "MANUAL_OVERRIDE" not in issues:
            issues.append("MANUAL_OVERRIDE")
        item["issue_types"] = issues
