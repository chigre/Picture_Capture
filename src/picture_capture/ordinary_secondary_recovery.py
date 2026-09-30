from __future__ import annotations

"""Recover secondary entry rows after a page has proven an indented entry lane.

The first ordinary visual pass is intentionally conservative: it requires a
repeated X-cluster with similar leading patches. Real dictionaries often prefix
some subentries with superscript numbers, which shifts the first ink far enough
to split one semantic entry lane into two small X clusters. Once several
``ordinary_visual_lane`` rows have already proved the page polarity, those
numbered variants should not have to prove a second independent cluster.

This pass remains OCR-independent. It uses only normalized indentation relative
to each column's body lane, normal line height, and a clean separator immediately
before the row.
"""

from typing import Any

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb
from .models import AppSettings, Entry
from .ordinary_visual import (
    _body_lane,
    _column_band_gray,
    _duplicate,
    _entry_column,
    _first_ink_lines,
    _inside_sections,
    _otsu,
    _source_edge,
)
from .ordinary_postprocess import _separator_near_next_line


def _character_height(settings: AppSettings) -> int:
    return max(8, int(round(float(getattr(settings, "character_height", 26) or 26))))


def _column_data(source: Image.Image, geometry: Any, settings: AppSettings, column: int):
    character_height = _character_height(settings)
    top = max(0, int(geometry.top))
    bottom = min(source.height, int(geometry.bottom))
    band = _column_band_gray(source, geometry, column, top, bottom)
    if band.size == 0:
        return top, np.zeros((0, 0), dtype=bool), [], None, float(character_height)
    ink = band <= _otsu(band)
    lines = _first_ink_lines(ink, character_height)
    baseline = _body_lane(lines, ink.shape[1], character_height)
    heights = [int(line.y1) - int(line.y0) for line in lines if int(line.y1) > int(line.y0)]
    reference = float(np.median(np.asarray(heights, dtype=float))) if heights else float(character_height)
    reference = max(6.0, min(float(character_height) * 1.15, reference))
    return top, ink, lines, baseline, reference


def _line_after_marker(lines: list[Any], local_y: int, reference: float):
    lower = int(local_y) - max(2, round(reference * 0.10))
    upper = int(local_y) + max(8, round(reference * 1.40))
    candidates = [line for line in lines if lower <= int(line.y0) <= upper]
    if not candidates:
        return None
    forward = [line for line in candidates if int(line.y0) >= int(local_y)]
    pool = forward or candidates
    return min(pool, key=lambda line: abs(int(line.y0) - int(local_y)))


def recover_proven_secondary_lane_variants(
    image: Image.Image,
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    page_sections: list[Any] | None = None,
) -> list[Entry]:
    """Recover nearby indented variants after visual entry lanes are proven."""
    proven_entries = [
        entry for entry in entries
        if str(getattr(entry, "ocr_source", "") or "") == "ordinary_visual_lane"
    ]
    if len(proven_entries) < 3:
        return list(entries)
    if not bool(getattr(settings, "profile_cjk_allow_bracketed_headword", True)):
        return list(entries)

    source = normalize_page_rgb(image)
    data = {
        column: _column_data(source, geometry, settings, column)
        for column in range(len(geometry.column_starts))
    }

    # Learn normalized indentation from the rows that already survived the
    # stricter repeated-marker detector. This lets one page/column teach another
    # without hard-coding pixel offsets or DPI.
    normalized_offsets: list[float] = []
    for entry in proven_entries:
        column = _entry_column(entry, geometry)
        top, _ink, lines, baseline, reference = data[column]
        if baseline is None or reference <= 0:
            continue
        _u, marker_v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        line = _line_after_marker(lines, int(marker_v) - int(top), reference)
        if line is None:
            continue
        normalized_offsets.append((float(line.start) - float(baseline)) / float(reference))
    if len(normalized_offsets) < 3:
        return list(entries)

    center = float(np.median(np.asarray(normalized_offsets, dtype=float)))
    # Prefix numbers can shift first ink by roughly half to one full text
    # character. Keep this broader than the initial X-cluster detector, but far
    # narrower than arbitrary paragraph indentation.
    lower_offset = max(0.75, center - 0.75)
    upper_offset = min(4.20, center + 1.00)

    recovered = list(entries)
    for column, (top, ink, lines, baseline, reference) in data.items():
        if baseline is None or ink.size == 0:
            continue
        duplicate_tolerance = max(4, round(reference * 0.45))
        for line in lines:
            line_height = int(line.y1) - int(line.y0)
            if not (reference * 0.65 <= line_height <= reference * 1.35):
                continue
            offset = (float(line.start) - float(baseline)) / float(reference)
            if not (lower_offset <= offset <= upper_offset):
                continue
            separator = _separator_near_next_line(ink, int(line.y0), reference)
            if separator is None:
                continue
            source_y = int(top) + int(separator)
            if not _inside_sections(source_y, page_sections):
                continue
            if _duplicate(recovered, geometry, column, source_y, duplicate_tolerance):
                continue
            marker_x, _direction = _source_edge(geometry, column, source_y)
            recovered.append(Entry(
                word="",
                x=int(marker_x),
                y=int(source_y),
                confidence=0.93,
                ocr_source="ordinary_visual_lane",
                issue_type="ORDINARY_PROVEN_INDENT_VARIANT",
            ))
    return recovered
