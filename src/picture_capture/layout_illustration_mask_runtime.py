from __future__ import annotations

"""Compatibility UI/cache integration for illustration masking.

Mask policy and Page Understanding preprocessing are static. This remaining
runtime seam only exposes the Settings Center control and includes the setting
in the Layout visualization cache key.
"""

from functools import wraps
from typing import Any

from .layout_illustration_mask import (
    DEFAULT_ENABLED,
    IllustrationMaskStats,
    SETTING_LABEL,
    SETTING_NAME,
    layout_mask_region_is_large_enough,
    mask_large_illustrations_for_layout,
)


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
    "install_layout_illustration_mask_ui",
    "layout_mask_region_is_large_enough",
    "mask_large_illustrations_for_layout",
]
