from __future__ import annotations

"""Literal-pixel top/bottom bounds for whole-entry crops.

The historical processing_core callables continue to supply live geometry,
special-page path, and source-pixel converters at the original import paths.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from PIL import Image
from ..models import AppSettings


def special_bounds(
    root: Path, page_stem: str, geometry: Any,
    *, special_path_fn: Callable[[Path], Path],
) -> tuple[int, int]:
    path = special_path_fn(root)
    if not path.exists():
        return geometry.top, geometry.bottom
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        fields = raw.split("\t")
        if fields and fields[0] == page_stem:
            top = int(fields[1]) if len(fields) > 1 and fields[1].strip() else geometry.top
            bottom = int(fields[2]) if len(fields) > 2 and fields[2].strip() else geometry.bottom
            return max(0, top), max(top + 1, bottom)
    return geometry.top, geometry.bottom


def entry_crop_bounds(
    image: Image.Image, settings: AppSettings, *, top_y: int | None = None, bottom_y: int | None = None,
    root: Path | None = None, page_stem: str = "",
    geometry_fn: Callable[..., Any],
    special_bounds_fn: Callable[[Path, str, Any], tuple[int, int]],
    source_px_fn: Callable[[int | float], int],
) -> tuple[int, int]:
    """Resolve whole-entry crop bounds in canonical full-resolution pixels.

    Crop bounds are literal original-image pixel values. No page-width or display-width conversion is performed.
    """
    geometry = geometry_fn(image, settings)
    canonical_width, canonical_height = geometry.transform.canonical_size(image.size)
    if top_y is None and bottom_y is None and root is not None:
        top, bottom = special_bounds_fn(root, page_stem, geometry)
        return max(0, top), min(canonical_height, bottom)

    top_value = (
        source_px_fn(settings.start_y)
        if top_y is None
        else source_px_fn(max(0, int(top_y)))
    )
    if bottom_y is None:
        bottom_value = (
            source_px_fn(max(0, int(settings.bottom_y)))
            if bool(getattr(settings, "crop_to_bottom_y", False))
            and int(getattr(settings, "bottom_y", 0) or 0) > 0
            else 0
        )
    else:
        bottom_value = (
            0
            if int(bottom_y) <= 0
            else source_px_fn(max(0, int(bottom_y)))
        )
    top = max(0, min(canonical_height - 1, int(top_value)))
    bottom = canonical_height if bottom_value <= 0 else max(
        top + 1, min(canonical_height, int(bottom_value))
    )
    return top, bottom
