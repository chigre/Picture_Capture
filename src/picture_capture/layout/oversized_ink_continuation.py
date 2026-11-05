"""Image-backed veto of duplicate entry starts *inside* printed large heads.

A large CJK display glyph often bridges two physical projection rows. Even
when its connected-component detector fragments that glyph, a second indent
role can be assigned one line below its real head. A broad Y-distance
deduplicator would delete valid adjacent dictionary headwords instead.

Only suppress a later indent-derived row when the leading ink band shows
continuous printed ink spanning the earlier entry and the later row. All
distances are scaled by the observed physical line height. Independent symbol
and verified large-head evidence is never vetoed here.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

from ..proofreading.classification import get_layout_line_classification


def _joined_head_ink(
    gray: Image.Image, column: Any,
    earlier_y: float, later_y: float, reference: float,
) -> bool:
    """Require an uninterrupted, ink-backed span across two entry boundaries.

    The narrow front-of-column band covers the single large glyph, rather
    than the whole definition. Distinct normal-height words have a blank row
    gap, even when their baselines happen to be near one another.
    """
    left = float(getattr(column, "left", 0) or 0)
    right = float(getattr(column, "right", gray.width) or gray.width)
    x0 = max(0, round(left + reference * .55))
    x1 = min(gray.width, round(left + reference * 3.4), round(right))
    y0 = max(0, round(earlier_y + reference * .15))
    y1 = min(gray.height, round(later_y + reference * .18))
    if x1 - x0 < max(12, reference) or y1 - y0 < reference * .70:
        return False
    patch = np.asarray(gray.crop((x0, y0, x1, y1)), dtype=np.uint8)
    if patch.ndim != 2 or patch.size == 0:
        return False
    # Require ink sustained over several columns, not a one-pixel scan rule.
    ink_per_row = np.count_nonzero(patch < 170, axis=1)
    active = ink_per_row >= max(3, round((x1 - x0) * .018))
    # Two ordinary printed rows may leave only a short interline blank.  An
    # oversized *single glyph* needs nearly uninterrupted leading ink; 75%
    # coverage was broad enough to erase real adjacent CJK dictionary heads.
    if float(np.mean(active)) < .94:
        return False
    gaps = np.flatnonzero(~active)
    if gaps.size == 0:
        return True
    boundaries = np.flatnonzero(np.diff(gaps) > 1)
    starts = np.r_[0, boundaries + 1]
    ends = np.r_[boundaries, gaps.size - 1]
    longest_gap = int(max(gaps[ends] - gaps[starts] + 1))
    return longest_gap <= max(1, round(reference * .05))


def _separate_left_edge_entry_rows(
    layout: Any, column: Any, earlier: Any, later: Any, reference: float,
) -> bool:
    """Protect two physical, same-indent headwords in a proven body-indent lane.

    The oversized-ink veto is a *weak* image heuristic, never authority to
    delete two otherwise independent entry rows. This protection is active
    only for a resolved left-edge/indented-body grammar, not for no-indent or
    truly oversized display-head layouts. It has no fixed image coordinates.
    """
    if str(getattr(layout, "indent_type", "") or "") != "body":
        return False
    body_mode = getattr(column, "body_mode", None)
    entry_modes = list(getattr(column, "entry_modes", ()) or ())
    if body_mode is None or not entry_modes:
        return False
    # Require repeated, independently observed lane families. A single
    # punctuation mark or illustration fragment is not proof of an entry lane.
    row_count = len(getattr(column, "lines", ()) or ())
    support_floor = max(3, round(row_count * .08))
    if int(getattr(body_mode, "support", 0) or 0) < support_floor:
        return False
    if max(int(getattr(mode, "support", 0) or 0) for mode in entry_modes) < support_floor:
        return False
    body_x = float(getattr(body_mode, "center", 0.0) or 0.0)
    entry_x = min(float(getattr(mode, "center", 0.0) or 0.0) for mode in entry_modes)
    if body_x - entry_x < max(15.0, .38 * reference):
        return False
    first_end = float(getattr(earlier, "y1", 0.0) or 0.0)
    later_start = float(getattr(later, "y0", 0.0) or 0.0)
    if later_start < first_end - .08 * reference:
        return False
    # Ordinary printing occupies about one line height per physical run.
    # Keep truly tall display-glyph fragments eligible for separate checking.
    for row in (earlier, later):
        height = float(getattr(row, "y1", 0.0) or 0.0) - float(
            getattr(row, "y0", 0.0) or 0.0
        )
        if not (.32 * reference <= height <= 1.28 * reference):
            return False
        first_x = float(getattr(row, "first_x", body_x) or 0.0)
        if abs(first_x - entry_x) > max(8.0, .25 * reference):
            return False
        if first_x >= entry_x + (body_x - entry_x) * .48:
            return False
    return True


def suppress_oversized_ink_continuation(
    image: Image.Image, layout: Any,
) -> dict[str, int]:
    """Demote only indistinguishable indent fragments within the same glyph.

    This is a final role veto, after independent OCR-free symbol/large-head
    evidence and verified-oversized recovery have completed. It does not
    create or move rows and cannot change an explicit large-head/symbol role.
    """
    stats = {"candidate_pairs": 0, "demoted_fragments": 0}
    reference = float(getattr(layout, "ordinary_line_height", 0) or 0)
    if reference < 4:
        return stats
    body_top = float(getattr(layout, "body_top", 0) or 0)
    candidates: list[tuple[Any, Any, Any, float, float]] = []
    for column in list(getattr(layout, "columns", ()) or ()):
        entries = sorted(
            (line for line in (getattr(column, "lines", ()) or ())
             if str(getattr(line, "role", "") or "") == "entry"),
            key=lambda line: float(getattr(line, "y0", 0) or 0),
        )
        for earlier, later in zip(entries, entries[1:]):
            gap = float(getattr(later, "y0", 0) or 0) - float(
                getattr(earlier, "y0", 0) or 0
            )
            if not (.70 * reference <= gap <= 1.65 * reference):
                continue
            meta = get_layout_line_classification(later)
            if meta.entry_source != "indent" or meta.manual_override:
                continue
            # Proven independent physical rows at the repeated entry left edge
            # must not be removed by ink continuity in the dictionary text.
            if _separate_left_edge_entry_rows(layout, column, earlier, later, reference):
                continue
            candidates.append((
                column, earlier, later,
                body_top + float(getattr(earlier, "y0", 0) or 0),
                body_top + float(getattr(later, "y0", 0) or 0),
            ))
    stats["candidate_pairs"] = len(candidates)
    if not candidates:
        return stats

    canonical = layout.transform.canonical_image_for_analysis(image.convert("RGB"))
    try:
        gray = canonical.convert("L")
        try:
            for column, earlier, later, first_y, second_y in candidates:
                if (str(getattr(earlier, "role", "")) == "entry"
                        and str(getattr(later, "role", "")) == "entry"
                        and _joined_head_ink(
                            gray, column, first_y, second_y, reference,
                        )):
                    later.role = "body"
                    stats["demoted_fragments"] += 1
        finally:
            gray.close()
    finally:
        canonical.close()
    return stats


__all__ = ["suppress_oversized_ink_continuation"]
