from __future__ import annotations

"""Page-adaptive speck analysis for the shared full-resolution analysis image.

The goal is not generic photographic denoising. Dictionary scans contain real
small punctuation, accents, thin rules and detached glyph parts that must remain.
We therefore profile the *whole page* first and only remove ink with unusually
weak local support relative to the page's observed sparse-ink distribution.
"""

from dataclasses import dataclass
import os
from typing import Any

import numpy as np


DENOISE_ENV = "PICTURE_CAPTURE_DENOISE_STRENGTH"
VALID_STRENGTHS = {"off", "weak", "auto", "strong"}


@dataclass(frozen=True, slots=True)
class DenoiseProfile:
    requested: str
    effective_scale: float
    ink_pixels: int
    sparse_ratio: float
    local5_limit: int
    local11_limit: int
    directional_limit: int
    near_text_limit: int
    candidate_pixels: int
    removed_pixels: int


def normalize_denoise_strength(value: object) -> str:
    text = str(value or "auto").strip().lower()
    aliases = {
        "关闭": "off",
        "关": "off",
        "off": "off",
        "none": "off",
        "弱": "weak",
        "weak": "weak",
        "low": "weak",
        "自动": "auto",
        "auto": "auto",
        "标准": "auto",
        "强": "strong",
        "strong": "strong",
        "high": "strong",
    }
    return aliases.get(text, "auto")


def resolve_denoise_strength(settings: Any | None = None) -> str:
    """Resolve the shared denoise mode.

    A future/project setting takes precedence when present. The environment
    fallback lets the main GUI change the mode without changing the large legacy
    settings model, and is inherited by spawned ordinary-drawing workers.
    """
    if settings is not None:
        configured = getattr(settings, "analysis_denoise_strength", None)
        if configured not in (None, ""):
            return normalize_denoise_strength(configured)
    return normalize_denoise_strength(os.environ.get(DENOISE_ENV, "auto"))


def _box_sum(mask: np.ndarray, radius_y: int, radius_x: int) -> np.ndarray:
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
    h = 2 * ry + 1
    w = 2 * rx + 1
    return (
        integral[h:, w:]
        - integral[:-h, width:] if False else
        integral[h:, w:]
        - integral[:-h, w:]
        - integral[h:, :-w]
        + integral[:-h, :-w]
    )


def _auto_scale(ink: np.ndarray, local5: np.ndarray, local11: np.ndarray) -> tuple[float, float]:
    total = int(np.count_nonzero(ink))
    if total <= 0:
        return 1.0, 0.0

    # A page with many low-support ink pixels is objectively noisier than one
    # whose ink is mostly embedded in letter strokes. This ratio is invariant
    # to page size and substantially more transferable across scanner DPI than
    # an absolute component-area threshold.
    sparse = ink & (local5 <= 5) & (local11 <= 10)
    ratio = float(np.count_nonzero(sparse)) / float(total)
    if ratio >= 0.080:
        scale = 1.60
    elif ratio >= 0.045:
        scale = 1.40
    elif ratio >= 0.025:
        scale = 1.22
    elif ratio >= 0.012:
        scale = 1.08
    else:
        scale = 0.92
    return scale, ratio


def adaptive_speck_remove_mask(
    ink_mask: np.ndarray,
    *,
    strength: str = "auto",
) -> tuple[np.ndarray, DenoiseProfile]:
    """Return a mask of pixels to whiten plus whole-page noise diagnostics."""
    ink = np.asarray(ink_mask, dtype=bool)
    requested = normalize_denoise_strength(strength)
    empty = np.zeros_like(ink, dtype=bool)
    if ink.size == 0 or not bool(np.any(ink)) or requested == "off":
        profile = DenoiseProfile(
            requested=requested,
            effective_scale=0.0 if requested == "off" else 1.0,
            ink_pixels=int(np.count_nonzero(ink)),
            sparse_ratio=0.0,
            local5_limit=0,
            local11_limit=0,
            directional_limit=0,
            near_text_limit=0,
            candidate_pixels=0,
            removed_pixels=0,
        )
        return empty, profile

    local5 = _box_sum(ink, 2, 2)
    local11 = _box_sum(ink, 5, 5)
    auto_scale, sparse_ratio = _auto_scale(ink, local5, local11)

    if requested == "weak":
        scale = max(0.65, auto_scale * 0.70)
    elif requested == "strong":
        scale = max(1.45, auto_scale * 1.35)
    else:
        scale = auto_scale

    # Thresholds intentionally remain bounded. Even on a very dirty page the
    # shared cleaner is only allowed to remove locally sparse structures; larger
    # blobs are left for component-aware line-start logic rather than erased.
    local5_limit = max(2, min(8, int(round(3.0 * scale))))
    local11_limit = max(3, min(15, int(round(5.0 * scale))))
    directional_limit = max(2, min(6, int(round(2.2 * scale))))

    vertical13 = _box_sum(ink, 6, 0)
    horizontal13 = _box_sum(ink, 0, 6)
    local17 = _box_sum(ink, 8, 8)

    candidate = (
        ink
        & (local5 <= local5_limit)
        & (local11 <= local11_limit)
        & (vertical13 <= directional_limit)
        & (horizontal13 <= directional_limit)
    )

    # Detached punctuation/diacritics close to a real word can look sparse in a
    # 5x5 or 11x11 window. Protect them when the wider 17x17 neighbourhood has
    # real nearby stroke support. The previous auto threshold of 22 erased small
    # detached marks only a few pixels from a stem; 12 still rejects isolated
    # scan dirt while retaining those legitimate glyph components. Strong mode
    # deliberately keeps a higher bar for users who explicitly request cleanup.
    near_text_limit = 10 if requested == "weak" else 12 if requested == "auto" else 18
    protected_near_text = local17 >= near_text_limit
    remove = candidate & ~protected_near_text

    profile = DenoiseProfile(
        requested=requested,
        effective_scale=float(scale),
        ink_pixels=int(np.count_nonzero(ink)),
        sparse_ratio=float(sparse_ratio),
        local5_limit=int(local5_limit),
        local11_limit=int(local11_limit),
        directional_limit=int(directional_limit),
        near_text_limit=int(near_text_limit),
        candidate_pixels=int(np.count_nonzero(candidate)),
        removed_pixels=int(np.count_nonzero(remove)),
    )
    return remove, profile
