"""Conservative top-of-ink anchoring for the explicit existing-PDIC refine command.

This is not OCR or Layout classification. Existing PDIC owns every marker and its
text; failure to prove a safe local text edge leaves its Y unchanged.
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
    """Align above a bounded current-line ink run; refuse unproven movements.

    ROI is anchored to the saved PDIC X rather than the whole definition width.
    Unlike the old valley-centre algorithm, wide whitespace does not increase
    the final margin between the marker and the actual glyph top.
    """
    h, w = gray.shape[:2]
    coarse = int(coarse_y)
    details: dict[str, Any] = {"method": "existing_marker_ink_top",
                               "reason": "unconfirmed"}
    if h < 8 or w < 12 or line_height < 2:
        return coarse, {**details, "reason": "image_too_small"}
    lo = max(0, int(lower_bound))
    hi = min(h, int(upper_bound) if upper_bound is not None else h)
    if not lo <= coarse < hi:
        return coarse, {**details, "reason": "outside_page_bounds"}

    ratio = max(0.05, min(0.80, float(settings.paddle_separator_search_ratio)))
    max_ratio = max(0.0, min(1.5, float(settings.separator_y_max_shift_ratio)))
    max_shift = max(0, round(int(line_height) * max_ratio))
    gap = max(1, int(settings.paddle_separator_safety_px))
    details.update({"max_shift": max_shift, "target_gap": gap})
    if max_shift == 0:
        return coarse, {**details, "reason": "max_shift_zero"}

    left = max(0, min(w - 1, int(column_left)))
    right = max(left + 1, min(w, int(column_right)))
    margin = max(0, int(settings.paddle_separator_column_margin))
    start_x = max(left + min(margin, max(0, (right - left) // 4)),
                  int(anchor_x))
    start_x = min(right - 1, start_x)
    fraction = max(0.10, min(1.0,
                            float(settings.paddle_separator_roi_width_ratio) / 100.0))
    roi_width = min(round((right - left) * fraction),
                    max(20, int(line_height) * 8))
    end_x = min(right, start_x + max(12, roi_width))
    if end_x - start_x < 8:
        return coarse, {**details, "reason": "anchor_roi_too_narrow"}

    search_radius = max(2, round(int(line_height) * ratio))
    y0 = max(lo, coarse - max(max_shift, search_radius) -
             max(3, line_height // 3))
    y1 = min(hi, coarse + max(max_shift, search_radius) +
             max(6, line_height))
    if y1 - y0 < 6:
        return coarse, {**details, "reason": "scan_interval_too_short"}
    region = np.asarray(gray[y0:y1, start_x:end_x], dtype=np.uint8)
    threshold = _otsu_ink_threshold(region)
    dark_count = (region <= threshold).sum(axis=1)
    row_min = max(2, int(np.ceil(region.shape[1] * 0.015)))
    ink_rows = dark_count >= row_min

    # Bridge single-row holes without shifting the actual top upward.
    if int(settings.paddle_separator_band_radius) > 0 and len(ink_rows) >= 3:
        ink_rows[1:-1] |= ink_rows[:-2] & ink_rows[2:]
    padded = np.pad(ink_rows, (1, 1), constant_values=False).astype(np.int8)
    transitions = np.diff(padded)
    starts = np.flatnonzero(transitions == 1)
    ends = np.flatnonzero(transitions == -1)
    min_run = max(4, round(line_height * 0.28))
    candidates: list[tuple[int, int, int]] = []
    for start, end in zip(starts, ends):
        if end - start < min_run or start == 0:
            continue
        top = y0 + int(start)
        proposed = top - gap
        if not (lo <= proposed < hi and abs(proposed - coarse) <= max_shift):
            continue
        blank_start = max(y0, proposed - 1)
        if bool(np.any(ink_rows[blank_start - y0:start])):
            continue
        candidates.append((abs(proposed - coarse), proposed, top))
    details.update({"threshold": threshold, "row_ink_min": row_min,
                    "roi_x0": start_x, "roi_x1": end_x,
                    "scan_y0": y0, "scan_y1": y1,
                    "candidates": len(candidates)})
    if not candidates:
        return coarse, {**details, "reason": "no_verified_headword_top"}
    candidates.sort(key=lambda item: (item[0], item[1]))
    if len(candidates) > 1 and candidates[1][0] - candidates[0][0] <= 1:
        return coarse, {**details, "reason": "ambiguous_neighbouring_lines"}
    _, proposed, ink_top = candidates[0]
    return proposed, {**details, "reason": "verified_ink_top",
                      "ink_top": ink_top, "shift": proposed - coarse}
