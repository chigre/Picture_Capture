"""Whole-column white-line Y refinement for explicit existing-PDIC markers.

This is not OCR or Layout classification. Existing PDIC owns every marker and its
text; failure to prove a near-white full-column position preserves its Y.
"""
from __future__ import annotations

from typing import Any

import numpy as np


def _otsu_ink_threshold(region: np.ndarray) -> int:
    hist = np.bincount(region.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    if not total:
        return 185
    probability = hist / total
    weight = probability.cumsum()
    means = (probability * np.arange(256)).cumsum()
    denominator = weight * (1.0 - weight)
    scores = np.zeros(256, dtype=np.float64)
    good = denominator > 1e-10
    scores[good] = (means[-1] * weight[good] - means[good]) ** 2 / denominator[good]
    return max(105, min(205, int(scores.argmax())))


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    padded = np.pad(mask.astype(np.int8), (1, 1), constant_values=0)
    delta = np.diff(padded)
    return list(zip(np.flatnonzero(delta == 1), np.flatnonzero(delta == -1)))


def refine_existing_marker_to_ink_top(
    gray: np.ndarray,
    coarse_y: int,
    line_height: int,
    settings: Any,
    *,
    anchor_x: int,
    column_left: int,
    column_right: int,
    lower_bound: int = 0,
    upper_bound: int | None = None,
) -> tuple[int, dict[str, Any]]:
    """Search both ways around a saved Y, then select a near-white full-column Y.

    The small headword-anchor ROI identifies the first text band; the separate
    *whole column* ROI decides whether placing an entire separator at a proposed
    Y would touch other glyphs. Keep original Y if a safe band is not confirmed.
    """
    height, width = gray.shape[:2]
    coarse = int(coarse_y)
    details: dict[str, Any] = {"method": "whole_column_white_y", "reason": "unconfirmed"}
    if height < 8 or width < 12 or line_height < 2:
        return coarse, {**details, "reason": "image_too_small"}
    lo = max(0, int(lower_bound))
    hi = min(height, int(upper_bound) if upper_bound is not None else height)
    if not lo <= coarse < hi:
        return coarse, {**details, "reason": "outside_page_bounds"}
    max_ratio = max(0., min(1.5, float(settings.separator_y_max_shift_ratio)))
    max_shift = max(0, round(int(line_height) * max_ratio))
    min_gap = max(1, int(settings.paddle_separator_safety_px))
    if max_shift == 0:
        return coarse, {**details, "reason": "max_shift_zero"}

    left = max(0, min(width - 1, int(column_left)))
    right = max(left + 1, min(width, int(column_right)))
    margin = max(0, int(settings.paddle_separator_column_margin))
    # Only a narrow edge exclusion is permitted: preserve the real full-column
    # ink safety evidence rather than hiding long definitions on the right.
    excluded = min(margin, (right - left) // 10)
    safe_left = min(right - 1, left + excluded)
    safe_right = max(safe_left + 1, right - excluded)
    if safe_right - safe_left < 12:
        return coarse, {**details, "reason": "column_too_narrow"}

    start_x = min(right - 1, max(left, int(anchor_x)))
    fraction = max(.10, min(1., float(settings.paddle_separator_roi_width_ratio) / 100.))
    # A short word-anchor region determines which text line owns this marker.
    # The full-width verification below is NEVER restricted to this region.
    anchor_width = max(12, min(round((right - left) * fraction),
                               max(20, round(line_height * 2.5))))
    end_x = min(right, start_x + anchor_width)
    if end_x - start_x < 8:
        return coarse, {**details, "reason": "anchor_roi_too_narrow"}

    search_ratio = max(.05, min(.80, float(settings.paddle_separator_search_ratio)))
    radius = max(2, round(line_height * search_ratio))
    # Search upward and downward from the saved marker Y, not only below it.
    y0 = max(lo, coarse - max(max_shift, radius) - max(3, line_height // 3))
    y1 = min(hi, coarse + max(max_shift, radius) + max(6, line_height))
    if y1 - y0 < 6:
        return coarse, {**details, "reason": "scan_interval_too_short"}

    local = np.asarray(gray[y0:y1, start_x:end_x], dtype=np.uint8)
    full = np.asarray(gray[y0:y1, safe_left:safe_right], dtype=np.uint8)
    threshold = _otsu_ink_threshold(local)
    local_ink = (local <= threshold).sum(axis=1)
    ink_min = max(2, int(np.ceil(local.shape[1] * .015)))
    ink_rows = local_ink >= ink_min
    if int(settings.paddle_separator_band_radius) > 0 and len(ink_rows) >= 3:
        ink_rows[1:-1] |= ink_rows[:-2] & ink_rows[2:]

    # Count every dark pixel in each whole-column row, including those in
    # definition text far to the right of the headword.
    full_ink = (full <= max(185, threshold)).sum(axis=1)
    allowed = max(1, int(round(full.shape[1] * .003)))
    max_gap = max(min_gap + 3, int(round(line_height * .40)))
    # Rank clearance first: the preferred Y is ink_top - configured_safety.
    # Three-row whole-column evidence is still a hard admission gate, so
    # moving closer to the word may never cut a glyph elsewhere in the column.
    candidates: list[tuple[int, int, int, int, int]] = []
    for start, end in _runs(ink_rows):
        if start == 0 or end - start < max(4, round(line_height * .28)):
            continue
        ink_top = y0 + int(start)
        low = max(lo, ink_top - max_gap, coarse - max_shift, y0 + 1)
        high = min(ink_top - min_gap, coarse + max_shift, y1 - 2)
        for y in range(low, high + 1):
            i = y - y0
            # Check the candidate AND its neighbours across the whole column;
            # one locally blank pixel row inside a printed stroke is not safe.
            triple = full_ink[i - 1:i + 2]
            if len(triple) != 3 or np.any(triple > allowed):
                continue
            candidates.append((ink_top - y, int(triple.sum()),
                               abs(y - coarse), y, ink_top))
    details.update({"threshold": threshold, "full_width_ink_tolerance": allowed,
                    "full_roi_x0": safe_left, "full_roi_x1": safe_right,
                    "anchor_roi_x0": start_x, "anchor_roi_x1": end_x,
                    "scan_y0": y0, "scan_y1": y1,
                    "candidates": len(candidates)})
    if not candidates:
        return coarse, {**details, "reason": "no_whole_column_blank_y"}
    # Among verified near-white rows choose the nearest safe Y *above* the
    # current ink top. More whitespace is not automatically a better result.
    candidates.sort()
    gap, score, _, chosen, ink_top = candidates[0]
    return int(chosen), {**details, "reason": "verified_whole_column_blank",
                         "ink_top": int(ink_top), "gap": int(gap),
                         "whole_column_ink_score": int(score),
                         "shift": int(chosen) - coarse}
