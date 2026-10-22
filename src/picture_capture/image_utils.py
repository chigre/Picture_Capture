from __future__ import annotations

from typing import Any
import os

import numpy as np
from PIL import Image, ImageOps

from .preprocess.adaptive_denoise import adaptive_speck_remove_mask, resolve_denoise_strength
from .preprocess.page_pixels import normalize_page_rgb, _box_sum, _generic_analysis_ink


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
    # Experimental reuse: enabled only for images explicitly produced by this
    # same analysis builder at the same denoise strength. Keep off by default
    # until exact PDIC parity has been validated on real dictionary scans.
    requested = resolve_denoise_strength(settings)
    if (os.environ.get("PICTURE_CAPTURE_REUSE_PREPARED_ANALYSIS") == "1"
            and ink_mask is None
            and image.mode == "RGB"
            and image.info.get("_picture_capture_analysis_strength") == requested):
        return image.copy()
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

        strength = requested
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
            source.info["_picture_capture_analysis_strength"] = requested
            return source

        arr = np.asarray(source).copy()
        arr[remove] = 255
        cleaned = Image.fromarray(arr, mode="RGB")
        cleaned.info["analysis_denoise_profile"] = profile_payload
        cleaned.info["_picture_capture_analysis_strength"] = requested
        source.close()
        return cleaned
    finally:
        gray_image.close()
