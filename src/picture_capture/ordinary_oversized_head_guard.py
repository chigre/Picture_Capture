"""Remove duplicate ordinary separators that fall *inside* oversized CJK heads.

The Layout row detector can split one very large ideograph into several row
roles.  A connected, tall ink component at the left-side headword lane is a
stronger physical constraint: only its top can start an entry.  This is a
conservative veto of duplicate candidates, not a headword generator.
"""
from __future__ import annotations

from PIL import Image, ImageFilter
import numpy as np


def _tall_head_components(image: Image.Image, left: int, right: int, pitch: float):
    from .illustration_detection import _rle_components

    x0 = max(0, int(left + max(8, round(pitch))))
    x1 = min(image.width, int(min(right, left + max(130, round(7.7 * pitch)))))
    if x1 - x0 < 30:
        return []
    crop = image.crop((x0, 0, x1, image.height)).convert("L")
    try:
        ink = np.asarray(crop, dtype=np.uint8) < 155
        bitmap = Image.fromarray((ink.astype(np.uint8) * 255), "L")
        try:
            linked = np.asarray(bitmap.filter(ImageFilter.MaxFilter(3))) > 0
        finally:
            bitmap.close()
    finally:
        crop.close()
    heads = []
    for a, top, b, bottom, _area in _rle_components(linked):
        width, height = b - a, bottom - top
        if (height >= 2.3 * pitch and width >= 1.9 * pitch
                and a + x0 <= left + 4.5 * pitch
                and width <= height * 1.8):
            heads.append((top, bottom))
    return heads


def suppress_oversized_head_fragment_entries(
    entries, image: Image.Image, column_starts, column_widths, line_height: float,
):
    """Keep each oversized glyph's earliest candidate, never infer new lines.

    A candidate is removed only when it lies in a tall connected headword
    already represented by another entry near the component's upper edge.
    This cannot remove a lone candidate, and is not applied to OCR modes.
    """
    pitch = float(line_height)
    if pitch < 8 or len(entries) < 3:
        return list(entries)
    groups = [[] for _ in column_starts]
    for entry in entries:
        if not groups:
            return list(entries)
        index = min(range(len(column_starts)), key=lambda i: abs(entry.x - column_starts[i]))
        groups[index].append(entry)

    removed = set()
    for index, group in enumerate(groups):
        ordered = sorted(group, key=lambda item: item.y)
        if len(ordered) < 2 or not any(
            b.y - a.y < 1.6 * pitch for a, b in zip(ordered, ordered[1:])
        ):
            continue
        left = int(column_starts[index])
        right = left + int(column_widths[index])
        for top, bottom in _tall_head_components(image, left, right, pitch):
            within = [
                item for item in ordered
                if top - .7 * pitch <= item.y <= bottom + .3 * pitch
            ]
            anchored = [item for item in within if abs(item.y - top) <= .75 * pitch]
            if len(within) < 2 or not anchored:
                continue
            keep = min(anchored, key=lambda item: abs(item.y - top))
            for item in within:
                if item is not keep:
                    removed.add(id(item))
    return [entry for entry in entries if id(entry) not in removed]
