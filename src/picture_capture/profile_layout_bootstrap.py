from __future__ import annotations

"""Fast, anchor-free page-layout bootstrap for Project Profile creation.

Profile creation is the stage that *establishes* stable page geometry.  It must
therefore not use the current project's column width/gutter/manual-X as a prior,
and it should not pay the cost of Paddle TextDetection for every representative
page.  This module deliberately uses only the shared denoised image plus the
OCR-free projection estimator, then lets the existing multi-page robust
aggregation in ``profile_setup`` establish the stable Profile values.
"""

from collections import OrderedDict
from dataclasses import replace
import hashlib
from typing import Any

from PIL import Image

from . import layout_detection
from .image_utils import build_analysis_image
from .layout_transform import LayoutTransform


_CACHE_LIMIT = 24
_PROFILE_BOOTSTRAP_CACHE: "OrderedDict[tuple[Any, ...], Any]" = OrderedDict()


def _cache_key(image: Image.Image, settings: Any) -> tuple[Any, ...]:
    digest = hashlib.blake2b(image.tobytes(), digest_size=16).digest()
    return (str(image.mode), tuple(image.size), digest, repr(settings))


def clear_profile_layout_bootstrap_cache() -> None:
    _PROFILE_BOOTSTRAP_CACHE.clear()


def detect_profile_layout_parameters(image: Image.Image, settings: Any) -> Any:
    """Estimate one representative page without Profile anchoring or Paddle.

    ``settings`` is copied and never mutated.  Column count is always detected
    during bootstrap because the Profile is precisely where the stable column
    geometry is being learned.  Reading/transform semantics and the user's
    separator declaration are preserved.
    """
    current = replace(settings)
    current.layout_columns_policy = "detect"

    analysis = build_analysis_image(image, current)
    try:
        key = _cache_key(analysis, current)
        cached = _PROFILE_BOOTSTRAP_CACHE.get(key)
        if cached is not None:
            _PROFILE_BOOTSTRAP_CACHE.move_to_end(key)
            return cached

        transform = LayoutTransform(
            str(getattr(current, "layout_transform", "identity") or "identity")
        )
        canonical = transform.canonical_image_for_analysis(analysis)
        try:
            # Intentionally bypass detect_layout_parameters(): that public path
            # performs reliable Paddle+projection fusion against current Profile
            # geometry, which is circular and expensive during Profile creation.
            estimate = layout_detection._projection_layout_estimate(
                canonical,
                current,
            )
        finally:
            canonical.close()

        # Projection geometry is deliberately OCR-free, but its historical
        # character_height = 0.008 * page_height is NOT a measurement of text.
        # On the real XDHYCD scans this was 17px while the printed row ink was
        # consistently 29px on all representative pages. Measure physical ink
        # at source resolution before making a multi-page Profile proposal.
        from .layout_character_height import observed_character_height
        observed, stats = observed_character_height(
            canonical, current, estimate, layout_detection,
        )
        base_method = f"profile_bootstrap+{getattr(estimate, 'method', 'projection')}"
        if observed is not None:
            estimate = replace(estimate, character_height=int(observed))
            estimate.method = (
                f"{base_method}+observed_character_height={int(observed)}"
                f"(n={int(stats.get('samples', 0))})"
            )
        else:
            # Callers must not present a page-ratio guess as measured height.
            estimate.method = f"{base_method}+unverified_character_height"
        estimate.canonical_transform = transform.kind

        _PROFILE_BOOTSTRAP_CACHE[key] = estimate
        _PROFILE_BOOTSTRAP_CACHE.move_to_end(key)
        while len(_PROFILE_BOOTSTRAP_CACHE) > _CACHE_LIMIT:
            _PROFILE_BOOTSTRAP_CACHE.popitem(last=False)
        return estimate
    finally:
        analysis.close()


def install_profile_layout_bootstrap() -> None:
    """Compatibility no-op; Profile detector ownership is now static."""
    return None
