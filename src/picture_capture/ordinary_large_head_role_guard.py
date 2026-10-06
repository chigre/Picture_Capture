from __future__ import annotations

"""Conservative static authorization policy for oversized-head evidence.

A confirmed oversized display head is stronger than indentation: its first
logical row is an entry and continuation rows inside the glyph are body.  The
physical detector also finds weaker size candidates, though, so ordinary body
rows may change role only when row-front geometry and a strong size ratio agree.

This module is deliberately mutation-free. Detection and fusion import these
helpers directly so bootstrap/import order cannot select a weaker policy.
"""

from typing import Any


# A true display head in the supported dictionaries normally spans clearly more
# than one ordinary text row.  1.65 keeps the known ~1.75x consecutive-head case
# while leaving a margin above ordinary glyph/scan-height variation (~1.4-1.5x).
HARD_ROLE_OVERRIDE_RATIO = 1.65


def _nearest_row(column: Any, box: tuple[int, int, int, int], reference: float) -> Any | None:
    lines = list(getattr(column, "lines", []) or [])
    if not lines:
        return None
    _x0, y0, _x1, _y1 = box
    nearest = min(
        lines,
        key=lambda line: abs(float(getattr(line, "y0", 0) or 0) - float(y0)),
    )
    row_y0 = float(getattr(nearest, "y0", 0) or 0)
    row_y1 = float(getattr(nearest, "y1", row_y0) or row_y0)
    if not (
        row_y0 - reference * 0.50
        <= float(y0)
        <= row_y1 + reference * 0.30
    ):
        return None
    return nearest


def strict_candidate_starts_at_row_front(
    column: Any,
    box: tuple[int, int, int, int],
    line_height: float,
) -> bool:
    """Authorize only true row-front display-head geometry."""
    x0, _y0, x1, y1 = box
    reference = max(8.0, float(line_height))
    nearest = _nearest_row(column, box, reference)
    if nearest is None:
        return False

    try:
        first_x = float(getattr(nearest, "first_x", 0) or 0)
    except (TypeError, ValueError):
        first_x = 0.0
    anchor = getattr(nearest, "anchor_x", None)
    try:
        anchor_x = float(anchor) if anchor is not None else None
    except (TypeError, ValueError):
        anchor_x = None

    # Prefer the first full-height anchor when it is meaningfully after a tiny
    # prefix/number. Otherwise the physical first ink is the row-front target.
    if anchor_x is not None and anchor_x >= first_x + reference * 0.12:
        target = anchor_x
        left_limit = target - reference * 0.85
        right_limit = target + reference * 0.55
    else:
        target = first_x
        left_limit = target - reference * 0.35
        right_limit = target + reference * 0.85

    if not (left_limit <= float(x0) <= right_limit):
        return False

    height = max(0.0, float(y1) - float(box[1]))
    width = max(1.0, float(x1) - float(x0))
    role = str(getattr(nearest, "role", "body") or "body").lower()

    # Existing entry rows do not create overdraw, so they may retain the base
    # detector's looser oversized classification. A body row, however, needs
    # strong evidence before it is emitted as a role-changing candidate.
    if role not in {"entry", "headword"}:
        ratio = height / reference
        if ratio < HARD_ROLE_OVERRIDE_RATIO:
            return False
        # Reject horizontal multi-character merges. A single CJK display glyph
        # may be broad, but a box much wider than its height is usually body text
        # or underline-connected fragments rather than one oversized head.
        if width > reference * 2.25:
            return False
        if height / width < 0.60:
            return False

    return True


def strong_ordinary_large_head(evidence: Any, layout: Any) -> bool:
    """Return whether ordinary large-head evidence may change Layout roles.

    Non-large-head evidence is outside this policy and passes through unchanged.
    Weak ordinary-large-head evidence is consumed by fusion without generic
    nearest-row fallback, matching the former runtime wrapper contract.
    """
    source = str(getattr(evidence, "ocr_source", "") or "")
    issue = str(getattr(evidence, "issue_type", "") or "")
    if (
        "ordinary_large_head_evidence" not in source
        and "ORDINARY_OVERSIZED_DISPLAY_HEAD" not in issue
    ):
        return True

    height = float(getattr(evidence, "ocr_visual_run_height", 0.0) or 0.0)
    reference = float(getattr(evidence, "ocr_line_height_reference", 0.0) or 0.0)
    if reference <= 0:
        reference = float(getattr(layout, "ordinary_line_height", 0.0) or 0.0)
    if reference <= 0 or height <= 0:
        return False
    return bool(height / reference >= HARD_ROLE_OVERRIDE_RATIO)


__all__ = [
    "HARD_ROLE_OVERRIDE_RATIO",
    "strict_candidate_starts_at_row_front",
    "strong_ordinary_large_head",
]
