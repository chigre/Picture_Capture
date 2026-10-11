"""Correct page-coherent separators that slice through oversized printed glyphs.

Unprocessed dictionary scans can have per-page optical positioning differences:
the physical row detector occasionally returns a Y about one ordinary text
pitch *inside* a large initial headword. Looking for black ink above the marker
and a local preceding white band yields an image-supported page-level offset.

No saved PDIC, dictionary name, OCR, ground-truth coordinates, or learned
per-dictionary pixel constant is used. The shift is applied ONLY when several
same-page printed glyphs independently support a consistent correction.
"""
from __future__ import annotations

from dataclasses import replace
import statistics

import numpy as np
from PIL import Image

from .entry_classification import get_entry_classification, register_entry_classification
from .models import Entry


def _crossing_candidate(
    gray: np.ndarray, x: int, y: int, line_height: float,
) -> int | None:
    height, width = gray.shape
    pitch = max(8.0, float(line_height))
    y = int(y)
    xl = max(0, int(x))
    xr = min(width, xl + max(12, round(pitch * 1.8)))
    if xr <= xl or y - round(pitch * 1.8) < 0 or y + 5 >= height:
        return None
    ink = gray[:, xl:xr] < 150
    r = max(4, round(pitch * .42))
    # A true separator at the *top* of a glyph has no substantial ink above.
    # A line crossing a glyph has substantial ink on both sides of its Y.
    upper = float(ink[max(0, y - r):max(0, y - 3)].mean())
    crossing = float(ink[max(0, y - 3):y + 5].mean())
    if upper <= .105 or crossing <= .14:
        return None

    low = max(0, y - round(pitch * 1.8))
    high = max(low, y - round(pitch * .45))
    coverage = ink[low:high].mean(axis=1)
    rows = coverage < .045
    runs: list[tuple[int, int]] = []
    start = None
    for i, white in enumerate(rows):
        if white and start is None:
            start = i
        if start is not None and (not white or i == len(rows) - 1):
            end = i if not white else i + 1
            if end - start >= max(3, pitch * .15):
                runs.append((low + start, low + end))
            start = None
    if not runs:
        return None

    # Use the closest *white* interval to one observed normal line before Y;
    # never simply subtract a hard-coded number of pixels from every marker.
    best = min(runs, key=lambda pair: abs((pair[0] + pair[1]) * .5 - (y - pitch)))
    corrected = round((best[0] + best[1]) * .5)
    if not (.35 * pitch <= y - corrected <= 1.75 * pitch):
        return None
    return y - corrected


def adjust_page_coherent_crossing_separators(
    entries: list[Entry], image: Image.Image, line_height: float,
) -> tuple[list[Entry], int]:
    """Return adjusted entries and the measured page shift, or unchanged input.

    A minority of strong observations is enough because one large glyph may
    be ink-disconnected at the same Y as another. But all supported offsets
    must agree; if evidence conflicts the page remains untouched.
    """
    if not entries or line_height < 9:
        return list(entries), 0
    with image.convert("L") as gray_image:
        gray = np.asarray(gray_image, dtype=np.uint8)
        supported = [
            shift
            for entry in entries
            if (shift := _crossing_candidate(
                gray, int(entry.x), int(entry.y), line_height,
            )) is not None
        ]
    if not supported or len(supported) / len(entries) < .22:
        return list(entries), 0
    shift = int(round(statistics.median(supported)))
    mad = statistics.median(abs(value - shift) for value in supported)
    if mad > .30 * line_height:
        return list(entries), 0

    shifted = []
    for entry in entries:
        old_meta = get_entry_classification(entry)
        revised = replace(entry, y=max(0, int(entry.y) - shift))
        register_entry_classification(
            revised, entry_source=old_meta.entry_source,
            entry_scale=old_meta.entry_scale,
            detected_head_height=old_meta.detected_head_height,
            manual_override=old_meta.manual_override,
            auto_entry_source=old_meta.auto_entry_source,
            auto_entry_scale=old_meta.auto_entry_scale,
        )
        shifted.append(revised)
    return shifted, shift
