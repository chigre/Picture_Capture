from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .adaptive_denoise import adaptive_speck_remove_mask, resolve_denoise_strength


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


def build_analysis_image(
    image: Image.Image,
    settings: Any | None = None,
    *,
    ink_mask: np.ndarray | None = None,
) -> Image.Image:
    """Return the shared, coordinate-identical analysis image.

    The full page is profiled before any pixel is removed.  The amount of sparse
    ink on this page determines the automatic cleanup strength, while the user
    may override it with off/weak/auto/strong.  The source scan is never mutated,
    resized, cropped or deskewed here.

    Real punctuation and detached glyph parts near dense text are protected by a
    wider-neighbourhood guard; long thin rules/stems are protected by directional
    support.  The resulting image is shared by Layout, Page Understanding,
    ordinary/VB and other visual evidence so they see the same cleaned pixels.
    """
    source = normalize_page_rgb(image)
    gray_image = ImageOps.grayscale(source)
    try:
        gray = np.asarray(gray_image, dtype=np.uint8)
        if ink_mask is None:
            ink = _generic_analysis_ink(gray_image, gray)
        else:
            ink = np.asarray(ink_mask, dtype=bool)
            if ink.shape != gray.shape:
                raise ValueError("analysis ink mask must match page dimensions")

        if ink.size == 0 or not bool(np.any(ink)):
            return source

        strength = resolve_denoise_strength(settings)
        remove, profile = adaptive_speck_remove_mask(ink, strength=strength)

        # Keep diagnostics attached to the in-memory analysis image.  This is
        # deliberately metadata only; no detector depends on it.
        profile_payload = {
            "requested": profile.requested,
            "effective_scale": profile.effective_scale,
            "ink_pixels": profile.ink_pixels,
            "sparse_ratio": profile.sparse_ratio,
            "local5_limit": profile.local5_limit,
            "local11_limit": profile.local11_limit,
            "directional_limit": profile.directional_limit,
            "near_text_limit": profile.near_text_limit,
            "candidate_pixels": profile.candidate_pixels,
            "removed_pixels": profile.removed_pixels,
        }

        if not bool(np.any(remove)):
            source.info["analysis_denoise_profile"] = profile_payload
            return source

        arr = np.asarray(source).copy()
        arr[remove] = 255
        cleaned = Image.fromarray(arr, mode="RGB")
        cleaned.info["analysis_denoise_profile"] = profile_payload
        source.close()
        return cleaned
    finally:
        gray_image.close()
