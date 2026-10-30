"""Strict R4.2 SECTION v2 ownership from original-image coordinates.

Unlike section_index_for_v (which deliberately assigns nearest lanes for UI),
this security-sensitive attribution NEVER guesses across gaps or malformed
saved boundaries. A single corrupt, missing or overlapping section row makes
the entire snapshot unprovable.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from ..geometry.coordinate_space import SOURCE_COORDINATE_SPACE
from ..geometry.layout_transform import LayoutTransform
from ..persistence.page_sections import PAGE_SECTIONS_FORMAT


def _point(value: Any) -> tuple[int, int] | None:
    if (
        not isinstance(value, (list, tuple)) or len(value) != 2
        or any(type(n) is not int for n in value)
    ):
        return None
    return value[0], value[1]


def _v(value: Any, transform: LayoutTransform, source_size: tuple[int, int]) -> int | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    a, b = _point(value[0]), _point(value[1])
    if a is None or b is None:
        return None
    u, v = transform.source_to_canonical_point(*a, source_size)
    u2, v2 = transform.source_to_canonical_point(*b, source_size)
    if v != v2:
        return None
    cw, ch = transform.canonical_size(source_size)
    if (u, u2) != (0, cw - 1) or not (0 <= v <= ch):
        return None
    expected = transform.canonical_segment_to_source((0, v), (cw - 1, v), source_size)
    if (a, b) != expected:
        return None
    return v


def section_key_for_source_point(
    image_path: Path, section_path: Path, x: int, y: int,
) -> str | None:
    """Return exact 1-based SECTION identity or None on *any* uncertainty.

    Uses saved v2 source-coordinate line segments, strict layout transform
    and actual EXIF-oriented image dimensions. Boundaries use [top, bottom).
    Adjacent sections are unambiguous; gaps and outside points are unknown.
    """
    if type(x) is not int or type(y) is not int:
        return None
    try:
        payload = json.loads(Path(section_path).read_text("utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("format") != PAGE_SECTIONS_FORMAT
            or type(payload.get("version")) is not int
            or payload["version"] != 2
            or payload.get("coordinate_space") != SOURCE_COORDINATE_SPACE
            or type(payload.get("source_width")) is not int
            or type(payload.get("source_height")) is not int
            or not isinstance(payload.get("sections"), list)
            or not payload["sections"]
        ):
            return None
        with Image.open(image_path) as opened:
            source_size = ImageOps.exif_transpose(opened).size
        if (
            source_size != (payload["source_width"], payload["source_height"])
            or not (0 <= x < source_size[0] and 0 <= y < source_size[1])
        ):
            return None
        transform = LayoutTransform(payload.get("layout_transform_internal"))
        spans: list[tuple[int, int, int]] = []
        for index, row in enumerate(payload["sections"], 1):
            if (
                not isinstance(row, dict)
                or type(row.get("index")) is not int
                or row["index"] != index
            ):
                return None
            top = _v(row.get("top_source_segment_xyxy"), transform, source_size)
            bottom = _v(row.get("bottom_source_segment_xyxy"), transform, source_size)
            if top is None or bottom is None or bottom <= top:
                return None
            if spans and top < spans[-1][2]:
                return None
            spans.append((index, top, bottom))
        _u, v = transform.source_to_canonical_point(x, y, source_size)
        matches = [index for index, top, bottom in spans if top <= v < bottom]
        return f"section-{matches[0]}" if len(matches) == 1 else None
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        return None
