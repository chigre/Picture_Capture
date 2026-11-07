from __future__ import annotations

"""Coordinate-preserving page pixel primitives.

These helpers own EXIF orientation, white-backed alpha compositing and the
historical uint8 local ink predicate. They never resize, deskew, mutate source
scans, construct OCR engines or apply higher-level denoising policy.
The shared analysis_image owner re-exports the exact function objects.
"""

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
    """Backward-compatible local foreground count helper."""
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


def _generic_analysis_ink(
    gray_image: Image.Image,
    gray: np.ndarray | None = None,
) -> np.ndarray:
    """Return a conservative local-contrast ink mask for shared preprocessing."""
    gray_u8 = (
        np.asarray(gray_image, dtype=np.uint8)
        if gray is None
        else np.asarray(gray, dtype=np.uint8)
    )
    local_u8 = np.asarray(
        gray_image.filter(ImageFilter.BoxBlur(5)),
        dtype=np.uint8,
    )
    # Historical condition:
    #   gray <= 150 or (gray <= 205 and gray + 20 <= local)
    # For uint8, guard local >= 20 before subtracting to avoid underflow.
    return (
        (gray_u8 <= 150)
        | (
            (gray_u8 <= 205)
            & (local_u8 >= 20)
            & (gray_u8 <= (local_u8 - 20))
        )
    )


