from __future__ import annotations

"""Literal source-pixel, half-open PIL boxes for single-word export.

Original processing_core entrypoints retain live column-index, source-pixel
rounding and clamp hooks. No crop file publishing happens in this module.
"""

from collections.abc import Callable
from typing import Any
from PIL import Image
from ..models import AppSettings, Entry


def clamp_box(box: tuple[int, int, int, int], image: Image.Image) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    left = min(image.width - 1, max(0, int(left)))
    top = min(image.height - 1, max(0, int(top)))
    right = min(image.width, max(left + 1, int(right)))
    bottom = min(image.height, max(top + 1, int(bottom)))
    return left, top, right, bottom


def line_box(
    entry: Entry, geometry: Any, image: Image.Image, settings: AppSettings, *,
    column_fn: Callable[[int, Any, int], int],
    source_px_fn: Callable[[int | float], int],
    clamp_fn: Callable[[tuple[int, int, int, int], Image.Image], tuple[int, int, int, int]],
) -> tuple[int, int, int, int]:
    _entry_u, entry_v = geometry.source_to_canonical(entry.x, entry.y)
    idx = column_fn(entry.x, geometry, entry.y)
    canonical_width = geometry.transform.canonical_size(image.size)[0]
    row_padding = source_px_fn(settings.row_padding)
    character_height = source_px_fn(settings.character_height)
    vertical_pad = abs(row_padding)
    height = character_height + 2 * abs(row_padding)
    width = round(geometry.column_widths[idx] * min(100.0, max(1.0, settings.crop_width_percent)) / 100.0)
    left_extension = round(geometry.column_starts[0] * 0.5)
    tracked_x = geometry.x_at(idx, entry_v)
    canonical_box = (
        tracked_x - left_extension,
        entry_v - vertical_pad,
        tracked_x + width,
        entry_v - vertical_pad + height,
    )
    return clamp_fn(geometry.transform.canonical_box_to_source(canonical_box, geometry.source_size), image)
