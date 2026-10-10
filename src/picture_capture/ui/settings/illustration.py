"""Dedicated illustration settings task page; uses existing persisted AppSettings fields."""
from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk

from .schema import (
    ILLUSTRATION_APPEARANCE_FIELDS, ILLUSTRATION_CHECKS,
    ILLUSTRATION_DETECTION_FIELDS,
)

COLOR_FIELDS = frozenset({
    "illustration_outline_color", "illustration_fill_color",
    "illustration_label_border_color", "illustration_label_fill_color",
})


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
        intro="灰度阈值越高，允许较浅的墨迹；最小面积和墨迹占比越高，识别越保守。"
              "阈值修改后需重新运行“插图识别”才能改变已有自动区域。",
    )
    dialog._add_check_group(page, "插图与 Layout", ILLUSTRATION_CHECKS[:1])
    group = dialog._add_setting_group(
        page, "插图区域、边框与标签",
        ILLUSTRATION_APPEARANCE_FIELDS,
        intro="颜色使用 #RRGGBB；标签样式只影响标注，不修改 PPP 坐标。",
    )
    for name in COLOR_FIELDS:
        variable = dialog.vars.get(name)
        if variable is None:
            continue
        # Reuse the same settings variable, so automatic saving is unchanged.
        row = 1 + list(ILLUSTRATION_APPEARANCE_FIELDS).index(name)
        control = group.grid_slaves(row=row, column=1)
        if not control:
            continue
        def choose(v=variable):
            chosen = colorchooser.askcolor(color=str(v.get()), parent=dialog)[1]
            if chosen:
                v.set(chosen)
        ttk.Button(control[0], text="选色…", command=choose).grid(
            row=0, column=2, padx=(8, 0),
        )
    dialog._add_check_group(page, "标签显示与字形", ILLUSTRATION_CHECKS[1:])
