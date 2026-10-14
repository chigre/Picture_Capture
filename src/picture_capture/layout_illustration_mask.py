from __future__ import annotations

"""Pure illustration masking policy shared by Layout and training diagnostics."""

from dataclasses import dataclass
from pathlib import Path
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
    candidate_debug: list[dict[str, Any]] | None = None,
    source_image_path: Path | None = None,
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
    reuse_existing = bool(getattr(settings, "layout_mask_illustrations_use_existing", False))
    if reuse_existing:
        if source_image_path is None:
            raise ValueError(
                "已启用使用已有的插图数据，但当前 Layout 入口没有对应图片路径，"
                "无法确定 PPP 文件。"
            )
        from .project_storage import ppp_read_path_for_image
        from .formats import read_ppp
        ppp_file = ppp_read_path_for_image(Path(source_image_path))
        if not ppp_file.is_file():
            raise FileNotFoundError(
                f"当前页缺少 PPP 插图数据：{ppp_file}；"
                "复用模式不会重新检测。请先运行插图识别，或关闭复用。"
            )
        regions = read_ppp(ppp_file)
        if candidate_debug is not None:
            for region in regions:
                candidate_debug.append({
                    "status": "masked_existing_ppp",
                    "source_polygon": [
                        [int(x), int(y)] for x, y in
                        (getattr(region, "points", []) or [])
                    ],
                    "reason": "直接使用已经保存的 PPP 多边形，不重复分析",
                })
        if not regions:
            return image, IllustrationMaskStats(detected=0)
        masked = image.convert("RGB")
        draw = ImageDraw.Draw(masked)
        count = 0
        for region in regions:
            points = [
                (int(x), int(y)) for x, y in
                (getattr(region, "points", []) or [])
            ]
            if len(points) >= 3:
                draw.polygon(points, fill=(255, 255, 255))
                count += 1
        return masked, IllustrationMaskStats(
            detected=len(regions), masked=count,
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
    # The detection already ran for the Layout mask. Persist those very same
    # candidates using the existing AUTO/manual merge semantics, not a second
    # costly image analysis. No PPP writes are performed in reuse mode.
    if source_image_path is not None and detector is None:
        from .processing_core import detect_illustrations_to_ppp
        detect_illustrations_to_ppp(
            Path(source_image_path), settings,
            profile_page_index=int(profile_page_index),
            detected_regions=regions,
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
        if candidate_debug is not None:
            points = [[int(p[0]), int(p[1])] for p in
                      list(getattr(region, "points", []) or []) if len(p) >= 2]
            candidate_debug.append({
                "status": "masked" if allowed else f"rejected_{reason}",
                "source_polygon": points,
                "reason": "面积/形状满足安全白化条件" if allowed
                          else ("疑似大字头，保留墨迹" if reason == "headlike"
                                else "尺寸不足或形状不可靠，保留墨迹"),
            })
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
