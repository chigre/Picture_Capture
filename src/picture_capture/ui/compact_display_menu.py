"""Compact display palette with explicit, one-line control groups.

The underlying app quick-variable state and existing callbacks remain the
single source of truth; this file only creates one compact presentation.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import font, ttk
from typing import Any, Callable

from picture_capture.adaptive_denoise import DENOISE_ENV
from picture_capture.layout_visualization_ui_v3 import (
    _invalidate_layout_snapshot,
    _set_layout_exclusive_visibility,
)

DISPLAY_MODES = (
    "原图+标注", "二值+标注", "仅原图", "仅二值",
    "切图预览", "OCR词头区域预览",
)

# Swatches have 25% of their 24-pixel height as vertical whitespace on
# *both* sides; the visible coloured strip therefore occupies the middle 50%.
SWATCH_HEIGHT = 24
SWATCH_VERTICAL_PADDING_FRACTION = 0.25
# Keep checkbox captions in a stable first column; move overflow below.
DISPLAY_CAPTION_WIDTH = 126
DISPLAY_ROW_PADDING = (2, 2)


def build_compact_display_menu(app: Any, parent: tk.Misc) -> ttk.Frame:
    """Build the requested single-line groups inside a 280px tool palette."""
    panel = ttk.Frame(parent, padding=(4, 3, 4, 6))
    qv, qb, qc = app.quick_vars, app.quick_bool_vars, app.quick_color_vars

    style = ttk.Style(panel)
    style.configure("PC.Display.TCheckbutton", padding=(0, 1))
    style.configure("PC.Display.TCombobox", padding=(0, 0))
    style.configure("PC.Display.TEntry", padding=(0, 0))

    def line() -> ttk.Frame:
        row = ttk.Frame(panel)
        row.pack(fill="x", pady=DISPLAY_ROW_PADDING)
        return row

    def detail_line() -> ttk.Frame:
        """Align secondary attributes beneath the primary property column."""
        row = line()
        ttk.Frame(row, width=DISPLAY_CAPTION_WIDTH).pack(side="left")
        return row

    def label(row: tk.Misc, caption: str, width: int | None = None) -> ttk.Label:
        options = {"width": width} if width is not None else {}
        item = ttk.Label(row, text=caption, **options)
        item.pack(side="left", padx=(0, 3), pady=0)
        return item

    def check(row: tk.Misc, caption: str, variable: tk.Variable,
              action: Callable[..., Any] | None = None) -> ttk.Checkbutton:
        item = ttk.Checkbutton(
            row, text=caption, variable=variable, command=action,
            style="PC.Display.TCheckbutton",
        )
        item.pack(side="left", padx=(0, 4), pady=0)
        return item

    def primary_check(row: ttk.Frame, caption: str, variable: tk.Variable,
                      action: Callable[..., Any] | None = None) -> ttk.Checkbutton:
        """Reserve the same width before every swatch/width input group."""
        holder = ttk.Frame(row, width=DISPLAY_CAPTION_WIDTH, height=26)
        holder.pack(side="left")
        holder.pack_propagate(False)
        return check(holder, caption, variable, action)

    def entry(row: tk.Misc, name: str, chars: int = 3) -> ttk.Entry:
        item = ttk.Entry(
            row, textvariable=qv[name], width=chars, justify="center",
            style="PC.Display.TEntry",
        )
        item.pack(side="left", padx=(0, 4), pady=0)
        return item

    def value(row: tk.Misc, caption: str, name: str, chars: int = 3) -> None:
        label(row, caption, width=10 if not row.winfo_children() else None)
        entry(row, name, chars)

    def swatch(row: tk.Misc, key: str) -> tk.Button:
        holder = ttk.Frame(row, width=20, height=SWATCH_HEIGHT)
        holder.pack(side="left", padx=(1, 4), pady=0)
        holder.pack_propagate(False)
        button = tk.Button(holder, bd=0, borderwidth=0, highlightthickness=0,
                           padx=0, pady=0, cursor="hand2")
        button.place(
            relx=0, rely=SWATCH_VERTICAL_PADDING_FRACTION, relwidth=1,
            relheight=1 - 2 * SWATCH_VERTICAL_PADDING_FRACTION,
        )
        button.configure(command=lambda: app.choose_overlay_color(key, button))

        def refresh(*_args: Any) -> None:
            try:
                app._style_color_button(button, str(qc[key].get()))
            except tk.TclError:
                pass

        qc[key].trace_add("write", refresh)
        refresh()
        return button

    def divider() -> None:
        ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=(7, 6))

    def family(row: ttk.Frame, name: str) -> ttk.Combobox:
        families = ("自动（系统推荐）", *tuple(sorted(set(font.families()), key=str.casefold)))
        combo = ttk.Combobox(
            row, textvariable=qv[name], values=families, state="normal",
            style="PC.Display.TCombobox",
        )
        combo.pack(side="left", fill="x", expand=True, padx=0, pady=0)
        return combo

    def family_line(name: str) -> None:
        row = line()
        label(row, "字体:", width=10)
        family(row, name)

    def font_style(row: ttk.Frame, size: str, bold: str, italic: str) -> None:
        label(row, "字号:", width=10)
        entry(row, size, 4)
        check(row, "粗", qb[bold])
        check(row, "斜", qb[italic])

    def dropdown(caption: str, variable: tk.Variable, choices: tuple[str, ...],
                 callback: Callable[..., Any] | None = None) -> None:
        row = line()
        label(row, caption, width=10)
        item = ttk.Combobox(
            row, textvariable=variable, values=choices,
            state="readonly", style="PC.Display.TCombobox",
        )
        item.pack(side="left", fill="x", expand=True, padx=(2, 0), pady=0)
        if callback is not None:
            item.bind("<<ComboboxSelected>>", callback)

    # Group 1: all main-canvas visibility controls, ONE line per feature.
    row = line()
    primary_check(row, "自动保存", app.autosave_var, app.toggle_autosave)
    value(row, "间隔时间(秒)", "batch_interval", 3)

    check(line(), "隐藏线框（插图除外）", app.hide_var, app._toggle_hide_overlays)

    row = line()
    primary_check(row, "显示标尺", qb["show_rulers"],
          lambda: app._apply_overlay_visibility_toggle("show_rulers", qb["show_rulers"]))
    swatch(row, "ruler_color")

    row = line()
    primary_check(row, "显示区块", qb["show_page_sections"],
          lambda: app._apply_overlay_visibility_toggle("show_page_sections", qb["show_page_sections"]))
    swatch(row, "page_section_color")
    value(row, "宽:", "page_section_width", 2)

    row = line()
    primary_check(row, "栏左垂线", qb["show_column_guides"], app._quick_parameter_changed)
    swatch(row, "guide_color")
    value(row, "宽:", "guide_width", 3)
    value(detail_line(), "透明度%:", "guide_opacity", 5)

    row = line()
    primary_check(row, "词头横线", qb["show_headword_markers"], app._quick_parameter_changed)
    swatch(row, "headword_marker_color")
    value(row, "宽:", "marker_height", 3)
    value(detail_line(), "透明度%:", "headword_marker_opacity", 5)

    divider()

    # Group 2: illustration shape and label. Each visual property remains
    # on its specified line, not a generic verticalized grid.
    row = line()
    primary_check(row, "插图形状:线", app.polygon_var, app.redraw)
    swatch(row, "illustration_outline_color")
    value(row, "宽:", "illustration_outline_width", 3)
    row = detail_line()
    label(row, "底色")
    swatch(row, "illustration_fill_color")
    value(detail_line(), "透明度%:", "illustration_fill_opacity", 5)

    row = line()
    primary_check(row, "插图标签:线", qb["show_illustration_labels"],
          lambda: app._apply_overlay_visibility_toggle(
              "show_illustration_labels", qb["show_illustration_labels"],
          ))
    swatch(row, "illustration_label_border_color")
    value(row, "宽:", "illustration_label_border_width", 3)
    row = detail_line()
    label(row, "底色")
    swatch(row, "illustration_label_fill_color")

    family_line("illustration_label_font_family")
    font_style(line(), "illustration_label_font_size",
               "illustration_label_font_bold", "illustration_label_font_italic")

    divider()

    # Group 3: editable headword label, background, fixed/zoom behaviour.
    visible = qb.get("show_main_entry_labels")
    if visible is None:
        visible = tk.BooleanVar(value=bool(app.settings.show_main_entry_labels))
        qb["show_main_entry_labels"] = visible
        visible.trace_add("write", lambda *_: app._quick_parameter_changed())

    row = line()
    primary_check(row, "词头标签", visible,
          lambda: app._apply_overlay_visibility_toggle("show_main_entry_labels", visible))
    label(row, "底色")
    swatch(row, "main_entry_default_color")
    check(row, "缩放", qb["main_entry_follow_zoom"])

    row = line()
    value(row, "宽度(字符)", "main_entry_width_chars", 4)
    value(detail_line(), "偏移%:", "main_entry_x_ratio", 5)
    family_line("main_entry_font_family")
    font_style(line(), "main_entry_font_size",
               "main_entry_font_bold", "main_entry_font_italic")

    divider()

    # Group 4: diagnostic OCR overlays.
    for caption, key in (
        ("显示OCR内容选择器", "review_main_show_ocr_choices"),
        ("显示OCR对比底色结果", "review_main_show_ocr_background"),
        ("显示单行画线候选框", "paddle_show_candidate_checkboxes"),
    ):
        row = line()
        check(row, caption, qb[key],
              lambda setting=key: app._apply_overlay_visibility_toggle(setting, qb[setting]))

    divider()

    # Group 5: appearance and exclusive display mode. Keep right-ratio directly
    # below display mode while preserving the pre-existing quick variable.
    dropdown("颜色模式", app.appearance_mode_var,
             ("浅色", "深色", "跟随系统"), app._appearance_mode_selected)
    dropdown("显示模式", app.display_mode_var, DISPLAY_MODES, app._apply_display_mode)
    row = line()
    value(row, "向右比例%", "right_ratio", 4)

    row = line()
    layout_var = app._layout_visualization_var

    def toggle_layout() -> None:
        _set_layout_exclusive_visibility(app, bool(layout_var.get()))
        _invalidate_layout_snapshot(app)
        app.redraw()

    primary_check(row, "显示Layout", layout_var, toggle_layout)
    label(row, "去噪强度")

    def apply_denoise(_event: Any = None) -> None:
        from picture_capture.layout_visualization_ui_v3 import _DENOISE_LABEL_TO_VALUE
        os.environ[DENOISE_ENV] = _DENOISE_LABEL_TO_VALUE.get(
            str(app._analysis_denoise_strength_var.get()), "auto",
        )
        _invalidate_layout_snapshot(app)
        app.redraw()

    denoise = ttk.Combobox(
        row, textvariable=app._analysis_denoise_strength_var,
        values=("关闭", "弱", "自动", "强"), state="readonly",
        width=6, style="PC.Display.TCombobox",
    )
    denoise.pack(side="left", padx=0, pady=0)
    denoise.bind("<<ComboboxSelected>>", apply_denoise)

    row = line()
    label(row, "切图预览标签:", width=12)
    check(row, "缩放", qb["crop_preview_follow_zoom"])
    font_style(line(), "crop_preview_font_size",
               "crop_preview_font_bold", "crop_preview_font_italic")
    family_line("crop_preview_font_family")
    return panel


__all__ = [
    "DISPLAY_MODES", "SWATCH_HEIGHT", "SWATCH_VERTICAL_PADDING_FRACTION",
    "DISPLAY_CAPTION_WIDTH", "DISPLAY_ROW_PADDING",
    "build_compact_display_menu",
]
