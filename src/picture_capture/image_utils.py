from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps


def normalize_page_rgb(image: Image.Image) -> Image.Image:
    """Return a detached, EXIF-oriented RGB page image.

    Any image carrying transparency (RGBA/LA/P with transparency, etc.) is
    composited onto an opaque white page *before* RGB conversion.  This keeps
    display, OCR, separator detection and Y refinement on the same pixels and
    avoids transparent PNGs becoming dark when alpha is discarded.

    For ordinary opaque RGB pages, pixel values are preserved exactly.
    """
    oriented = ImageOps.exif_transpose(image)
    try:
        has_alpha = "A" in oriented.getbands() or "transparency" in oriented.info
        if has_alpha:
            rgba = oriented.convert("RGBA")
            try:
                white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                try:
                    return Image.alpha_composite(white, rgba).convert("RGB")
                finally:
                    white.close()
            finally:
                if rgba is not oriented:
                    rgba.close()
        if oriented.mode == "RGB":
            return oriented.copy()
        return oriented.convert("RGB")
    finally:
        if oriented is not image:
            oriented.close()


def _box_sum(mask: np.ndarray, radius_y: int, radius_x: int) -> np.ndarray:
    """Return a local foreground count with the same shape as ``mask``."""
    ry = max(0, int(radius_y))
    rx = max(0, int(radius_x))
    src = np.pad(
        np.asarray(mask, dtype=np.uint8),
        ((ry, ry), (rx, rx)),
        mode="constant",
    )
    integral = np.pad(
        src.cumsum(axis=0, dtype=np.int32).cumsum(axis=1, dtype=np.int32),
        ((1, 0), (1, 0)),
    )
    height = 2 * ry + 1
    width = 2 * rx + 1
    return (
        integral[height:, width:]
        - integral[:-height, width:]
        - integral[height:, :-width]
        + integral[:-height, :-width]
    )


def _generic_analysis_ink(gray_image: Image.Image) -> np.ndarray:
    """Return a conservative local-contrast ink mask for shared preprocessing.

    This mask is intentionally independent of any one detector.  It is only
    used to decide whether a dark pixel is an *isolated speck*; downstream
    modules remain free to apply their own thresholds to the cleaned image.
    """
    gray = np.asarray(gray_image, dtype=np.int16)
    local = np.asarray(gray_image.filter(ImageFilter.BoxBlur(5)), dtype=np.int16)
    # Require both absolute darkness and local contrast.  The absolute branch
    # keeps black specks detectable on already-white scans, while the local
    # branch handles yellow/gray paper without whitening the page globally.
    return (gray <= 150) | ((gray <= 205) & (gray + 20 <= local))


def build_analysis_image(
    image: Image.Image,
    settings: Any | None = None,
    *,
    ink_mask: np.ndarray | None = None,
) -> Image.Image:
    """Return the shared full-resolution image used by detection/analysis.

    The analysis image has exactly the same width, height and coordinate system
    as the normalized source page.  Only tiny *isolated* dark specks are painted
    white.  It is therefore safe for layout analysis, ordinary/VB drawing,
    Page Understanding and other visual evidence modules to share one cleaned
    page without introducing coordinate drift.

    Important contract:
    * this function never resizes, crops or deskews;
    * the original scan remains untouched and should still be used for display
      and final crop/export;
    * punctuation/diacritics near real glyph strokes are protected by the wider
      neighbourhood test;
    * long one-pixel rules/stems are protected by directional support tests.

    ``settings`` is accepted deliberately so callers can use one stable API;
    the first version is detector-independent and does not require a setting.
    A caller with a more specific already-computed foreground mask may pass it
    through ``ink_mask`` while retaining the same cleanup semantics.
    """
    del settings  # reserved for future user-configurable cleanup strength
    source = normalize_page_rgb(image)
    gray_image = ImageOps.grayscale(source)
    try:
        gray = np.asarray(gray_image, dtype=np.uint8)
        if ink_mask is None:
            ink = _generic_analysis_ink(gray_image)
        else:
            ink = np.asarray(ink_mask, dtype=bool)
            if ink.shape != gray.shape:
                raise ValueError("analysis ink mask must match page dimensions")

        if ink.size == 0 or not bool(np.any(ink)):
            return source

        # Shared preprocessing is intentionally more conservative than the old
        # layout-only cleanup.  A candidate pixel must have almost no nearby
        # support before it can disappear.  This removes scan dust while keeping
        # periods, accents and detached glyph pieces that sit near normal text.
        local5 = _box_sum(ink, 2, 2)
        local11 = _box_sum(ink, 5, 5)
        vertical13 = _box_sum(ink, 6, 0)
        horizontal13 = _box_sum(ink, 0, 6)
        remove = (
            ink
            & (local5 <= 3)
            & (local11 <= 4)
            & (vertical13 <= 2)
            & (horizontal13 <= 2)
        )
        if not bool(np.any(remove)):
            return source

        arr = np.asarray(source).copy()
        arr[remove] = 255
        cleaned = Image.fromarray(arr, mode="RGB")
        source.close()
        return cleaned
    finally:
        gray_image.close()
