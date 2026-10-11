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
            # The 0.8%-of-page-height seed is NOT a text measurement. Measure
            # physical ink at source resolution while canonical is still open.
            from .layout_character_height import observed_character_height
            observed, stats = observed_character_height(
                canonical, current, estimate, layout_detection,
            )
        finally:
            canonical.close()
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



def robust_profile_ink_height(estimates: list[Any]) -> tuple[int | None, int]:
    """Aggregate *measured* page character heights, never 0.8%-height guesses.

    A six-page Profile with three verified 29px pages and three heuristic 17px
    pages must not silently propose median 23px. Require physical measurements
    from at least half of successful representative pages; otherwise leave the
    existing Profile height unchanged and expose the missing evidence.
    """
    import statistics

    trustworthy = [
        int(row.character_height)
        for row in estimates
        if "+observed_character_height=" in str(getattr(row, "method", ""))
        and int(getattr(row, "character_height", 0) or 0) > 0
    ]
    required = max(1, (len(estimates) + 1) // 2)
    if len(trustworthy) < required:
        return None, len(trustworthy)
    return int(round(statistics.median(trustworthy))), len(trustworthy)


def apply_profile_ink_height_suggestion(aggregate: dict, estimates: list[Any]) -> str:
    """Update a Profile proposal from verified multi-page ink measurements only."""
    height, count = robust_profile_ink_height(estimates)
    if height is not None:
        aggregate["character_height"] = height
        return f"；字高按真实墨迹测量{count}/{len(estimates)}页"
    aggregate.pop("character_height", None)
    return (
        f"；⚠字高仅{count}/{len(estimates)}页有可靠测量，"
        "未自动修改字高，请核对代表页"
    )


def install_profile_layout_bootstrap() -> None:
    """Compatibility no-op; Profile detector ownership is now static."""
    return None
