"""Optional, ink-safe original-image Y correction for existing separator candidates.

Does not classify, add, or remove entries. The usual shared OCR/Layout
separator refiner runs first; this safeguard only moves its result when that
exact row crosses substantial ink AND a verified local multi-row white gap
exists. It defaults OFF pending full-scan accuracy benchmarking.
"""
from __future__ import annotations

from typing import Any

import numpy as np


def refine_to_verified_white_gap(
    gray: np.ndarray, original_y: int, coarse_y: int, line_height: float,
    *, max_fraction: float = 0.25, ink_threshold: int = 185,
    existing_ink_ratio: float = 0.045, gap_ink_ratio: float = 0.02,
) -> tuple[int, dict[str, Any]]:
    """Find the nearest safe, multi-row white gap within a bounded ink ROI.

    The gray ROI is already expressed in the candidate's canonical coordinate
    space, and any correction must remain inside it. A gap must be three
    successive rows with at most the configured dark-pixel fraction. Do not "optimize" a row already
    sufficiently white, and do not force a move when no verified gap exists.
    """
    info: dict[str, Any] = {
        "ink_gap_guard": True,
        "gap_corrected": False,
        "original_y": int(original_y),
        "coarse_y": int(coarse_y),
    }
    data = np.asarray(gray)
    if data.ndim != 2 or data.shape[0] < 7 or data.shape[1] < 8:
        info["gap_reason"] = "roi_too_small"
        return int(original_y), info
    h = int(data.shape[0])
    y = int(original_y)
    if y < 0 or y >= h or not np.isfinite(float(line_height)):
        info["gap_reason"] = "invalid_position"
        return int(original_y), info

    # Quantize by character height; never jump into another physical row.
    radius = max(1, int(round(max(2.0, float(line_height)) * float(max_fraction))))
    radius = min(radius, max(1, int(round(float(line_height) * 0.30))))
    low, high = max(2, int(coarse_y) - radius), min(h - 3, int(coarse_y) + radius)
    if not low <= y <= high or high < low:
        info["gap_reason"] = "outside_anchor_window"
        return y, info
    roi = data[low - 2:high + 3]
    if roi.size == 0:
        info["gap_reason"] = "empty_roi"
        return y, info
    dark = np.asarray(roi < int(ink_threshold), dtype=np.float32).mean(axis=1)
    ink_here = float(dark[y - (low - 2)])
    info["original_ink_fraction"] = round(ink_here, 6)
    if ink_here <= float(existing_ink_ratio):
        info["gap_reason"] = "already_ink_safe"
        return y, info
    candidates: list[tuple[int, int, int]] = []
    for target in range(low, high + 1):
        at = target - (low - 2)
        if float(np.max(dark[at - 1:at + 2])) > float(gap_ink_ratio):
            continue
        # Prefer smallest distance from the original chosen position, then the
        # original coarse anchor, then earlier (upper) safe gap for stable ties.
        candidates.append((abs(target - y), abs(target - int(coarse_y)), target))
    if not candidates:
        info["gap_reason"] = "no_three_row_white_gap"
        return y, info
    corrected = min(candidates)[2]
    info["gap_corrected"] = corrected != y
    info["gap_reason"] = "verified_gap" if corrected != y else "same_position"
    info["corrected_ink_fraction"] = round(float(dark[corrected - (low - 2)]), 6)
    info["gap_shift_px"] = int(corrected - y)
    return int(corrected), info
