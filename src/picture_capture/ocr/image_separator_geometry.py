from __future__ import annotations

"""Detect grayscale image-only separator candidates and pair OCR lines.

Candidate proposals remain independent of text recognition. No raw OCR cache,
saved marker, review arbitration or persisted coordinate is modified here.
The historical OCR core passes its current visual measurement hooks per call.
"""

from collections.abc import Callable
from typing import Any
import numpy as np
from ..models import AppSettings
from .headword_models import OCRLine


def detect_image_separator_candidates(
    gray: np.ndarray,
    reference_line_height: int,
    settings: AppSettings,
    pixel_scale: float = 1.0,
    lower_bound: int = 0,
    *,
    roi_fn: Callable[[int, AppSettings, float], tuple[int, int]],
    otsu_fn: Callable[[np.ndarray], int],
    runs_fn: Callable[[np.ndarray], list[tuple[int, int]]],
    np_module: Any = np,
) -> list[dict[str, Any]]:
    """Detect image-only entry-boundary candidates from blank-to-ink transitions.

    These candidates deliberately contain no OCR text.  They are an independent
    visual source that is later paired *mutually* with OCR lines.  Dense pages
    with no stable whitespace simply emit few/no candidates and fall back to the
    OCR geometry path.
    """
    if gray.size == 0 or gray.ndim < 2:
        return []
    height, width = gray.shape[:2]
    if height < 4 or width < 12:
        return []
    lower = max(0, min(height - 1, int(lower_bound)))
    x0, x1 = roi_fn(width, settings, pixel_scale)
    roi = gray[lower:, x0:x1]
    if roi.size == 0 or roi.shape[0] < 4 or roi.shape[1] < 8:
        return []

    threshold = otsu_fn(roi)
    ink = roi <= threshold
    # Remove only narrow persistent vertical rules; they otherwise make every
    # row appear non-blank.
    if ink.shape[0] >= 3 and ink.shape[1] >= 3:
        persistent = ink.mean(axis=0) >= 0.72
        if persistent.any():
            narrow = np_module.zeros_like(persistent, dtype=bool)
            max_rule_width = max(2, round(ink.shape[1] * 0.025))
            for a, b in runs_fn(persistent):
                if b - a <= max_rule_width:
                    narrow[a:b] = True
            if narrow.any():
                ink = ink.copy(); ink[:, narrow] = False

    row_ink = ink.mean(axis=1).astype(np_module.float64)
    if row_ink.size >= 3:
        padded = np_module.pad(row_ink, (1, 1), mode="edge")
        smooth = np_module.convolve(padded, np_module.ones(3, dtype=np_module.float64) / 3.0, mode="valid")
    else:
        smooth = row_ink.copy()

    line_h = max(3, int(round(reference_line_height)))
    quantization = 1.0 / max(1, ink.shape[1] * 3)
    positive = smooth[smooth > 0]
    low_positive = float(np_module.percentile(positive, 20)) if positive.size else 0.0
    blank_threshold = max(quantization * 2.5, min(0.010, low_positive * 0.45 if low_positive else 0.0025))
    blank_mask = smooth <= blank_threshold
    ink_threshold = max(blank_threshold * 1.8, quantization * 5.0)
    ink_mask = smooth > ink_threshold
    min_blank = max(3, round(line_h * 0.12))
    min_ink = max(2, round(line_h * 0.07))
    configured_safety = max(0, int(getattr(settings, "paddle_separator_safety_px", 2)))
    safety = max(0, round(configured_safety * max(0.5, float(pixel_scale))))

    result: list[dict[str, Any]] = []
    for run_start, run_end in runs_fn(blank_mask):
        if run_end - run_start < min_blank:
            continue
        # The visual boundary is useful only when the blank band is followed by
        # a sustained ink onset soon below it.
        onset: int | None = None
        j = run_end
        max_j = min(len(smooth) - 1, run_end + max(4, round(line_h * 0.32)))
        while j <= max_j:
            e = min(len(smooth), j + min_ink)
            if e - j >= min_ink and (bool(np_module.all(~blank_mask[j:e])) or bool(np_module.all(ink_mask[j:e]))):
                onset = j; break
            j += 1
        if onset is None:
            continue
        onset_y = lower + onset
        blank_bottom = lower + run_end - 1
        boundary_y = int(min(blank_bottom, onset_y - safety))
        boundary_y = max(lower, min(height - 1, boundary_y))
        blank_len = run_end - run_start
        strength = min(1.0, blank_len / max(1.0, line_h * 0.35))
        result.append({
            "y": boundary_y,
            "ink_onset_y": int(onset_y),
            "blank_start_y": int(lower + run_start),
            "blank_end_y": int(blank_bottom),
            "blank_rows": int(blank_len),
            "strength": round(float(strength), 4),
            "analysis_x0": int(x0),
            "analysis_x1": int(x1),
            "threshold": int(threshold),
        })
    return result


def match_ocr_lines_to_image_boundaries(
    lines: list[OCRLine],
    boundaries: list[dict[str, Any]],
    reference_line_height: int,
) -> dict[int, dict[str, Any]]:
    """Mutually pair OCR lines and image boundaries using vertical geometry.

    A match is accepted only when the OCR line chooses the boundary and the
    boundary independently chooses the same OCR line.  This prevents a large
    whitespace region from being attached to the wrong neighbouring line.
    """
    if not lines or not boundaries:
        return {}
    line_h = max(3, int(round(reference_line_height)))
    max_delta = max(6, round(line_h * 0.75))

    def distance(line: OCRLine, boundary: dict[str, Any]) -> float:
        onset = int(boundary.get("ink_onset_y", boundary.get("y", 0)))
        y0, y1 = int(line.box[1]), int(line.box[3])
        # OCR boxes may begin slightly high or include accents.  Distance to the
        # vertical box interval is more stable than top-only distance.
        if y0 <= onset <= y1:
            interval = 0.0
        else:
            interval = float(min(abs(onset - y0), abs(onset - y1)))
        top_delta = abs(onset - y0)
        return interval * 0.65 + top_delta * 0.35

    line_choice: dict[int, int] = {}
    for i, line in enumerate(lines):
        ranked = sorted((distance(line, b), j) for j, b in enumerate(boundaries))
        if ranked and ranked[0][0] <= max_delta:
            line_choice[i] = ranked[0][1]
    boundary_choice: dict[int, int] = {}
    for j, boundary in enumerate(boundaries):
        ranked = sorted((distance(line, boundary), i) for i, line in enumerate(lines))
        if ranked and ranked[0][0] <= max_delta:
            boundary_choice[j] = ranked[0][1]

    matches: dict[int, dict[str, Any]] = {}
    for i, j in line_choice.items():
        if boundary_choice.get(j) != i:
            continue
        item = dict(boundaries[j])
        item["match_method"] = "mutual_nearest_y"
        item["ocr_line_index"] = int(i)
        item["delta_to_box_top"] = int(item.get("ink_onset_y", item["y"])) - int(lines[i].box[1])
        matches[i] = item
    return matches
