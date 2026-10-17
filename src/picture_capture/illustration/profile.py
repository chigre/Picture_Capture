"""Project-wide illustrated/ordinary layout routing and validated OCR preferences.

This layer owns *which* editor applies, not text geometry or Tk widgets.
For mixed projects, absent page overrides default to traditional processing;
the image's exact filename is the stable identity (not its list index).
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

KINDS = ("traditional", "illustrated", "mixed")
PAGE_KINDS = ("traditional", "illustrated")
GROUPING = ("strict", "auto", "loose")
LANGUAGE_TOKEN = re.compile(r"^[a-z][a-z0-9_]{1,19}$")
PROFILE_FIELDS = (
    "dictionary_layout_kind",
    "illustrated_page_overrides",
    "illustrated_primary_language",
    "illustrated_ocr_languages",
    "illustrated_grouping_mode",
    "illustrated_group_max_lines",
    "illustrated_require_review",
    "illustrated_export_split_aliases",
    "illustrated_ocr_top_percent",
    "illustrated_ocr_bottom_percent",
    "illustrated_ocr_side_percent",
    "illustrated_grid_visible", "illustrated_grid_x", "illustrated_grid_y",
    "illustrated_grid_subdivisions", "illustrated_grid_origin_x",
    "illustrated_grid_origin_y", "illustrated_grid_color",
    "illustrated_guide_color", "illustrated_grid_opacity",
    "illustrated_guides_visible", "illustrated_guides_locked",
    "illustrated_snap_grid", "illustrated_snap_guides",
    "illustrated_snap_objects", "illustrated_snap_tolerance",
    "illustrated_nudge_step", "illustrated_history_depth",
)


def effective_page_kind(settings: Any, page: Path | str | None) -> str:
    kind = str(getattr(settings, "dictionary_layout_kind", "traditional") or "traditional")
    if kind not in KINDS:
        kind = "traditional"
    if kind != "mixed":
        return kind
    overrides = getattr(settings, "illustrated_page_overrides", {}) or {}
    value = overrides.get(Path(page).name) if page is not None and isinstance(overrides, dict) else None
    return value if value in PAGE_KINDS else "traditional"


def set_page_kind(settings: Any, page: Path | str, kind: str) -> None:
    if kind not in (*PAGE_KINDS, "default"):
        raise ValueError("页面版式必须为传统、图解或项目默认")
    overrides = dict(getattr(settings, "illustrated_page_overrides", {}) or {})
    name = Path(page).name
    if kind == "default":
        overrides.pop(name, None)
    else:
        overrides[name] = kind
    settings.illustrated_page_overrides = overrides


def languages(value: str) -> tuple[str, ...]:
    result = tuple(x.strip().lower() for x in re.split(r"[,，;+、\s]+", str(value or "")) if x.strip())
    if not result or len(result) > 12 or any(not LANGUAGE_TOKEN.fullmatch(x) for x in result):
        raise ValueError("OCR 语言应是以逗号或 + 分隔的 Tesseract 语言代码（最多 12 种）")
    return tuple(dict.fromkeys(result))


def validate_illustrated_preferences(settings: Any) -> None:
    if getattr(settings, "dictionary_layout_kind", "traditional") not in KINDS:
        raise ValueError("不支持的词典版式")
    overrides = getattr(settings, "illustrated_page_overrides", {})
    if not isinstance(overrides, dict) or any(
        not isinstance(name, str) or not name or Path(name).name != name
        or kind not in PAGE_KINDS for name, kind in overrides.items()
    ):
        raise ValueError("逐页版式覆盖必须使用图片文件名")
    languages(str(getattr(settings, "illustrated_ocr_languages", "eng")))
    if not LANGUAGE_TOKEN.fullmatch(str(getattr(settings, "illustrated_primary_language", "eng"))):
        raise ValueError("主索引语言代码无效")
    if getattr(settings, "illustrated_grouping_mode", "auto") not in GROUPING:
        raise ValueError("OCR 归并方式不支持")
    value = getattr(settings, "illustrated_group_max_lines", 10)
    if type(value) is not int or not 1 <= value <= 30:
        raise ValueError("每组最大行数应在 1–30 之间")
    for name in ("illustrated_ocr_top_percent", "illustrated_ocr_bottom_percent",
                 "illustrated_ocr_side_percent"):
        value = getattr(settings, name, 0)
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("OCR 页面边距必须是数字") from exc
        if not 0 <= number <= 40:
            raise ValueError("OCR 页面边距必须在 0–40% 之间")
    if float(settings.illustrated_ocr_top_percent) + float(settings.illustrated_ocr_bottom_percent) >= 90:
        raise ValueError("顶部与底部 OCR 排除区域总和过大")
    for key,low,high in (
        ("illustrated_grid_x", 4, 2000), ("illustrated_grid_y", 4, 2000),
        ("illustrated_grid_subdivisions", 1, 16),
        ("illustrated_snap_tolerance", 1, 50),
        ("illustrated_nudge_step", 1, 50),
        ("illustrated_history_depth", 1, 200),
        ("illustrated_grid_opacity", 0, 100),
        ("illustrated_grid_origin_x", 0, 100000),
        ("illustrated_grid_origin_y", 0, 100000),
    ):
        val=getattr(settings,key)
        if type(val) is not int or not low<=val<=high:
            raise ValueError(f"图解布局参数 {key} 应在 {low}–{high} 之间")
    for key in ("illustrated_grid_color","illustrated_guide_color"):
        val=getattr(settings,key)
        if not isinstance(val,str) or not re.fullmatch(r"#[0-9a-fA-F]{6}",val):
            raise ValueError("辅助线颜色须为 #RRGGBB")
    for key in ("illustrated_grid_visible","illustrated_guides_visible",
                "illustrated_guides_locked","illustrated_snap_grid",
                "illustrated_snap_guides","illustrated_snap_objects"):
        if type(getattr(settings,key)) is not bool:
            raise ValueError("图解网格开关应为布尔值")



def profile_payload(settings: Any) -> dict[str, Any]:
    validate_illustrated_preferences(settings)
    return {key: getattr(settings, key) for key in PROFILE_FIELDS}


def apply_profile_payload(settings: Any, payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    # Validate a proposed clone before mutating the actual settings.
    from dataclasses import replace
    incoming = {key: value for key, value in payload.items() if key in PROFILE_FIELDS}
    if not incoming:
        return
    candidate = replace(settings, **incoming)
    validate_illustrated_preferences(candidate)
    for key, value in incoming.items():
        setattr(settings, key, value)


def tesseract_languages(settings: Any) -> str:
    return "+".join(languages(str(getattr(settings, "illustrated_ocr_languages", "eng"))))


def effective_ocr_roi(settings: Any, image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    validate_illustrated_preferences(settings)
    width, height = image_size
    left = round(width * float(settings.illustrated_ocr_side_percent) / 100)
    right = width - left
    top = round(height * float(settings.illustrated_ocr_top_percent) / 100)
    bottom = height - round(height * float(settings.illustrated_ocr_bottom_percent) / 100)
    if right <= left or bottom <= top:
        raise ValueError("图解 OCR 的有效区域为空")
    return left, top, right, bottom
