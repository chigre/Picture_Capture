from __future__ import annotations

"""Append physical-indent lane diagnostics to the Layout summary."""

from typing import Any

from .layout_indent_visibility import add_prepared_indent_summary


def _role_label(role: object) -> str:
    key = str(role or "unknown").strip().lower()
    if key in {"entry", "headword"}:
        return "entry"
    if key == "body":
        return "body"
    return "unknown"


def append_physical_lane_summary(base_text: str, app: Any) -> str:
    lanes = list(getattr(app, "_layout_visualization_indent_lanes", []) or [])
    if not lanes:
        return base_text

    lines = [base_text, "physical indent lanes:"]
    lanes.sort(key=lambda item: (int(item.get("column", 0)), float(item.get("center", 0.0))))
    for lane in lanes:
        column = int(lane.get("column", 0)) + 1
        index = int(lane.get("lane", 0)) + 1
        center = float(lane.get("center", 0.0))
        low = float(lane.get("min", center))
        high = float(lane.get("max", center))
        raw_low = float(lane.get("raw_min", low))
        raw_high = float(lane.get("raw_max", high))
        support = int(lane.get("support", 0))
        role = _role_label(lane.get("role", "unknown"))
        lines.append(
            f"  C{column}/L{index}: center={center:.1f}   "
            f"corrected={low:.1f}-{high:.1f}   "
            f"raw={raw_low:.1f}-{raw_high:.1f}   "
            f"n={support}   role={role}"
        )
    return "\n".join(lines)


def install_physical_lane_summary() -> None:
    """Compatibility no-op; lane/prepared summaries are statically composed."""
    return None
