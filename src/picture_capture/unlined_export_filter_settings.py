from __future__ import annotations

"""Persistence helpers for Layout-derived unlined-row export filters.

The options live in the existing ``QT/_CropSettings.json`` store. Settings
Center presentation/payload ownership is static in ``ui.settings.crop``; this
module retains the compatibility key aliases and raw-file helpers consumed by
workers/controllers.
"""

from pathlib import Path
import json
import os
import tempfile
from typing import Any

from .crop.settings import (
    DEFAULT_UNLINED_BLANK_INK_PERCENT,
    MAX_UNLINED_BLANK_INK_PERCENT,
    MIN_UNLINED_BLANK_INK_PERCENT,
    UNLINED_BLANK_INK_PERCENT_KEY,  # Obsolete setting removed on save.
    UNLINED_LEFT_WHITE_PERCENT_KEY,
    DEFAULT_UNLINED_LEFT_WHITE_PERCENT,
    MIN_UNLINED_LEFT_WHITE_PERCENT,
    MAX_UNLINED_LEFT_WHITE_PERCENT,
    UNLINED_FILTER_BLANK_KEY,
    UNLINED_FILTER_ENABLED_KEY,
)
from .project_storage import crop_settings_path

CROP_SETTINGS_FILENAME = "_CropSettings.json"
FILTER_ENABLED_KEY = UNLINED_FILTER_ENABLED_KEY
FILTER_BLANK_KEY = UNLINED_FILTER_BLANK_KEY
BLANK_INK_PERCENT_KEY = UNLINED_BLANK_INK_PERCENT_KEY  # deprecated
LEFT_WHITE_PERCENT_KEY = UNLINED_LEFT_WHITE_PERCENT_KEY
DEFAULT_LEFT_WHITE_PERCENT = DEFAULT_UNLINED_LEFT_WHITE_PERCENT
MIN_LEFT_WHITE_PERCENT = MIN_UNLINED_LEFT_WHITE_PERCENT
MAX_LEFT_WHITE_PERCENT = MAX_UNLINED_LEFT_WHITE_PERCENT
FILTER_LABEL = "未画线行导出过滤"
BLANK_LABEL = "空白"
DEFAULT_BLANK_INK_PERCENT = DEFAULT_UNLINED_BLANK_INK_PERCENT
MIN_BLANK_INK_PERCENT = MIN_UNLINED_BLANK_INK_PERCENT
MAX_BLANK_INK_PERCENT = MAX_UNLINED_BLANK_INK_PERCENT

FILTER_HELP = (
    "开启后，【未画线行导出】会按后面的子条件筛选 Layout 已恢复但当前没有 PDIC 横线的文字行。"
    "目前可选【空白】；如果没有勾选任何子条件，则等同于不过滤。"
)
BLANK_HELP = (
    "针对【后期制作 → 切图宽度(%栏)】指定的栏左切片，寻找从其左边缘开始连续没有文字墨迹的宽度。"
    "只导出左侧连续白色宽度占切片宽度超过阈值的未画线候选行（例如5%栏宽切片，阈值50%）。"
    "通过过滤的切片直接保留完整行框和原始左白边，不执行白边修剪；按页合并时也保留该白边。"
)
THRESHOLD_HELP = (
    "左侧连续白色宽度 / 当前切片宽度 × 100%，默认50%，范围0–100%。严格大于阈值才保留。"
    "从左向右寻找有实际文字墨迹的首列：纸色自适应阈值结合小连通块过滤，"
    "轻微孤立污点按空白处理，不会截断连续白宽；明显笔画仍计为墨迹。"
    "整个切片无有效墨迹时视为100%；不再使用旧的整体墨迹占比0.8%判断。"
)


def _settings_path(project_root: Path) -> Path:
    return crop_settings_path(Path(project_root), CROP_SETTINGS_FILENAME)


def _read_payload(project_root: Path) -> dict[str, Any]:
    path = _settings_path(project_root)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


def load_unlined_filter_settings(project_root: Path) -> tuple[bool, bool, float]:
    payload = _read_payload(Path(project_root))
    try:
        threshold = float(payload.get(LEFT_WHITE_PERCENT_KEY, DEFAULT_LEFT_WHITE_PERCENT))
        if not MIN_LEFT_WHITE_PERCENT <= threshold <= MAX_LEFT_WHITE_PERCENT:
            threshold = DEFAULT_LEFT_WHITE_PERCENT
    except (TypeError, ValueError, OverflowError):
        threshold = DEFAULT_LEFT_WHITE_PERCENT
    return (
        bool(payload.get(FILTER_ENABLED_KEY, False)),
        bool(payload.get(FILTER_BLANK_KEY, False)),
        float(threshold),
    )


def save_unlined_filter_settings(
    project_root: Path,
    *,
    enabled: bool,
    blank: bool,
    left_white_percent: float,
) -> Path:
    path = _settings_path(Path(project_root))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_payload(Path(project_root))
    payload[FILTER_ENABLED_KEY] = bool(enabled)
    payload[FILTER_BLANK_KEY] = bool(blank)
    value = float(left_white_percent)
    if not MIN_LEFT_WHITE_PERCENT <= value <= MAX_LEFT_WHITE_PERCENT:
        raise ValueError("左侧连续白色宽度阈值必须在 0–100% 之间")
    payload[LEFT_WHITE_PERCENT_KEY] = value
    payload.pop(BLANK_INK_PERCENT_KEY, None)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return path


def install_unlined_export_filter_settings_ui(app_module: Any) -> None:
    """Compatibility no-op; Settings crop ownership is static."""
    _ = app_module


__all__ = [
    "BLANK_INK_PERCENT_KEY",  # Compatibility-only, no longer written.
    "DEFAULT_BLANK_INK_PERCENT",
    "LEFT_WHITE_PERCENT_KEY",
    "DEFAULT_LEFT_WHITE_PERCENT",
    "MIN_LEFT_WHITE_PERCENT",
    "MAX_LEFT_WHITE_PERCENT",
    "FILTER_BLANK_KEY",
    "FILTER_ENABLED_KEY",
    "load_unlined_filter_settings",
    "save_unlined_filter_settings",
    "install_unlined_export_filter_settings_ui",
]
