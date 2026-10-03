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
from pathlib import Path
from typing import Any, Callable
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


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


def install_layout_illustration_mask_settings() -> type[Any]:
    """Extend AppSettings with one native dataclass field before consumers import it.

    A real dataclass field is required here: ``dataclasses.replace`` is used
    throughout Profile/page resolution, and a dynamic property would silently
    fall back to its default on every replace().
    """
    from . import models

    current = models.AppSettings
    fields = set(getattr(current, "__dataclass_fields__", {}))
    if SETTING_NAME in fields:
        return current

    @dataclass(slots=True)
    class ExtendedAppSettings(current):
        layout_mask_illustrations: bool = DEFAULT_ENABLED

    # Keep pickle/spawn identity stable.  Windows/macOS workers import
    # picture_capture.models.AppSettings in a fresh interpreter.
    ExtendedAppSettings.__name__ = "AppSettings"
    ExtendedAppSettings.__qualname__ = "AppSettings"
    ExtendedAppSettings.__module__ = models.__name__
    models.AppSettings = ExtendedAppSettings
    return ExtendedAppSettings


def _detect_illustration_regions_in_image(
    image: Image.Image,
    settings: Any,
    *,
    analysis_column_width: int = 520,
    profile_page_index: int = 0,
) -> list[Any]:
    """In-memory form of the existing automatic PPP illustration detector.

    The algorithm intentionally mirrors ``processing_core.detect_illustration_regions``
    and calls its shared geometry/mask/component helpers.  The runtime installer
    also redirects the historical path-based detector through this function, so
    PPP detection and Layout masking cannot drift into two independent detector
    implementations.
    """
    from . import processing_core as core
    from .models import PolygonRegion

    source, effective, analysis_source, geometry = core._page_geometry_context(
        image,
        settings,
        int(profile_page_index),
    )
    work_image: Image.Image | None = None
    try:
        work_image = geometry.transform.canonical_image_for_analysis(analysis_source)
        source_margin = max(
            2,
            core._source_px(
                max(0, int(getattr(effective, "illustration_detect_padding", 8)))
            ),
        )
        source_margin_right = max(
            source_margin,
            core._source_px(
                max(
                    0,
                    int(getattr(effective, "illustration_detect_right_padding", 16)),
                )
            ),
        )
        results: list[Any] = []
        for column, start in enumerate(geometry.column_starts):
            width = geometry.column_widths[column]
            base_x0 = max(0, int(start))
            base_x1 = min(work_image.width, int(start + width))
            if column + 1 < len(geometry.column_starts):
                next_start = int(geometry.column_starts[column + 1])
                free_right = max(0, next_start - base_x1)
                right_room = min(
                    max(source_margin_right, free_right // 2),
                    max(source_margin_right, round(width * 0.10)),
                )
            else:
                free_right = max(0, work_image.width - base_x1)
                right_room = min(
                    free_right,
                    max(source_margin_right, round(width * 0.08)),
                )
            x0 = base_x0
            x1 = min(work_image.width, base_x1 + max(0, right_room))
            y0 = max(0, int(geometry.top))
            y1 = min(work_image.height, int(geometry.bottom))
            if x1 - x0 < 40 or y1 - y0 < 80:
                continue

            crop = work_image.crop((x0, y0, x1, y1)).convert("L")
            try:
                a_scale = min(1.0, analysis_column_width / max(1, crop.width))
                aw = max(1, round(crop.width * a_scale))
                ah = max(1, round(crop.height * a_scale))
                small = (
                    crop
                    if a_scale == 1.0
                    else crop.resize((aw, ah), Image.Resampling.BILINEAR)
                )
                try:
                    adaptive = core._adaptive_dark_mask(small, 19, 16)
                    arr = np.asarray(small, dtype=np.uint8)
                    dark = np.logical_or(adaptive, arr < 170)
                    mask_img = Image.fromarray(
                        dark.astype(np.uint8) * 255,
                        mode="L",
                    )
                    try:
                        joined = (
                            np.asarray(
                                mask_img.filter(ImageFilter.MaxFilter(3)),
                                dtype=np.uint8,
                            )
                            > 0
                        )
                    finally:
                        mask_img.close()

                    comps = core._rle_components(joined)
                    min_h = max(18, round(0.028 * ah))
                    min_w = max(18, round(0.055 * aw))
                    min_bbox_area = max(500, round(0.0022 * aw * ah))
                    candidates: list[tuple[int, int, int, int]] = []
                    for cx0, cy0, cx1, cy1, area in comps:
                        bw = cx1 - cx0
                        bh = cy1 - cy0
                        bbox_area = bw * bh
                        if bw < min_w or bh < min_h or bbox_area < min_bbox_area:
                            continue
                        occupancy = area / max(1, bbox_area)
                        if occupancy < 0.035:
                            continue
                        if bw / max(1, bh) > 7.0 and bh < 0.08 * ah:
                            continue
                        candidates.append((cx0, cy0, cx1, cy1))

                    gap = max(5, round(0.018 * aw))
                    candidates = core._merge_nearby_boxes(candidates, gap)
                    for cx0, cy0, cx1, cy1 in candidates:
                        bw = cx1 - cx0
                        bh = cy1 - cy0
                        if bh < min_h or bw < min_w:
                            continue
                        sx0 = x0 + round(cx0 / a_scale) - source_margin
                        sy0 = y0 + round(cy0 / a_scale) - source_margin
                        sx1 = x0 + round(cx1 / a_scale) + source_margin_right
                        sy1 = y0 + round(cy1 / a_scale) + source_margin
                        sx0 = max(x0, sx0)
                        sy0 = max(y0, sy0)
                        sx1 = min(x1, sx1)
                        sy1 = min(y1, sy1)
                        if sx1 - sx0 < 8 or sy1 - sy0 < 8:
                            continue
                        results.append(
                            PolygonRegion(
                                "",
                                [
                                    (sx0, sy0),
                                    (sx1, sy0),
                                    (sx1, sy1),
                                    (sx0, sy1),
                                ],
                            )
                        )
                finally:
                    if small is not crop:
                        small.close()
            finally:
                crop.close()

        if geometry.transform.kind == "identity":
            return results
        return [
            PolygonRegion(
                region.label,
                [geometry.canonical_to_source(x, y) for x, y in region.points],
            )
            for region in results
        ]
    finally:
        if work_image is not None:
            try:
                work_image.close()
            except Exception:
                pass
        try:
            if analysis_source is not source:
                analysis_source.close()
        except Exception:
            pass
        try:
            if source is not image:
                source.close()
        except Exception:
            pass


def detect_illustration_regions_from_image(
    image: Image.Image,
    settings: Any,
    *,
    analysis_column_width: int = 520,
    profile_page_index: int = 0,
) -> list[Any]:
    return _detect_illustration_regions_in_image(
        image,
        settings,
        analysis_column_width=int(analysis_column_width),
        profile_page_index=int(profile_page_index),
    )


def detect_illustration_regions_from_path(
    image_path: str | Path,
    settings: Any,
    *,
    analysis_column_width: int = 520,
    profile_page_index: int = 0,
) -> list[Any]:
    """Historical path API forwarded through the shared in-memory detector."""
    from .image_utils import normalize_page_rgb

    with Image.open(Path(image_path)) as opened:
        image = normalize_page_rgb(opened)
    try:
        return detect_illustration_regions_from_image(
            image,
            settings,
            analysis_column_width=int(analysis_column_width),
            profile_page_index=int(profile_page_index),
        )
    finally:
        image.close()


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
    detect = detector or detect_illustration_regions_from_image
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
    """Share the detector and wrap the single Page Understanding entry point."""
    if bool(getattr(processing_module, "_pc_layout_illustration_mask_installed", False)):
        return

    from . import processing_core as core

    # Existing PPP auto-detection now goes through exactly the same in-memory
    # component detector used by Layout masking.
    core.detect_illustration_regions = detect_illustration_regions_from_path
    processing_module.detect_illustration_regions = detect_illustration_regions_from_path

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
