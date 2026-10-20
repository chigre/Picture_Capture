"""Whole-column white-row / ink-valley Y refinement for existing PDIC markers.

This is not OCR or Layout classification. Existing PDIC owns every marker and its
text; use a near-white row first, then a genuine low-ink valley, else keep Y.
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
    """Search both ways around a saved Y for white rows or a local ink valley.

    The small headword-anchor ROI identifies the first text band; the separate
    *whole column* ROI prefers blank rows, otherwise a distinct low-ink valley
    near the current headword top. Preserve Y when neither is established.
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

    # Analyze the full column (including the optional half-gutters). Skewed
    # print often has NO three consecutive globally white rows; that must not
    # prevent using a genuine local ink valley above the headword.
    full_ink = (full <= max(185, threshold)).sum(axis=1)
    allowed = max(1, int(round(full.shape[1] * .003)))
    max_gap = max(min_gap + 3, int(round(line_height * .40)))
    white: list[tuple[int, int, int, int, int]] = []
    valleys: list[tuple[int, int, int, int, int]] = []
    # Each detected anchor band has its own short Y window. Never search the
    # entire page for a globally minimal row or expand past the move limit.
    for start, end in _runs(ink_rows):
        if start == 0 or end - start < max(4, round(line_height * .28)):
            continue
        ink_top = y0 + int(start)
        low = max(lo, ink_top - max_gap, coarse - max_shift, y0 + 1)
        high = min(ink_top - min_gap, coarse + max_shift, y1 - 2)
        band: list[tuple[int, int, int, int, int]] = []
        for y in range(low, high + 1):
            i = y - y0
            triple = full_ink[i - 1:i + 2]
            if len(triple) != 3:
                continue
            candidate = (ink_top - y, int(triple.sum()),
                         abs(y - coarse), y, ink_top)
            if np.all(triple <= allowed):
                white.append(candidate)
            band.append(candidate)

        if len(band) < 3:
            continue
        # Fallback only for a *real* local trough, not a flat swath of ink
        # (e.g. a descender or illustration covering every candidate row).
        scores = [candidate[1] for candidate in band]
        lowest, highest = min(scores), max(scores)
        contrast = max(2, round(full.shape[1] * .012))
        if highest - lowest < contrast or lowest * 4 > highest * 3:
            continue
        tolerance = max(1, round(full.shape[1] * .005))
        valleys.extend(
            candidate for candidate in band
            if candidate[1] <= lowest + tolerance
        )

    details.update({"threshold": threshold, "full_width_ink_tolerance": allowed,
                    "full_roi_x0": safe_left, "full_roi_x1": safe_right,
                    "anchor_roi_x0": start_x, "anchor_roi_x1": end_x,
                    "scan_y0": y0, "scan_y1": y1,
                    "candidates": len(white), "valley_candidates": len(valleys)})
    if white:
        # Original preference: smallest clearance above the detected ink top.
        gap, score, _, chosen, ink_top = min(white)
        reason = "verified_whole_column_blank"
    elif valleys:
        # Choose the closest qualified trough to the ink top, rather than
        # retaining the old Y only because its line cannot be perfectly white.
        gap, score, _, chosen, ink_top = min(valleys)
        reason = "verified_whole_column_valley"
    else:
        return coarse, {**details, "reason": "no_whole_column_blank_y"}

    return int(chosen), {**details, "reason": reason,
                         "ink_top": int(ink_top), "gap": int(gap),
                         "whole_column_ink_score": int(score),
                         "shift": int(chosen) - coarse}
