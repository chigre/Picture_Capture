"""Dedicated illustration settings task page; uses existing persisted AppSettings fields."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .schema import (
    ILLUSTRATION_APPEARANCE_FIELDS, ILLUSTRATION_CHECKS,
    ILLUSTRATION_DETECTION_FIELDS,
)

def build_illustration_settings_tab(dialog: object, tab: ttk.Frame) -> None:
    page = dialog._scrollable_settings_page(tab)
    dialog._settings_intro(
        page, "插图自动检测与标注",
        "识别阈值用于自动生成 PPP 插图区域；颜色、透明度、轮廓及标签仅改变画布显示。"
        "现有项目默认值保持不变，手工绘制的 PPP 区域不会因调整阈值而自动删除。",
    )
    dialog._add_setting_group(
        page, "自动识别阈值与边界",
        ILLUSTRATION_DETECTION_FIELDS,
        intro="灰度阈值越高，允许较浅的墨迹；候选宽、高必须同时达到设定下限。"
              "尺寸单位可填 % 或 px（切换单位不自动换算数值）；墨迹占比越高筛选越保守。"
              "阈值修改后需重新运行“插图识别”才能改变已有自动区域。",
    )
    dialog._add_check_group(page, "插图与 Layout", ILLUSTRATION_CHECKS[:2])
    dialog._add_setting_group(
        page, "插图区域、边框与标签",
        ILLUSTRATION_APPEARANCE_FIELDS,
        intro="颜色字段统一显示实色的选色按钮，旁边仍可手动输入 #RRGGBB；"
              "标签样式只影响标注，不修改 PPP 坐标。",
    )
    dialog._add_check_group(page, "标签显示与字形", ILLUSTRATION_CHECKS[2:])
