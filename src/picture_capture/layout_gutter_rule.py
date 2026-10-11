"""Detect ruled dictionary gutters even when the vertical line tilts.

This shared pixel-only primitive belongs to both column geometry inference
and later physical first-X measurement. It never edits the source image.
"""
from __future__ import annotations

import numpy as np


def gutter_divider_right_edge(
    ink: np.ndarray,
    *,
    body_top: int,
    body_bottom: int,
    corridor_left: int,
    corridor_right: int,
    reference: float,
) -> int | None:
    """Find a *slanted* printed divider in the inter-column gutter.

    Whole-page X-column persistence misses diagonal rules (e.g., a rule that
    drifts 7px from page top to bottom). Here we locate an almost-continuous
    single-pixel stroke in successive vertical tiles and require its X position
    to form one coherent track. Only a *gutter*, never legitimate word ink, is
    eligible. Return the right edge of that stroke plus a tiny safety margin.
    """
    if ink.ndim != 2 or ink.size == 0:
        return None
    height, width = ink.shape
    left = max(0, min(width, int(corridor_left)))
    right = max(left, min(width, int(corridor_right)))
    top = max(0, min(height, int(body_top)))
    bottom = max(top, min(height, int(body_bottom)))
    ref = max(6.0, float(reference))
    if right - left < max(8, round(ref * .45)) or bottom - top < ref * 8:
        return None

    tile = max(44, round(ref * 3.0))
    peaks: list[int] = []
    eligible = 0
    for y in range(top, bottom, tile):
        band = ink[y:min(bottom, y + tile), left:right]
        if band.shape[0] < tile * .42:
            continue
        eligible += 1
        density = np.asarray(band, dtype=np.uint8).mean(axis=0)
        peak = int(np.argmax(density))
        if float(density[peak]) >= .50:
            peaks.append(left + peak)
    if eligible < 4 or len(peaks) < max(4, round(eligible * .55)):
        return None
    values = np.asarray(peaks, dtype=float)
    center = float(np.median(values))
    inliers = values[np.abs(values - center) <= max(4.0, ref * .18)]
    if len(inliers) < max(4, round(eligible * .50)):
        return None
    return int(max(inliers)) + max(2, round(ref * .10))
