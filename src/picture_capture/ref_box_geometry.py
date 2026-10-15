"""REF hit-testing and four-sided geometry in original source-image pixels.

Pure functions allow editing behavior to be tested without a Tk display.
"""
from __future__ import annotations

from dataclasses import replace
from math import ceil
from typing import Iterable

from .ref_boxes import RefBox


MIN_SIZE = 2
SIDES = frozenset({"left", "right", "top", "bottom"})
CORNERS = frozenset({"top-left", "top-right", "bottom-left", "bottom-right"})


def hit_test(
    boxes: Iterable[RefBox], x: float, y: float, *, scale: float,
    selected_id: int | None = None,
) -> tuple[RefBox | None, str]:
    """Prefer selected edges, then topmost rectangle. Return (box, action).

    Side priority precedes movement only near the side (in screen pixels).
    The tolerance is scaled to source pixels so zoom never makes handles
    unreachable. Corners are supported in addition to all four sides.
    """
    boxes = list(boxes)
    tolerance = max(2, ceil(7 / max(float(scale), 0.08)))
    candidates = [b for b in boxes if b.id == selected_id]
    candidates.extend(b for b in reversed(boxes) if b.id != selected_id)
    for box in candidates:
        left, top = box.x, box.y
        right, bottom = box.x + box.w, box.y + box.h
        if not (left - tolerance <= x <= right + tolerance
                and top - tolerance <= y <= bottom + tolerance):
            continue
        # Prevent large source-pixel tolerances at low zoom from turning a
        # mid-edge drag into a corner drag or swallowing the move interior.
        tol_x = min(tolerance, max(2.0, box.w / 4))
        tol_y = min(tolerance, max(2.0, box.h / 4))
        near_left = abs(x - left) <= tol_x
        near_right = abs(x - right) <= tol_x
        near_top = abs(y - top) <= tol_y
        near_bottom = abs(y - bottom) <= tol_y
        # For narrow rectangles, choose the nearest of two opposing sides.
        if near_left and near_right:
            near_left = abs(x - left) <= abs(x - right)
            near_right = not near_left
        if near_top and near_bottom:
            near_top = abs(y - top) <= abs(y - bottom)
            near_bottom = not near_top
        if near_top and near_left:
            return box, "top-left"
        if near_top and near_right:
            return box, "top-right"
        if near_bottom and near_left:
            return box, "bottom-left"
        if near_bottom and near_right:
            return box, "bottom-right"
        if near_left and top - tolerance <= y <= bottom + tolerance:
            return box, "left"
        if near_right and top - tolerance <= y <= bottom + tolerance:
            return box, "right"
        if near_top and left - tolerance <= x <= right + tolerance:
            return box, "top"
        if near_bottom and left - tolerance <= x <= right + tolerance:
            return box, "bottom"
        if left <= x <= right and top <= y <= bottom:
            return box, "move"
    return None, "create"


def transform_box(
    original: RefBox, action: str, *, start: tuple[int, int],
    current: tuple[int, int], image_size: tuple[int, int],
) -> RefBox:
    """Clamp all four sides and both axes to image bounds, preserving identity."""
    width, height = image_size
    sx, sy = start
    x, y = current
    dx, dy = x - sx, y - sy
    if action == "move":
        return replace(
            original,
            x=max(0, min(max(0, width - original.w), original.x + dx)),
            y=max(0, min(max(0, height - original.h), original.y + dy)),
        )
    if action not in SIDES | CORNERS:
        raise ValueError(f"unknown REF edit action: {action}")
    left, top = original.x, original.y
    right, bottom = original.x + original.w, original.y + original.h
    if "left" in action:
        left = max(0, min(right - MIN_SIZE, left + dx))
    if "right" in action:
        right = min(width, max(left + MIN_SIZE, right + dx))
    if "top" in action:
        top = max(0, min(bottom - MIN_SIZE, top + dy))
    if "bottom" in action:
        bottom = min(height, max(top + MIN_SIZE, bottom + dy))
    return replace(original, x=left, y=top, w=right - left, h=bottom - top)




REF_ACTION_POSITIONS = ("above_right", "above_left", "right_side")


def ref_action_buttons(
    box: RefBox,
    image_size: tuple[int, int],
    scale: float,
    placement: str = "above_right",
    *,
    show_edit: bool = True,
    show_delete: bool = True,
) -> list[tuple[str, int, int, int, int]]:
    """Pixel-aligned REF action controls clamped to the source image bounds.

    Coordinates are original image pixels, so the hit-test and rendered
    buttons share the same geometry at every zoom. Above controls fall below
    when there is no room; right-side controls fall to the left on page edge.
    """
    if placement not in REF_ACTION_POSITIONS:
        placement = "above_right"
    labels = (["edit"] if show_edit else []) + (["delete"] if show_delete else [])
    if not labels:
        return []
    width, height = image_size
    if width <= 0 or height <= 0:
        return []
    scale = max(float(scale), 0.08)
    chip = max(1, min(round(22 / scale), width // 3 or 1, height // 3 or 1))
    gap = max(1, min(round(3 / scale), max(1, chip // 4)))
    count = len(labels)
    def clamp(value: int, ceiling: int) -> int:
        return max(0, min(max(0, ceiling), value))

    if placement == "right_side":
        stack_h = count * chip + (count - 1) * gap
        left = box.x + box.w + gap
        if left + chip > width:
            left = box.x - chip - gap
        left = clamp(left, width - chip)
        top = clamp(box.y, height - stack_h)
        return [
            (name, left, top + i * (chip + gap),
             left + chip, top + i * (chip + gap) + chip)
            for i, name in enumerate(labels)
        ]

    total_w = count * chip + (count - 1) * gap
    initial_x = box.x if placement == "above_left" else box.x + box.w - total_w
    left = clamp(initial_x, width - total_w)
    top = box.y - chip - gap
    if top < 0:
        top = box.y + box.h + gap
    top = clamp(top, height - chip)
    return [
        (name, left + i * (chip + gap), top,
         left + i * (chip + gap) + chip, top + chip)
        for i, name in enumerate(labels)
    ]

def action_cursor(action: str) -> str:
    if action in {"left", "right"}:
        return "sb_h_double_arrow"
    if action in {"top", "bottom"}:
        return "sb_v_double_arrow"
    if action in CORNERS:
        return "cross"
    if action == "move":
        return "fleur"
    return "crosshair"
