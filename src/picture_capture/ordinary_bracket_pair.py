"""Recover CJK entry starts marked by a *matched pair* of printed 【…】.

The physical layout classifier sometimes misses short numbered subentries.
Unlike text recognition, this evidence uses the distinctive left/right
vertical-ink polarity of both square brackets in the headword lane. A single
bracket, quotation inside a definition, or an unmatched ink component is
insufficient to introduce a separator.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from .illustration_detection import _rle_components
from .models import Entry


def _bracket_side(mask: np.ndarray, opening: bool) -> bool:
    height, width = mask.shape
    if width < 8 or height < 16:
        return False
    edge = max(2, round(width * .30))
    top = max(2, round(height * .12))
    middle = mask[round(height * .30):round(height * .70)]
    left = mask[:, 1:edge]
    right = mask[:, width - edge:width - 1]
    mid_left = middle[:, 1:edge]
    mid_right = middle[:, width - edge:width - 1]
    if any(part.size == 0 for part in (left, right, mid_left, mid_right)):
        return False
    dense, sparse = (left, right) if opening else (right, left)
    middle_dense, middle_sparse = (
        (mid_left, mid_right) if opening else (mid_right, mid_left)
    )
    return (
        dense.mean() > .55 and sparse.mean() < .38
        and middle_dense.mean() > .60 and middle_sparse.mean() < .27
        and mask[:top].mean() > .35 and mask[-top:].mean() > .35
    )


def recover_bracketed_ordinary_entries(
    entries: list[Entry],
    image: Image.Image,
    columns,
    body_top: int,
    body_bottom: int,
    line_height: float,
) -> list[Entry]:
    """Supplement entries only from matching opening/closing print glyphs.

    Coordinates are canonical and therefore require an identity page transform.
    Matching pairs must begin in the first ~5.5 text pitches of the column;
    this excludes quoted bracket expressions deeper inside a definition.
    """
    pitch = float(line_height)
    if not 18 <= pitch <= 120:
        return list(entries)
    gray = image.convert("L")
    try:
        result = list(entries)
        for col in columns:
            left, right = int(col.left), int(col.right)
            x0 = max(0, left + round(pitch * .50))
            x1 = min(gray.width, right, left + round(pitch * 13.2))
            y0 = max(0, int(body_top))
            y1 = min(gray.height, int(body_bottom))
            if x1 - x0 < pitch * 8 or y1 <= y0:
                continue
            crop = np.asarray(gray.crop((x0, y0, x1, y1)), dtype=np.uint8)
            ink = crop < 170
            openings, closings = [], []
            for a, b, c, d, area in _rle_components(ink):
                w, h = c - a, d - b
                if not (.35 * pitch <= w <= .95 * pitch
                        and 1.10 * pitch <= h <= 2.20 * pitch
                        and area >= .11 * pitch * pitch):
                    continue
                component = ink[b:d, a:c]
                location = (a + x0, b + y0, c + x0, d + y0)
                if (location[0] - left <= 5.5 * pitch
                        and _bracket_side(component, True)):
                    openings.append(location)
                if _bracket_side(component, False):
                    closings.append(location)
            for ax, ay, _ac, ad in openings:
                paired = any(
                    1.8 * pitch <= bx - ax <= 7.0 * pitch
                    and abs(by - ay) <= .4 * pitch
                    and abs((bd - by) - (ad - ay)) <= .5 * pitch
                    for bx, by, _bc, bd in closings
                )
                if not paired:
                    continue
                proposed_y = max(y0, round(ay - .08 * pitch))
                if any(
                    abs(entry.x - left) <= pitch
                    and abs(entry.y - proposed_y) <= .8 * pitch
                    for entry in result
                ):
                    continue
                result.append(Entry(
                    word="", x=left, y=proposed_y,
                    ocr_source="ordinary_bracket_pair",
                    issue_type="ORDINARY_VISUAL_BRACKET_PAIR",
                ))
        return result
    finally:
        gray.close()
