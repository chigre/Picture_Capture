"""Purpose-built compact panels for preprocessing, layout, OCR and drawing.

All controls bind to the original main-window variables and action methods.
The broad legacy sections remain hidden only as state/compatibility owners.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from .compact_layout_profile_menu import LAYOUT_ROWS, build_layout_profile_menu

def _row(panel: ttk.Frame) -> ttk.Frame:
    frame = ttk.Frame(panel)
    frame.pack(fill="x", padx=(2, 2), pady=(2, 2))
    return frame


def _label(row: ttk.Frame, text: str, width: int | None = None) -> None:
    options = {"width": width} if width is not None else {}
    ttk.Label(row, text=text, **options).pack(side="left", padx=(0, 3), pady=0)


def _button(row: ttk.Frame, text: str, command: Callable[[], Any],
            *, expand: bool = True) -> ttk.Button:
    button = ttk.Button(row, text=text, command=command, style="PC.Compact.TButton")
    button.pack(side="left", fill="x" if expand else "none", expand=expand,
                padx=(0, 3), pady=0)
    return button


def _check(row: ttk.Frame, text: str, variable: tk.Variable,
           command: Callable[[], Any] | None = None) -> ttk.Checkbutton:
    widget = ttk.Checkbutton(row, text=text, variable=variable, command=command)
    widget.pack(side="left", padx=(0, 4), pady=0)
    return widget


def _entry(row: ttk.Frame, variable: tk.Variable, width: int = 5,
           change: Callable[..., Any] | None = None) -> ttk.Entry:
    widget = ttk.Entry(row, textvariable=variable, width=width, justify="center")
    widget.pack(side="left", padx=(0, 4), pady=0)
    if change is not None:
        widget.bind("<Return>", change)
        widget.bind("<FocusOut>", change)
    return widget


def _select(row: ttk.Frame, variable: tk.Variable, values: tuple[str, ...],
            *, width: int = 13, command: Callable[..., Any] | None = None
            ) -> ttk.Combobox:
    widget = ttk.Combobox(row, textvariable=variable, values=values,
                          state="readonly", width=width)
    widget.pack(side="left", fill="x", expand=True, padx=(2, 0), pady=0)
    if command is not None:
        widget.bind("<<ComboboxSelected>>", command)
    return widget


def _separator(panel: ttk.Frame) -> None:
    ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=(5, 5))


def _panel(parent: tk.Misc) -> ttk.Frame:
    return ttk.Frame(parent, padding=(3, 3, 3, 4))


def build_preprocess_menu(app: Any, parent: tk.Misc) -> ttk.Frame:
    panel = _panel(parent)
    # One-row geometry is intentional; labels/buttons were moved rather than
    # reducing font sizes or discarding the underlying preprocessing actions.
    app.preprocess_mode_button = _button(_row(panel), "进入预处理模式",
                                          app.toggle_preprocess_mode)
    if app._preprocess_mode_active():
        app.preprocess_mode_button.configure(text="退出预处理模式")

    row = _row(panel)
    _check(row, "自动纠偏", app.preprocess_auto_deskew_var,
           app._preprocess_settings_changed)
    _label(row, "安全边界px:")
    _entry(row, app.preprocess_safety_var, 4, app._preprocess_settings_changed)

    row = _row(panel)
    _label(row, "几何纠正模式", width=12)
    _select(row, app.preprocess_geometry_var, (
        "自动几何（推荐）", "轻量：旋转+裁边",
        "自动透视", "UVDoc展平（Paddle高级）",
    ), command=app._preprocess_settings_changed)

    row = _row(panel)
    _button(row, "手动四角", app.edit_preprocess_corners)
    _button(row, "重置四角", app.reset_preprocess_corners)
    row = _row(panel)
    _button(row, "分析诊断", app.analyze_preprocess_selected)
    _button(row, "诊断信息", app.show_preprocess_diagnostics)
    row = _row(panel)
    _button(row, "上一需检", lambda: app.jump_preprocess_review(-1))
    _button(row, "下一需检", lambda: app.jump_preprocess_review(1))
    _separator(panel)

    row = _row(panel)
    _check(row, "统一页面大小", app.preprocess_export_canvas_var,
           app._preprocess_export_settings_changed)
    _select(row, app.preprocess_export_canvas_mode_var,
            ("本批最大裁剪尺寸", "自定义尺寸"),
            command=app._preprocess_export_settings_changed, width=14)

    row = _row(panel)
    _label(row, "页面宽×高px:")
    _entry(row, app.preprocess_export_canvas_width_var, 6,
           app._preprocess_export_settings_changed)
    _label(row, "×")
    _entry(row, app.preprocess_export_canvas_height_var, 6,
           app._preprocess_export_settings_changed)
    _label(_row(panel), "页边空px:")
    margins = (
        (("上", app.preprocess_export_margin_top_var),
         ("下", app.preprocess_export_margin_bottom_var)),
        (("左", app.preprocess_export_margin_left_var),
         ("右", app.preprocess_export_margin_right_var)),
    )
    for pair in margins:
        row = _row(panel)
        for caption, variable in pair:
            _label(row, caption, width=4)
            _entry(row, variable, 4, app._preprocess_export_settings_changed)
    _separator(panel)

    _label(_row(panel), "内容框排版:")
    row = _row(panel)
    _label(row, "水平X:", width=12)
    _select(row, app.preprocess_export_align_x_var,
            ("左对齐", "居中", "右对齐"),
            width=10, command=app._preprocess_export_settings_changed)
    row = _row(panel)
    _label(row, "垂直Y:", width=12)
    _select(row, app.preprocess_export_align_y_var,
            ("顶端对齐", "居中", "底部对齐"),
            width=10, command=app._preprocess_export_settings_changed)
    ttk.Label(panel, text="内容框在版心内排版；不足部分填白",
              wraplength=250).pack(anchor="w", pady=(1, 2))

    _button(_row(panel), "导出检查小图", app.export_preprocess_previews)
    _button(_row(panel), "导出预处理图片", app.export_preprocess_images)
    _button(_row(panel), "所选设为工作图片",
            app.promote_preprocessed_working_images)
    return panel


def build_layout_menu(app: Any, parent: tk.Misc) -> ttk.Frame:
    """Present the shared Project Profile and auto-layout settings compactly."""
    return build_layout_profile_menu(app, parent)



OCR_REFRESH_OPTIONS = {
    "使用有效缓存": "reuse",
    "重新OCR": "force",
}
OCR_PREPROCESS_OPTIONS = {
    "原图": "original",
    "灰度": "grayscale",
    "自动对比度": "auto_contrast",
    "二值化": "binary",
}


def _link_code_selection(
    code_var: tk.Variable, display_var: tk.Variable, options: dict[str, str],
) -> None:
    """Keep localized combobox text and canonical backend codes synchronized.

    Display strings are only presentation; the OCR runner still reads the
    original reuse/force and preprocessing identifiers.
    """
    to_label = {code: label for label, code in options.items()}

    def from_display(*_args: object) -> None:
        code = options.get(str(display_var.get()))
        if code is not None and str(code_var.get()) != code:
            code_var.set(code)

    def from_code(*_args: object) -> None:
        label = to_label.get(str(code_var.get()))
        if label is not None and str(display_var.get()) != label:
            display_var.set(label)

    display_var.trace_add("write", from_display)
    code_var.trace_add("write", from_code)
    from_code()


def _coded_select(
    row: ttk.Frame, code_var: tk.Variable, options: dict[str, str],
    *, width: int = 15,
) -> ttk.Combobox:
    display_var = tk.StringVar()
    _link_code_selection(code_var, display_var, options)
    return _select(row, display_var, tuple(options), width=width)


def build_ocr_menu(app: Any, parent: tk.Misc) -> ttk.Frame:
    """Compact OCR runtime settings; all choices reuse the existing backend."""
    panel = _panel(parent)

    row = _row(panel)
    _label(row, "识别策略")
    _coded_select(row, app.ocr_refresh_var, OCR_REFRESH_OPTIONS, width=15)

    _label(_row(panel), "OCR引擎:")
    row = _row(panel)
    for caption, field in (
        ("PaddleOCR", "paddle_use_paddleocr"),
        ("Tesseract", "paddle_compare_tesseract"),
    ):
        _check(row, caption, app.quick_bool_vars[field],
               app._quick_parameter_changed)

    row = _row(panel)
    _check(row, "Google Lens", app.quick_bool_vars["paddle_enable_lens"],
           app._quick_parameter_changed)
    from picture_capture.ocr_action_guard import LENS_MODE_VALUES
    _select(row, app.lens_mode_var, tuple(LENS_MODE_VALUES), width=13,
            command=app._quick_parameter_changed)

    row = _row(panel)
    _label(row, "OCR语言")
    _entry(row, app.quick_vars["ocr_language"], 17,
           app._quick_parameter_changed)

    row = _row(panel)
    _label(row, "识别带宽%")
    _entry(row, app.quick_vars["paddle_band_width_ratio"], 5,
           app._quick_parameter_changed)
    _label(row, "左缘容差")
    _entry(row, app.quick_vars["paddle_left_tolerance"], 4,
           app._quick_parameter_changed)

    row = _row(panel)
    _label(row, "横线与文字安全距离px")
    _entry(row, app.quick_vars["paddle_separator_safety_px"], 5,
           app._quick_parameter_changed)

    # The legacy quick panel never exposed this property. Register one canonical
    # string code in quick_vars so the normal autosave, Settings Center, project
    # loading and sync_quick_settings paths all agree.
    preprocessing_var = app.quick_vars.get("paddle_preprocessing")
    if preprocessing_var is None:
        preprocessing_var = tk.StringVar(
            value=str(getattr(app.settings, "paddle_preprocessing", "original")),
        )
        app.quick_vars["paddle_preprocessing"] = preprocessing_var
        app.quick_field_casts["paddle_preprocessing"] = str
        preprocessing_var.trace_add(
            "write", lambda *_args: app._quick_parameter_changed(),
        )
    row = _row(panel)
    _label(row, "OCR图像预处理")
    _coded_select(row, preprocessing_var, OCR_PREPROCESS_OPTIONS, width=14)

    _separator(panel)
    _button(_row(panel), "环境中心", app.check_ocr_engines)

    def open_ocr_line_settings() -> None:
        # An independent, already-built menu sits directly below OCR参数.
        from .workspace_tools import choose_workspace_section
        title = "三之一、OCR画线设置"
        app.workspace_tools_active = title
        choose_workspace_section(app, title)

    _button(_row(panel), "OCR画线设置...", open_ocr_line_settings)
    return panel

ACTION_GROUPS = (
    (("普通画线", "run_normal_draw_action"),
     ("仅OCR", "ocr_ordinary_lines_text_selected_scope")),
    (("融合画线+OCR", "run_combined_draw_action"),),
    (("OCR画线（默认）", "run_ocr_draw_action"),),
    None,
    (("清除画线", "clear_entries"), ("清除文本", "clear_text")),
    (("精修画线", "refine_lines_selected_scope"), ("保存当前页", "save_current_page")),
    None,
    (("词条校对", "open_review"),),
    (("选择词条文件", "select_existing_headwords_file"),
     ("新旧比较", "compare_old_new_selected_scope")),
    (("填充词条", "fill_existing_headwords"),
     ("修复排序", "repair_pdic_order_selected_scope")),
    (("备份PDIC", "backup_pdic"), ("恢复PDIC", "restore_from_pdic_backup")),
    None,
    (("插图识别", "detect_illustrations_selected_scope"),
     ("编辑插图", "toggle_polygon_drawing")),
    None,
    (("压缩OCR缓存", "cleanup_paddleocr_temp_selected_scope"),),
)


def build_drawing_menu(app: Any, parent: tk.Misc) -> ttk.Frame:
    panel = _panel(parent)
    for group in ACTION_GROUPS:
        if group is None:
            _separator(panel)
            continue
        row = _row(panel)
        for caption, method in group:
            button = _button(row, caption, getattr(app, method))
            if caption == "编辑插图":
                app.polygon_draw_button = button
                if app.polygon_draw_var.get():
                    button.configure(text="结束编辑插图", style="PC.EditActive.TButton")
    row = _row(panel)
    _check(row, "辅助线模式", app.auxiliary_mode_var, app.toggle_auxiliary_mode)
    _button(row, "撤销辅助线", app._auxiliary_controller.undo)
    return panel


__all__ = [
    "LAYOUT_ROWS", "ACTION_GROUPS",
    "build_preprocess_menu", "build_layout_menu",
    "build_ocr_menu", "build_drawing_menu",
]
