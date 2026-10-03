from __future__ import annotations

"""Conservative authorization layer for OCR-independent large-head evidence.

Recent Layout work deliberately made a *confirmed* oversized display head
stronger than indentation: its first logical row is an entry and continuation
rows inside the glyph are body.  That semantic rule is correct, but the physical
detector also emits weaker 1.38x-size candidates.  Treating every such candidate
as confirmed turns detector false positives into extra separator lines.

This module separates *candidate detection* from *role override authorization*.
A body row may be promoted only by strong, row-leading oversized evidence.  An
already-indented entry can still be inspected by the underlying detector, but a
weak candidate can never manufacture a new entry.
"""

from typing import Any, Callable


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
    """Authorize only true row-front display-head geometry.

    The previous runtime allowed a candidate up to 2.5 ordinary line-heights to
    the right of ``first_x``.  On dense dictionary text that reaches the second
    or third full-size character, so a merged/tall body object could be promoted
    to a headword.  Here the candidate must align with either the full-height
    anchor (preferred when a small superscript/prefix precedes the glyph) or the
    actual first ink.
    """
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
    # detector's looser oversized classification.  A body row, however, needs
    # strong evidence before it is even emitted as a role-changing candidate.
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


def _strong_ordinary_large_head(evidence: Any, layout: Any) -> bool:
    source = str(getattr(evidence, "ocr_source", "") or "")
    issue = str(getattr(evidence, "issue_type", "") or "")
    if "ordinary_large_head_evidence" not in source and "ORDINARY_OVERSIZED_DISPLAY_HEAD" not in issue:
        return True

    height = float(getattr(evidence, "ocr_visual_run_height", 0.0) or 0.0)
    reference = float(getattr(evidence, "ocr_line_height_reference", 0.0) or 0.0)
    if reference <= 0:
        reference = float(getattr(layout, "ordinary_line_height", 0.0) or 0.0)
    if reference <= 0 or height <= 0:
        return False
    return bool(height / reference >= HARD_ROLE_OVERRIDE_RATIO)


def install_ordinary_large_head_role_guard() -> None:
    """Install conservative candidate and fusion gates before Layout Core import."""
    from . import ordinary_large_head_runtime as detector_runtime
    from . import ordinary_evidence_fusion as fusion

    if bool(getattr(fusion, "_large_head_role_guard_installed", False)):
        return

    # detect_ordinary_large_head_entries_guarded resolves this module global at
    # call time, so replacing it here immediately tightens the already-installed
    # detector without duplicating its image/component logic.
    detector_runtime.candidate_starts_at_row_front = strict_candidate_starts_at_row_front

    original_force: Callable[..., tuple[bool, int]] = fusion._force_oversized_head_rows

    def guarded_force(understanding: Any, evidence: Any) -> tuple[bool, int]:
        # Consume weak ordinary-large-head evidence without falling through to
        # generic nearest-row promotion.  That fallthrough would recreate the
        # exact false-positive -> extra-entry amplification this guard prevents.
        if not _strong_ordinary_large_head(evidence, understanding.layout):
            return True, 0
        return original_force(understanding, evidence)

    fusion._force_oversized_head_rows = guarded_force
    fusion._large_head_role_guard_installed = True


__all__ = [
    "HARD_ROLE_OVERRIDE_RATIO",
    "install_ordinary_large_head_role_guard",
    "strict_candidate_starts_at_row_front",
]
