from __future__ import annotations

import numpy as np
from PIL import Image

from picture_capture.adaptive_denoise import adaptive_speck_remove_mask
from picture_capture.image_utils import build_analysis_image


def _noisy_mask(noise_points: int) -> np.ndarray:
    mask = np.zeros((160, 220), dtype=bool)
    # Two text-like blocks with strong local support.
    mask[30:55, 70:105] = True
    mask[90:116, 85:132] = True
    # A long thin rule must survive directional protection.
    mask[130, 25:190] = True
    # Deterministic isolated/sparse scan dirt.
    for i in range(noise_points):
        y = 5 + (i * 17) % 145
        x = 5 + (i * 31) % 205
        if not mask[y, x]:
            mask[y, x] = True
    return mask


def test_auto_strength_responds_to_whole_page_sparse_ink_distribution() -> None:
    cleanish = _noisy_mask(18)
    noisy = _noisy_mask(260)

    _remove_a, profile_a = adaptive_speck_remove_mask(cleanish, strength="auto")
    _remove_b, profile_b = adaptive_speck_remove_mask(noisy, strength="auto")

    assert profile_b.sparse_ratio > profile_a.sparse_ratio
    assert profile_b.effective_scale >= profile_a.effective_scale
    assert profile_b.local11_limit >= profile_a.local11_limit


def test_manual_strength_orders_cleanup_without_erasing_long_rule() -> None:
    mask = _noisy_mask(180)
    weak, weak_profile = adaptive_speck_remove_mask(mask, strength="weak")
    auto, auto_profile = adaptive_speck_remove_mask(mask, strength="auto")
    strong, strong_profile = adaptive_speck_remove_mask(mask, strength="strong")

    assert strong_profile.effective_scale >= auto_profile.effective_scale >= weak_profile.effective_scale
    assert strong_profile.removed_pixels >= weak_profile.removed_pixels

    # Directional support protects the printed rule in every mode.
    assert not bool(np.any(weak[130, 25:190]))
    assert not bool(np.any(auto[130, 25:190]))
    assert not bool(np.any(strong[130, 25:190]))


def test_build_analysis_image_keeps_coordinates_and_removes_sparse_dirt(monkeypatch) -> None:
    image = Image.new("RGB", (120, 100), "white")
    arr = np.asarray(image).copy()
    arr[10, 10] = 0
    arr[40:65, 55:82] = 0
    image = Image.fromarray(arr, mode="RGB")

    monkeypatch.setenv("PICTURE_CAPTURE_DENOISE_STRENGTH", "strong")
    cleaned = build_analysis_image(image)

    assert cleaned.size == image.size
    assert cleaned.getpixel((10, 10)) == (255, 255, 255)
    assert cleaned.getpixel((65, 50)) == (0, 0, 0)
    profile = cleaned.info.get("analysis_denoise_profile")
    assert isinstance(profile, dict)
    assert profile.get("requested") == "strong"
