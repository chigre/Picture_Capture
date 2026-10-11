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
from .visual_boundary_locator import safe_gap_above


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
    *,
    transform=None,
    source_size: tuple[int, int] | None = None,
) -> list[Entry]:
    """Supplement entries only from matching opening/closing print glyphs.

    Detect on a canonical image, and inverse-map accepted boundaries to the
    source image when a transform is supplied (RTL / rotated dictionaries).
    Matching pairs must begin in the first ~5.5 text pitches of the column;
    this excludes quoted bracket expressions deeper inside a definition.
    """
    pitch = float(line_height)
    if not 12 <= pitch <= 120:
        return list(entries)
    gray = image.convert("L")
    try:
        result = list(entries)
        for col in columns:
            left, right = int(col.left), int(col.right)
            # Brackets in real 三民 / XDHYCD pages start at (or even a few
            # pixels before) the registered column boundary. The old +0.5h
            # crop omitted entire opening glyphs and whole runs of entries.
            x0 = max(0, left - round(pitch * .25))
            x1 = min(gray.width, right, left + round(pitch * 21.0))
            y0 = max(0, int(body_top))
            y1 = min(gray.height, int(body_bottom))
            if x1 - x0 < pitch * 8 or y1 <= y0:
                continue
            crop = np.asarray(gray.crop((x0, y0, x1, y1)), dtype=np.uint8)
            ink = crop < 170
            openings, closings = [], []
            for a, b, c, d, area in _rle_components(ink):
                w, h = c - a, d - b
                if not (.32 * pitch <= w <= 1.25 * pitch
                        and .72 * pitch <= h <= 2.50 * pitch
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
                    .8 * pitch <= bx - ax <= 18.0 * pitch
                    and abs(by - ay) <= .5 * pitch
                    and abs((bd - by) - (ad - ay)) <= .7 * pitch
                    for bx, by, _bc, bd in closings
                )
                if not paired:
                    continue
                # Find an actual white line gap, never inside the bracket ink.
                # Earlier callers used an unconditional 0.08*pitch offset.
                proposed_y = y0 + safe_gap_above(crop, ay - y0, pitch)
                def same_boundary(entry):
                    if transform is not None and source_size is not None:
                        existing_x, existing_y = transform.source_to_canonical_point(
                            int(entry.x), int(entry.y), source_size,
                        )
                    else:
                        existing_x, existing_y = int(entry.x), int(entry.y)
                    return (
                        abs(existing_x - left) <= pitch
                        and abs(existing_y - proposed_y) <= .8 * pitch
                    )
                if any(same_boundary(entry) for entry in result):
                    continue
                if transform is not None and source_size is not None:
                    source_x, source_y = transform.canonical_to_source_point(
                        left, proposed_y, source_size,
                    )
                else:
                    source_x, source_y = left, proposed_y
                result.append(Entry(
                    word="", x=int(source_x), y=int(source_y),
                    ocr_source="ordinary_bracket_pair",
                    issue_type="ORDINARY_VISUAL_BRACKET_PAIR",
                ))
        return result
    finally:
        gray.close()
