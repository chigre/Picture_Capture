from __future__ import annotations

"""One-sided display-line anchoring shared by the opacity renderer.

Stored/detected coordinates are structural boundaries rather than visual centre
lines: marker Y is a top anchor, while a guide path is a left anchor.  Width=1
therefore stays unchanged; only added thickness is shifted inward/downward.
"""

from typing import Any


def one_sided_line_coordinates(
    coordinates: tuple[Any, ...] | list[Any],
    *,
    width: float,
    growth: str,
) -> tuple[float, ...]:
    values: tuple[Any, ...]
    if len(coordinates) == 1 and isinstance(coordinates[0], (list, tuple)):
        values = tuple(coordinates[0])
    else:
        values = tuple(coordinates)
    if len(values) < 4 or len(values) % 2:
        return tuple(float(value) for value in values)

    try:
        flattened = [float(value) for value in values]
        effective_width = max(1.0, float(width or 1.0))
    except (TypeError, ValueError):
        return tuple(float(value) for value in values)

    offset = max(0.0, (effective_width - 1.0) / 2.0)
    if offset <= 0.0:
        return tuple(flattened)

    normalized = str(growth or "").strip().lower()
    if normalized == "down":
        for index in range(1, len(flattened), 2):
            flattened[index] += offset
    elif normalized == "left":
        for index in range(0, len(flattened), 2):
            flattened[index] -= offset
    elif normalized == "right":
        for index in range(0, len(flattened), 2):
            flattened[index] += offset
    return tuple(flattened)


def add_line_anchor_help(dialog: Any) -> None:
    """Append directional anchor semantics to the existing display help."""
    help_map = dict(getattr(dialog, "SETTING_HELP", {}))
    additions = {
        "marker_height": (
            "粗细方向：词头横线的原始 Y 为上边界锚点；宽度增加时只向下方扩展，不向上遮挡词头。"
        ),
        "guide_width": (
            "粗细方向：栏左路径为左边界锚点；宽度增加时只向右侧扩展，不向栏外扩展。"
        ),
    }
    for name, suffix in additions.items():
        if name not in help_map:
            continue
        current = str(help_map[name]).rstrip()
        if suffix not in current:
            help_map[name] = current + "\n\n" + suffix
    dialog.SETTING_HELP = help_map


__all__ = ["add_line_anchor_help", "one_sided_line_coordinates"]
