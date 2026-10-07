from __future__ import annotations

"""Pure illustration masking policy shared by Layout and training diagnostics."""

from dataclasses import dataclass
from typing import Any, Callable

from PIL import Image, ImageDraw


SETTING_NAME = "layout_mask_illustrations"
SETTING_LABEL = "Layout前白化插图"
DEFAULT_ENABLED = False

_MIN_SHORT_SIDE_GLYPHS = 2.0
_MIN_LONG_SIDE_GLYPHS = 4.0
_MIN_AREA_GLYPH_SQUARES = 10.0
_DISPLAY_HEAD_SQUARE_MAX_GLYPHS = 5.2
_DISPLAY_HEAD_ASPECT_MIN = 0.62
_DISPLAY_HEAD_ASPECT_MAX = 1.62


@dataclass(frozen=True)
class IllustrationMaskStats:
    detected: int = 0
    masked: int = 0
    rejected_small: int = 0
    rejected_headlike: int = 0


def _region_box(region: Any) -> tuple[int, int, int, int] | None:
    points = list(getattr(region, "points", []) or [])
    if len(points) < 3:
        return None
    try:
        xs = [int(point[0]) for point in points]
        ys = [int(point[1]) for point in points]
    except (TypeError, ValueError, IndexError):
        return None
    return min(xs), min(ys), max(xs), max(ys)


def layout_mask_region_is_large_enough(
    region: Any,
    *,
    character_height: float,
    column_width: float,
) -> tuple[bool, str]:
    """Return whether an auto-illustration candidate is safe to white-fill."""
    box = _region_box(region)
    if box is None:
        return False, "small"
    width = max(0.0, float(box[2] - box[0]))
    height = max(0.0, float(box[3] - box[1]))
    if width <= 0 or height <= 0:
        return False, "small"

    glyph = max(6.0, float(character_height or 0.0))
    col = max(glyph * 6.0, float(column_width or 0.0))
    short_side = min(width, height)
    long_side = max(width, height)
    area = width * height

    min_short = max(glyph * _MIN_SHORT_SIDE_GLYPHS, col * 0.045)
    min_long = max(glyph * _MIN_LONG_SIDE_GLYPHS, col * 0.085)
    min_area = max(
        glyph * glyph * _MIN_AREA_GLYPH_SQUARES,
        min_short * min_long * 0.65,
    )
    if short_side < min_short or long_side < min_long or area < min_area:
        return False, "small"

    aspect = width / max(1.0, height)
    if (
        _DISPLAY_HEAD_ASPECT_MIN <= aspect <= _DISPLAY_HEAD_ASPECT_MAX
        and long_side <= glyph * _DISPLAY_HEAD_SQUARE_MAX_GLYPHS
    ):
        return False, "headlike"
    return True, "ok"


def mask_large_illustrations_for_layout(
    image: Image.Image,
    settings: Any,
    *,
    profile_page_index: int = 0,
    detector: Callable[..., list[Any]] | None = None,
) -> tuple[Image.Image, IllustrationMaskStats]:
    """Return a disposable white-filled Layout image plus diagnostics."""
    if not bool(getattr(settings, SETTING_NAME, DEFAULT_ENABLED)):
        return image, IllustrationMaskStats()

    from .profile_semantics import effective_page_settings

    effective = effective_page_settings(
        settings,
        image.size,
        int(profile_page_index),
    )
    character_height = max(
        6.0,
        float(getattr(effective, "character_height", 26) or 26),
    )
    column_width = max(
        character_height * 6.0,
        float(getattr(effective, "column_width", image.width) or image.width),
    )
    if detector is None:
        from .processing_core import detect_illustration_regions_from_image

        detect = detect_illustration_regions_from_image
    else:
        detect = detector
    regions = list(
        detect(
            image,
            effective,
            profile_page_index=int(profile_page_index),
        )
        or []
    )
    if not regions:
        return image, IllustrationMaskStats(detected=0)

    accepted: list[Any] = []
    small = 0
    headlike = 0
    for region in regions:
        allowed, reason = layout_mask_region_is_large_enough(
            region,
            character_height=character_height,
            column_width=column_width,
        )
        if allowed:
            accepted.append(region)
        elif reason == "headlike":
            headlike += 1
        else:
            small += 1

    if not accepted:
        return image, IllustrationMaskStats(
            detected=len(regions),
            masked=0,
            rejected_small=small,
            rejected_headlike=headlike,
        )

    masked = image.convert("RGB").copy()
    draw = ImageDraw.Draw(masked)
    for region in accepted:
        points = [
            (int(point[0]), int(point[1]))
            for point in list(getattr(region, "points", []) or [])
        ]
        if len(points) >= 3:
            draw.polygon(points, fill=(255, 255, 255))
    return masked, IllustrationMaskStats(
        detected=len(regions),
        masked=len(accepted),
        rejected_small=small,
        rejected_headlike=headlike,
    )


def append_mask_reason(understanding: Any, stats: IllustrationMaskStats) -> None:
    """Append the historical illustration-mask diagnostics to Layout reason."""
    if understanding is None:
        return
    layout = getattr(understanding, "layout", None)
    if layout is None:
        return
    try:
        layout.reason += (
            "; illustration_mask=1"
            f" detected={int(stats.detected)}"
            f" masked={int(stats.masked)}"
            f" small_rejected={int(stats.rejected_small)}"
            f" headlike_rejected={int(stats.rejected_headlike)}"
        )
    except Exception:
        pass


__all__ = [
    "DEFAULT_ENABLED",
    "IllustrationMaskStats",
    "SETTING_LABEL",
    "SETTING_NAME",
    "append_mask_reason",
    "layout_mask_region_is_large_enough",
    "mask_large_illustrations_for_layout",
]
