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
    UNLINED_BLANK_INK_PERCENT_KEY,
    UNLINED_FILTER_BLANK_KEY,
    UNLINED_FILTER_ENABLED_KEY,
)
from .project_storage import crop_settings_path

CROP_SETTINGS_FILENAME = "_CropSettings.json"
FILTER_ENABLED_KEY = UNLINED_FILTER_ENABLED_KEY
FILTER_BLANK_KEY = UNLINED_FILTER_BLANK_KEY
BLANK_INK_PERCENT_KEY = UNLINED_BLANK_INK_PERCENT_KEY
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
    "只导出接近空白的未画线行。空白判断在白边裁切之前进行：先估计该切片自己的纸张背景亮度，"
    "再计算明显暗于背景的有效墨迹像素占比。墨迹占比不高于设定阈值时视为接近空白。"
    "全白切片也会保留并导出，便于检查 Layout 是否恢复了不存在的文字行。"
)
THRESHOLD_HELP = (
    "接近空白的最大有效墨迹占比。默认 0.8%。值越大，越多含少量字迹/污点的切片会被归为接近空白；"
    "值越小越严格。该比例基于原始 Layout 行框计算，不受后续白边裁切影响。"
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
        threshold = float(payload.get(BLANK_INK_PERCENT_KEY, DEFAULT_BLANK_INK_PERCENT))
    except (TypeError, ValueError):
        threshold = DEFAULT_BLANK_INK_PERCENT
    threshold = max(MIN_BLANK_INK_PERCENT, min(MAX_BLANK_INK_PERCENT, threshold))
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
    blank_ink_percent: float,
) -> Path:
    path = _settings_path(Path(project_root))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_payload(Path(project_root))
    payload[FILTER_ENABLED_KEY] = bool(enabled)
    payload[FILTER_BLANK_KEY] = bool(blank)
    payload[BLANK_INK_PERCENT_KEY] = float(max(
        MIN_BLANK_INK_PERCENT,
        min(MAX_BLANK_INK_PERCENT, float(blank_ink_percent)),
    ))

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
    "BLANK_INK_PERCENT_KEY",
    "DEFAULT_BLANK_INK_PERCENT",
    "FILTER_BLANK_KEY",
    "FILTER_ENABLED_KEY",
    "load_unlined_filter_settings",
    "save_unlined_filter_settings",
    "install_unlined_export_filter_settings_ui",
]
