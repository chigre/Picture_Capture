"""Compact, task-specific display palette built from the existing quick-setting state.

All fields share the original Tk variables and callbacks. The wide legacy
display section is kept only as a source of those variables; it is never shown.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import font, ttk
from typing import Any

from picture_capture.adaptive_denoise import DENOISE_ENV
from picture_capture.layout_visualization_ui_v3 import (
    _invalidate_layout_snapshot,
    _set_layout_exclusive_visibility,
)

DISPLAY_MODES = (
    "原图+标注", "二值+标注", "仅原图", "仅二值",
    "切图预览", "OCR词头区域预览",
)


def build_compact_display_menu(app: Any, parent: tk.Misc) -> ttk.Frame:
    """Create the single 300px display menu, in the requested reading order."""
    panel = ttk.Frame(parent, padding=(5, 4, 5, 7))
    qv = app.quick_vars
    qb = app.quick_bool_vars
    qc = app.quick_color_vars

    def line() -> ttk.Frame:
        frame = ttk.Frame(panel)
        frame.pack(fill="x", pady=(2, 2))
        return frame

    def label(parent: tk.Misc, value: str) -> ttk.Label:
        widget = ttk.Label(parent, text=value)
        widget.pack(side="left", padx=(2, 2))
        return widget

    def check(parent: tk.Misc, title: str, variable: tk.Variable, action: Any = None) -> ttk.Checkbutton:
        widget = ttk.Checkbutton(parent, text=title, variable=variable, command=action)
        widget.pack(side="left", padx=(0, 2))
        return widget

    def field(parent: tk.Misc, name: str, width: int = 4) -> ttk.Entry:
        widget = ttk.Entry(parent, textvariable=qv[name], width=width)
        widget.pack(side="left", padx=(0, 3))
        return widget

    def number_line(names: tuple[tuple[str, str, int], ...]) -> None:
        row = line()
        for caption, name, width in names:
            label(row, caption)
            field(row, name, width)

    def swatch(parent: tk.Misc, key: str) -> tk.Button:
        button = tk.Button(parent, width=2, height=1, bd=1, padx=0, pady=0)
        button.configure(command=lambda: app.choose_overlay_color(key, button))
        button.pack(side="left", padx=(1, 4))
        def repaint(*_args: Any) -> None:
            try:
                app._style_color_button(button, str(qc[key].get()))
            except tk.TclError:
                pass
        qc[key].trace_add("write", repaint)
        repaint()
        return button

    def divider() -> None:
        ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=(8, 7))

    def combo_row(caption: str, variable: tk.Variable, values: tuple[str, ...],
                  action: Any = None, width: int = 19) -> ttk.Combobox:
        row = line()
        if caption:
            label(row, caption)
        control = ttk.Combobox(
            row, textvariable=variable, values=values,
            state="readonly", width=width,
        )
        control.pack(side="left", fill="x", expand=True)
        if action is not None:
            control.bind("<<ComboboxSelected>>", action)
        return control

    def font_block(family_name: str, size_name: str, bold_name: str,
                   italic_name: str, *, follow: str | None = None,
                   heading: str | None = None) -> None:
        if heading:
            ttk.Label(panel, text=heading).pack(anchor="w", padx=2, pady=(3, 0))
        families = ("自动（系统推荐）", *tuple(sorted(set(font.families()), key=str.casefold)))
        combo_row("", qv[family_name], families, width=19)
        row = line()
        label(row, "字号")
        field(row, size_name, 4)
        check(row, "粗", qb[bold_name])
        check(row, "斜", qb[italic_name])
        if follow is not None:
            # Separate narrow row: size + two style checks + zoom does not
            # reliably fit within 300px on Windows with Chinese system fonts.
            follow_row = line()
            check(follow_row, "跟随缩放", qb[follow])

    # General display.
    row = line()
    check(row, "自动保存", app.autosave_var, app.toggle_autosave)
    label(row, "间隔时间(秒)")
    field(row, "batch_interval", 4)

    row = line()
    check(row, "隐藏线框(插图除外)", app.hide_var, app._toggle_hide_overlays)

    row = line()
    check(row, "显示标尺", qb["show_rulers"],
          lambda: app._apply_overlay_visibility_toggle("show_rulers", qb["show_rulers"]))
    swatch(row, "ruler_color")

    row = line()
    check(row, "显示区块", qb["show_page_sections"],
          lambda: app._apply_overlay_visibility_toggle("show_page_sections", qb["show_page_sections"]))
    swatch(row, "page_section_color")
    label(row, "线宽")
    field(row, "page_section_width", 3)

    row = line()
    check(row, "栏左垂线", qb["show_column_guides"], app._quick_parameter_changed)
    swatch(row, "guide_color")
    number_line((("线宽", "guide_width", 3), ("透%", "guide_opacity", 4)))

    row = line()
    check(row, "词头横线", qb["show_headword_markers"], app._quick_parameter_changed)
    swatch(row, "headword_marker_color")
    number_line((("线宽", "marker_height", 3), ("透%", "headword_marker_opacity", 4)))

    divider()

    row = line()
    check(row, "插图形状:轮廓", app.polygon_var, app.redraw)
    swatch(row, "illustration_outline_color")
    number_line((("线宽", "illustration_outline_width", 3),))
    row = line()
    label(row, "背景")
    swatch(row, "illustration_fill_color")
    label(row, "透%")
    field(row, "illustration_fill_opacity", 4)

    row = line()
    check(row, "插图标签:外框", qb["show_illustration_labels"],
          lambda: app._apply_overlay_visibility_toggle("show_illustration_labels", qb["show_illustration_labels"]))
    swatch(row, "illustration_label_border_color")
    label(row, "线宽")
    field(row, "illustration_label_border_width", 3)
    row = line()
    label(row, "背景")
    swatch(row, "illustration_label_fill_color")
    font_block(
        "illustration_label_font_family", "illustration_label_font_size",
        "illustration_label_font_bold", "illustration_label_font_italic",
        heading="字体",
    )

    divider()

    visible_var = qb.get("show_main_entry_labels")
    if visible_var is None:
        visible_var = tk.BooleanVar(value=bool(app.settings.show_main_entry_labels))
        qb["show_main_entry_labels"] = visible_var
        visible_var.trace_add("write", lambda *_: app._quick_parameter_changed())
    row = line()
    check(row, "词头标签", visible_var,
          lambda: app._apply_overlay_visibility_toggle("show_main_entry_labels", visible_var))
    label(row, "背景")
    swatch(row, "main_entry_default_color")
    row = line()
    check(row, "跟随缩放", qb["main_entry_follow_zoom"])
    number_line((("宽度(字符)", "main_entry_width_chars", 4), ("偏移%", "main_entry_x_ratio", 4)))
    font_block(
        "main_entry_font_family", "main_entry_font_size",
        "main_entry_font_bold", "main_entry_font_italic",
        heading="字体",
    )

    divider()

    for text, key in (
        ("显示OCR内容选择器", "review_main_show_ocr_choices"),
        ("显示OCR对比底色结果", "review_main_show_ocr_background"),
        ("显示单行画线候选框", "paddle_show_candidate_checkboxes"),
    ):
        row = line()
        check(row, text, qb[key],
              lambda n=key: app._apply_overlay_visibility_toggle(n, qb[n]))

    divider()

    combo_row("颜色模式", app.appearance_mode_var, ("浅色", "深色", "跟随系统"),
              app._appearance_mode_selected, width=12)
    combo_row("显示模式", app.display_mode_var, DISPLAY_MODES,
              app._apply_display_mode, width=14)

    row = line()
    layout_var = app._layout_visualization_var
    def toggle_layout() -> None:
        _set_layout_exclusive_visibility(app, bool(layout_var.get()))
        _invalidate_layout_snapshot(app)
        app.redraw()
    check(row, "显示Layout", layout_var, toggle_layout)

    def apply_denoise(_event: Any = None) -> None:
        from picture_capture.layout_visualization_ui_v3 import _DENOISE_LABEL_TO_VALUE
        os.environ[DENOISE_ENV] = _DENOISE_LABEL_TO_VALUE.get(
            str(app._analysis_denoise_strength_var.get()), "auto"
        )
        _invalidate_layout_snapshot(app)
        app.redraw()
    combo_row("去噪强度", app._analysis_denoise_strength_var,
              ("关闭", "弱", "自动", "强"), apply_denoise, width=12)

    font_block(
        "crop_preview_font_family", "crop_preview_font_size",
        "crop_preview_font_bold", "crop_preview_font_italic",
        follow="crop_preview_follow_zoom",
        heading="切图预览标签字体",
    )
    return panel


__all__ = ["DISPLAY_MODES", "build_compact_display_menu"]
