from __future__ import annotations

"""Recover oversized CJK display heads as structural block starts.

Large dictionary heads are not ordinary text lines. Detecting them through a
vertical line projection is fragile: disconnected radicals can split one glyph,
and a glyph close to the following definition can merge into an over-tall run.

This detector therefore works on connected ink components in the column's left
text-start strip. It first separates *large-glyph fragments* from normal text
components, then groups only those fragments into a glyph-sized object. This is
important when a display head sits only one or two pixels above its definition:
the following normal text must never be absorbed into the large glyph.
"""

from typing import Any

import numpy as np
from PIL import Image

from .image_utils import normalize_page_rgb
from .models import AppSettings, Entry
from .ordinary_postprocess import _separator_near_next_line
from .ordinary_visual import (
    _body_lane,
    _column_band_gray,
    _components,
    _duplicate,
    _first_ink_lines,
    _inside_sections,
    _otsu,
    _source_edge,
)


def _character_height(settings: AppSettings) -> int:
    return max(8, int(round(float(getattr(settings, "character_height", 26) or 26))))


def _indent_type(settings: AppSettings) -> str:
    value = str(getattr(settings, "profile_indent_type", "") or "").strip().lower()
    if value in {"headword", "body"}:
        return value
    return (
        "body"
        if bool(getattr(settings, "profile_cjk_brackets_in_body", False))
        else "headword"
    )


def _analysis_width(column_width: int, character_height: int) -> int:
    return max(1, min(
        int(column_width),
        max(96, round(character_height * 6.25), round(column_width * 0.28)),
    ))


def _vertical_overlap(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    overlap = max(0, min(left[3], right[3]) - max(left[1], right[1]))
    return overlap / float(max(1, min(left[3] - left[1], right[3] - right[1])))


def _horizontal_overlap(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    overlap = max(0, min(left[2], right[2]) - max(left[0], right[0]))
    return overlap / float(max(1, min(left[2] - left[0], right[2] - right[0])))


def _horizontal_gap(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> int:
    if left[2] < right[0]:
        return right[0] - left[2]
    if right[2] < left[0]:
        return left[0] - right[2]
    return 0


def _vertical_gap(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> int:
    if left[3] < right[1]:
        return right[1] - left[3]
    if right[3] < left[1]:
        return left[1] - right[3]
    return 0


def _merge_box(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return (
        min(left[0], right[0]),
        min(left[1], right[1]),
        max(left[2], right[2]),
        max(left[3], right[3]),
    )


def _glyph_neighbors(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
    character_height: int,
) -> bool:
    if (
        _vertical_overlap(left, right) >= 0.34
        and _horizontal_gap(left, right) <= character_height * 0.72
    ):
        return True
    if (
        _horizontal_overlap(left, right) >= 0.28
        and _vertical_gap(left, right) <= character_height * 0.48
    ):
        return True
    return False


def _large_fragment(
    box: tuple[int, int, int, int],
    character_height: int,
) -> bool:
    """Reject normal text components before radical grouping begins."""
    x0, y0, x1, y1 = box
    width = x1 - x0
    height = y1 - y0
    # Long definition strokes/rows must not become radicals even if they sit
    # immediately below a large head. Real large-head fragments stay within a
    # few normal character cells and have at least one enlarged dimension.
    if width > character_height * 3.20 or height > character_height * 3.45:
        return False
    if height < character_height * 0.42:
        return False
    return bool(
        height >= character_height * 1.10
        or (
            width >= character_height * 1.15
            and height >= character_height * 0.62
        )
    )


def _group_components(
    boxes: list[tuple[int, int, int, int]],
    character_height: int,
) -> list[tuple[int, int, int, int]]:
    """Transitive grouping only among already-qualified large fragments."""
    groups = list(boxes)
    changed = True
    while changed:
        changed = False
        output: list[tuple[int, int, int, int]] = []
        while groups:
            current = groups.pop(0)
            merged_any = True
            while merged_any:
                merged_any = False
                remaining: list[tuple[int, int, int, int]] = []
                for candidate in groups:
                    if _glyph_neighbors(current, candidate, character_height):
                        current = _merge_box(current, candidate)
                        merged_any = True
                        changed = True
                    else:
                        remaining.append(candidate)
                groups = remaining
            output.append(current)
        groups = output
    return groups


def _candidate_boxes(ink: np.ndarray, character_height: int) -> list[tuple[int, int, int, int]]:
    raw: list[tuple[int, int, int, int]] = []
    minimum_area = max(3, round(character_height * character_height * 0.012))
    for x0, y0, x1, y1, area in _components(ink):
        if area < minimum_area:
            continue
        box = (int(x0), int(y0), int(x1), int(y1))
        if _large_fragment(box, character_height):
            raw.append(box)

    groups = _group_components(raw, character_height)
    result: list[tuple[int, int, int, int]] = []
    for box in groups:
        x0, y0, x1, y1 = box
        width = x1 - x0
        height = y1 - y0
        if not (character_height * 1.38 <= height <= character_height * 3.45):
            continue
        if not (character_height * 0.72 <= width <= character_height * 3.80):
            continue
        aspect = height / float(max(1, width))
        if not 0.42 <= aspect <= 2.80:
            continue
        roi = ink[y0:y1, x0:x1]
        if roi.size == 0 or float(roi.mean()) < 0.025:
            continue
        result.append(box)
    return result


def recover_cjk_oversized_heads(
    image: Image.Image,
    entries: list[Entry],
    geometry: Any,
    settings: AppSettings,
    page_sections: list[Any] | None = None,
) -> list[Entry]:
    """Recover display-head boundaries without requiring a text-line run."""
    if not bool(getattr(settings, "profile_cjk_allow_single_headword", True)):
        return list(entries)

    source = normalize_page_rgb(image)
    character_height = _character_height(settings)
    indent_type = _indent_type(settings)
    sign = 1.0 if indent_type == "headword" else -1.0
    recovered = list(entries)

    for column in range(len(geometry.column_starts)):
        top = max(0, int(geometry.top))
        bottom = min(source.height, int(geometry.bottom))
        full_band = _column_band_gray(source, geometry, column, top, bottom)
        if full_band.size == 0:
            continue
        width = _analysis_width(full_band.shape[1], character_height)
        gray = full_band[:, :width]
        ink = gray <= _otsu(gray)

        normal_lines = _first_ink_lines(ink, character_height)
        body_center = _body_lane(normal_lines, ink.shape[1], character_height)
        if body_center is None:
            continue

        for x0, y0, x1, y1 in _candidate_boxes(ink, character_height):
            signed_offset = sign * (float(x0) - float(body_center))
            if not (
                character_height * 0.16
                <= signed_offset
                <= character_height * 4.75
            ):
                continue
            separator = _separator_near_next_line(ink, int(y0), float(character_height))
            if separator is None:
                continue
            source_y = int(top) + int(separator)
            if not _inside_sections(source_y, page_sections):
                continue
            duplicate_tolerance = max(5, round(character_height * 0.58))
            if _duplicate(recovered, geometry, column, source_y, duplicate_tolerance):
                continue
            marker_x, _direction = _source_edge(geometry, column, source_y)
            recovered.append(Entry(
                word="",
                x=int(marker_x),
                y=int(source_y),
                confidence=0.98,
                ocr_source="ordinary_visual_head",
                issue_type="ORDINARY_BLOCK_OVERSIZED_HEAD",
                ocr_visual_run_height=float(y1 - y0),
                ocr_line_height_reference=float(character_height),
                ocr_single_cjk=True,
                ocr_oversized_cjk=True,
            ))
    return recovered
