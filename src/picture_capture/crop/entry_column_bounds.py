from __future__ import annotations

"""Pure column crop bounds, using call-time historical core hooks."""

from collections.abc import Callable
from typing import Any
import numpy as np
from PIL import Image


def entry_crop_box_for_column(
    image: Image.Image, settings: Any, geometry: Any, col: int, y0: int, y1: int,
    *, extra_left: int = 0, extra_right: int = 0,
    source_px_fn: Callable[[int | float], int],
    clamp_fn: Callable[[tuple[int, int, int, int], Image.Image], tuple[int, int, int, int]],
    np_module: Any = np,
) -> tuple[int, int, int, int]:
    """Whole-entry crop box with gutters divided between neighboring columns."""
    col = max(0, min(len(geometry.column_starts) - 1, int(col)))
    canonical_width = geometry.transform.canonical_size(image.size)[0]
    extra_left_px = max(
        0, source_px_fn(int(extra_left)),
    )
    extra_right_px = max(
        0, source_px_fn(int(extra_right)),
    )

    # Use the robust width of the ordinary columns. derive_geometry intentionally
    # lets the final column extend to the page edge for detection, which is not
    # the correct width for dictionary-entry cropping.
    widths = list(geometry.column_widths[:-1]) if len(geometry.column_widths) > 1 else list(geometry.column_widths)
    nominal_width = max(1, round(float(np_module.median(widths or geometry.column_widths or [image.width]))))
    gutter_px = max(
        0,
        source_px_fn(settings.gutter),
    )
    half_gutter = gutter_px // 2
    outer_margin = max(0, geometry.column_starts[0] // 2)

    left_margin = outer_margin if col == 0 else half_gutter
    right_margin = outer_margin if col == len(geometry.column_starts) - 1 else gutter_px - half_gutter
    path_left, path_right = geometry.x_bounds(col, y0, y1)
    canonical_size = geometry.transform.canonical_size(image.size)
    canonical_box = (
        path_left - left_margin - extra_left_px,
        y0,
        path_right + nominal_width + right_margin + extra_right_px,
        y1,
    )
    canonical_box = (
        max(0, canonical_box[0]),
        max(0, canonical_box[1]),
        min(canonical_size[0], canonical_box[2]),
        min(canonical_size[1], canonical_box[3]),
    )
    return clamp_fn(geometry.transform.canonical_box_to_source(canonical_box, image.size), image)

