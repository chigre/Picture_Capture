\
from __future__ import annotations

"""Observed character-height recovery for fallback Layout estimates.

Dense dictionary pages can make layout text boxes merge vertically, leaving the
reliable detector on its ``fallback=character_height`` projection path with an
underestimated page-height heuristic.  This module keeps the established
physical-row measurement as ordinary static logic: only an estimate already
marked for that fallback is eligible, and only ``character_height`` plus method
provenance may change.
"""

from dataclasses import replace
from typing import Any

import numpy as np
from PIL import Image, ImageOps


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    values = np.asarray(mask, dtype=bool)
    if values.ndim != 1 or values.size == 0:
        return []
    padded = np.pad(values.astype(np.int8), (1, 1), constant_values=0)
    changes = np.diff(padded)
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    return [(int(a), int(b)) for a, b in zip(starts, ends) if b > a]


def _fill_tiny_vertical_gaps(active: np.ndarray, maximum_gap: int = 1) -> np.ndarray:
    result = np.asarray(active, dtype=bool).copy()
    if maximum_gap <= 0 or result.size < 3:
        return result
    false_runs = _runs(~result)
    for start, end in false_runs:
        if start > 0 and end < result.size and end - start <= maximum_gap:
            result[start:end] = True
    return result


def observed_character_height(
    image: Image.Image,
    settings: Any,
    estimate: Any,
    backend: Any,
) -> tuple[int | None, dict[str, float | int]]:
    """Estimate ordinary glyph-ink height from physical row-projection bands."""
    source = image.convert("RGB")
    gray = np.asarray(ImageOps.grayscale(source), dtype=np.uint8)
    ink = backend.analysis_ink_mask(gray, settings)
    if ink.ndim != 2 or ink.size == 0 or not np.any(ink):
        return None, {"samples": 0}

    height, width = ink.shape
    current = max(1, int(getattr(estimate, "character_height", 1) or 1))
    top = max(0, min(height - 1, int(getattr(estimate, "start_y", 0) or 0)))
    bottom = max(top + 1, min(height, int(getattr(estimate, "bottom_y", height) or height)))
    column_width = max(24, int(getattr(estimate, "column_width", width) or width))
    starts = list(getattr(estimate, "column_starts", ()) or ())
    if not starts:
        count = max(1, int(getattr(estimate, "columns", 1) or 1))
        x0 = max(0, int(getattr(estimate, "manual_x", 0) or 0))
        gutter = max(0, int(getattr(estimate, "gutter", 0) or 0))
        starts = [x0 + index * (column_width + gutter) for index in range(count)]

    # Same broad leading domain used by Page Design.  It is wide enough to make
    # row presence robust while still avoiding ragged line endings.
    leading_width = max(
        24,
        min(column_width, max(round(column_width * 0.42), round(current * 7.0), 96)),
    )

    lower = max(6, int(round(current * 0.65)))
    upper = max(lower + 2, int(round(current * 2.10)))
    heights: list[int] = []
    for raw_left in starts:
        left = max(0, min(width - 1, int(raw_left)))
        right = max(left + 1, min(width, left + leading_width))
        strip = ink[top:bottom, left:right]
        if strip.size == 0:
            continue
        row_ink = np.asarray(strip, dtype=np.uint8).sum(axis=1)
        threshold = max(2, int(round(strip.shape[1] * 0.003)))
        active = _fill_tiny_vertical_gaps(row_ink >= threshold, 1)
        for y0, y1 in _runs(active):
            run_height = int(y1 - y0)
            if lower <= run_height <= upper:
                heights.append(run_height)

    if len(heights) < 8:
        return None, {"samples": len(heights)}

    values = np.asarray(heights, dtype=float)
    center = float(np.median(values))
    deviation = np.abs(values - center)
    mad = float(np.median(deviation)) if deviation.size else 0.0
    tolerance = max(2.0, 3.5 * mad)
    kept = values[deviation <= tolerance]
    if kept.size < 8:
        return None, {"samples": int(kept.size), "median": center, "mad": mad}

    center = float(np.median(kept))
    q10, q90 = (float(v) for v in np.percentile(kept, [10, 90]))
    spread = q90 - q10
    if center <= 0 or spread > max(4.0, center * 0.18):
        return None, {
            "samples": int(kept.size),
            "median": center,
            "spread": spread,
        }

    return max(1, int(round(center))), {
        "samples": int(kept.size),
        "median": center,
        "spread": spread,
    }


def apply_character_height_fallback(
    image: Image.Image,
    settings: Any,
    estimate: Any,
    backend: Any,
) -> Any:
    """Apply the established fallback correction without mutating raw estimates."""
    method = str(getattr(estimate, "method", "") or "")
    if "fallback=character_height" not in method:
        return estimate

    observed, stats = observed_character_height(
        image,
        settings,
        estimate,
        backend,
    )
    if observed is None:
        return estimate

    current = max(1, int(getattr(estimate, "character_height", 1) or 1))
    ratio = float(observed) / float(current)
    # Small differences are harmless and should not churn page parameters.
    if 0.82 <= ratio <= 1.22:
        return estimate

    updated = replace(estimate, character_height=int(observed))
    updated.method = (
        f"{method}+observed_character_height={int(observed)}"
        f"(n={int(stats.get('samples', 0))})"
    )
    return updated


__all__ = ["apply_character_height_fallback", "observed_character_height"]
