from __future__ import annotations

"""Optional illustration masking before Page/Layout Understanding.

The existing automatic PPP illustration detector is reused as the single image
component detector.  When the project switch is enabled, sufficiently large
illustration candidates are painted white on a disposable analysis copy before
Page Understanding runs.  Source scans, PPP annotations, OCR input and crop
outputs are never modified.

Layout masking is intentionally more conservative than PPP auto-detection.  A
second size/shape guard rejects candidates that are still compatible with an
oversized dictionary headword, so a display Han glyph cannot disappear merely
because it forms one large connected component.
"""

from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable
import math

from PIL import Image, ImageDraw


SETTING_NAME = "layout_mask_illustrations"
SETTING_LABEL = "Layout前白化插图"
DEFAULT_ENABLED = False

# These are deliberately conservative Layout-only guards, expressed in the
# page's ordinary glyph-height scale.  They do NOT change automatic PPP output.
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
    """Return whether an auto-illustration candidate is safe to white-fill.

    The primary guard is physical size.  A second near-square guard protects
    oversized display headwords: even if a giant glyph clears the minimum-area
    test, a roughly square object no larger than ~5 ordinary glyph heights is
    still too headword-like to erase from Layout analysis.
    """
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


def _append_mask_reason(understanding: Any, stats: IllustrationMaskStats) -> None:
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


def install_layout_illustration_mask_runtime(processing_module: Any) -> None:
    """Wrap the single Page Understanding entry point for optional masking."""
    if bool(getattr(processing_module, "_pc_layout_illustration_mask_installed", False)):
        return

    original = processing_module._understand_page_current

    @wraps(original)
    def wrapped(
        image: Image.Image,
        settings: Any,
        *,
        page_index: int,
        page_sections: Any,
        layout_only: bool = False,
    ):
        if not bool(getattr(settings, SETTING_NAME, DEFAULT_ENABLED)):
            return original(
                image,
                settings,
                page_index=page_index,
                page_sections=page_sections,
                layout_only=layout_only,
            )

        masked = image
        stats = IllustrationMaskStats()
        try:
            masked, stats = mask_large_illustrations_for_layout(
                image,
                settings,
                profile_page_index=int(page_index),
            )
        except Exception:
            # Illustration masking is a protective pre-filter, never a reason to
            # make Layout unavailable. Fall back to the original analysis image.
            masked = image
            stats = IllustrationMaskStats()

        try:
            understanding = original(
                masked,
                settings,
                page_index=page_index,
                page_sections=page_sections,
                layout_only=layout_only,
            )
            _append_mask_reason(understanding, stats)
            return understanding
        finally:
            if masked is not image:
                try:
                    masked.close()
                except Exception:
                    pass

    processing_module._understand_page_current = wrapped
    processing_module._pc_layout_illustration_mask_installed = True


def install_layout_illustration_mask_ui(app_module: Any) -> None:
    """Expose the switch in Settings Center and invalidate Layout UI cache."""
    dialog = app_module.SettingsDialog
    if bool(getattr(dialog, "_pc_layout_illustration_mask_ui_installed", False)):
        return

    checks = list(getattr(dialog, "NORMAL_CHECKS", ()))
    names = [str(item[1]) for item in checks if len(item) >= 2]
    if SETTING_NAME not in names:
        try:
            position = names.index("ordinary_auto_layout") + 1
        except ValueError:
            position = len(checks)
        checks.insert(position, (SETTING_LABEL, SETTING_NAME))
        dialog.NORMAL_CHECKS = tuple(checks)

    dialog.SETTING_HELP = dict(getattr(dialog, "SETTING_HELP", {}))
    dialog.SETTING_HELP[SETTING_NAME] = (
        "作用：开启后，【普通画线】和【显示 Layout】在 Page Understanding 之前先复用自动插图检测，"
        "把足够大的插图区域仅在分析副本上填成白色，再恢复文字行、缩进和 entry/body 角色。"
        "原始扫描图、PPP、OCR、PDIC 与切图文件都不会被修改。\n\n"
        "保护：Layout 白化比 PPP 自动插图更保守。小尺寸候选直接忽略；接近大字头尺寸且近方形的候选也不会白化，"
        "避免把大号单字/大字头误当成插图。关闭时完全保持原有 Layout 流程。"
    )
    dialog.SETTING_LABELS = dict(getattr(dialog, "SETTING_LABELS", {}))
    dialog.SETTING_LABELS[SETTING_NAME] = SETTING_LABEL

    # The shared visualization caches one snapshot per page/settings geometry.
    # Include this analysis switch explicitly so toggling it refreshes at once.
    try:
        from . import layout_visualization_ui as ui

        original_key = ui._layout_cache_key
        if not bool(getattr(original_key, "_pc_illustration_mask_key", False)):
            @wraps(original_key)
            def cache_key(app: Any):
                return (
                    *tuple(original_key(app)),
                    SETTING_NAME,
                    bool(getattr(app.settings, SETTING_NAME, DEFAULT_ENABLED)),
                )

            cache_key._pc_illustration_mask_key = True  # type: ignore[attr-defined]
            ui._layout_cache_key = cache_key
    except Exception:
        pass

    dialog._pc_layout_illustration_mask_ui_installed = True


__all__ = [
    "DEFAULT_ENABLED",
    "IllustrationMaskStats",
    "SETTING_LABEL",
    "SETTING_NAME",
    "detect_illustration_regions_from_image",
    "detect_illustration_regions_from_path",
    "install_layout_illustration_mask_runtime",
    "install_layout_illustration_mask_settings",
    "install_layout_illustration_mask_ui",
    "layout_mask_region_is_large_enough",
    "mask_large_illustrations_for_layout",
]
