"""Purpose-built compact panels for preprocessing, layout, OCR and drawing.

All controls bind to the original main-window variables and action methods.
The broad legacy sections remain hidden only as state/compatibility owners.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from .compact_layout_profile_menu import LAYOUT_ROWS, build_layout_profile_menu
from .crop_width_equivalence import CropWidthEquivalence
from ..line_diff_bookmarks import bookmark_modified_line_pages

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
    traditional_only: list[ttk.Frame] = []

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
    traditional_only.append(row)
    _check(row, "Google Lens", app.quick_bool_vars["paddle_enable_lens"],
           app._quick_parameter_changed)
    from picture_capture.ocr_action_guard import LENS_MODE_VALUES
    _select(row, app.lens_mode_var, tuple(LENS_MODE_VALUES), width=13,
            command=app._quick_parameter_changed)

    row = _row(panel)
    traditional_only.append(row)
    _label(row, "OCR语言")
    _entry(row, app.quick_vars["ocr_language"], 17,
           app._quick_parameter_changed)

    row = _row(panel)
    traditional_only.append(row)
    _label(row, "识别带宽%")
    _entry(row, app.quick_vars["paddle_band_width_ratio"], 5,
           app._quick_parameter_changed)
    _label(row, "左缘容差")
    _entry(row, app.quick_vars["paddle_left_tolerance"], 4,
           app._quick_parameter_changed)

    row = _row(panel)
    traditional_only.append(row)
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

    line_row = _row(panel)
    traditional_only.append(line_row)
    _button(line_row, "OCR画线设置...", open_ocr_line_settings)
    illustrated_row = _row(panel)
    ttk.Label(
        illustrated_row,
        text="图解 OCR：多语言集合、有效区域及归组参数请在【一、版面参数 / PROFILE】设置。"
             "图解页只使用本地 OCR，不发送 Lens。",
        wraplength=280, justify="left",
    ).pack(fill="x")
    from ..illustrated_profile import effective_page_kind
    def refresh():
        illustrated_row.pack_forget()
        for row in traditional_only:
            row.pack_forget()
        if effective_page_kind(app.settings, getattr(app, "current_page", None)) == "illustrated":
            illustrated_row.pack(fill="x", pady=(3, 4))
        else:
            for row in traditional_only:
                row.pack(fill="x", pady=2)
    panel.refresh_from_settings = refresh  # type: ignore[attr-defined]
    refresh()
    return panel

ACTION_GROUPS = (
    (("普通画线", "run_normal_draw_action"),
     ("仅OCR", "ocr_ordinary_lines_text_selected_scope")),
    (("融合画线+OCR", "run_combined_draw_action"),),
    (("OCR画线（默认）", "run_ocr_draw_action"),),
    None,
    (("清除画线", "clear_entries"), ("清除文本", "clear_text")),
    (("精修画线", "refine_lines_selected_scope"),
     ("标记线差异页", "bookmark_modified_line_pages")),
    (("精修Y·固定半栏距", "refine_y_fixed_half_gutter"),),
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
    (("插图关联", "associate_illustrations"),),
    None,
    (("识别'REF'", "recognize_ref_boxes"), ("编辑'REF'", "toggle_ref_box_edit"),
     ("OCR 'REF'", "ocr_ref_boxes")),
    None,
    (("压缩OCR缓存", "cleanup_paddleocr_temp_selected_scope"),),
)


def build_drawing_menu(app: Any, parent: tk.Misc) -> ttk.Frame:
    panel = _panel(parent)
    ordinary = ttk.Frame(panel)
    illustrated = ttk.Frame(panel)
    from ..illustrated_profile import effective_page_kind
    from .illustrated_dictionary_window import open_illustrated_dictionary_editor
    for group in ACTION_GROUPS:
        if group is None:
            _separator(ordinary)
            continue
        row = _row(ordinary)
        for caption, method in group:
            command = ((lambda: bookmark_modified_line_pages(app))
                       if method == "bookmark_modified_line_pages" else
                       (lambda: app.refine_lines_selected_scope(fixed_half_gutter=True))
                       if method == "refine_y_fixed_half_gutter" else getattr(app, method))
            button = _button(row, caption, command)
            if caption == "精修Y·固定半栏距":
                app._attach_tooltip(
                    button, "先临时填白插图，再按本栏固定宽度及左右半栏间距校验Y；"
                            "不会调用逐页版式识别，也不会跨入邻栏。缺已有PPP时遵守原严格校验。",
                )
            if caption == "精修画线":
                app._attach_tooltip(
                    button,
                    "请先去设置中心的精修Y调整参数。此操作仅移动已有横线，"
                    "不会重新识别词头；若词条关联简体副本则拒绝危险位移。",
                )
            if caption == "插图关联":
                app._attach_tooltip(button, "画线/插图校对后再进行本操作！")
            if caption == "编辑插图":
                app.polygon_draw_button = button
                if app.polygon_draw_var.get():
                    button.configure(text="结束编辑插图", style="PC.EditActive.TButton")
            if caption == "编辑'REF'":
                app._ref_box_edit_button = button
                if app.ref_box_controller.editing:
                    button.configure(text="结束编辑'REF'", style="PC.EditActive.TButton")
    from .ocr_detection_inspector import show_ocr_decision_inspector
    _button(_row(ordinary), "OCR／融合画线决策可视化（只读）", lambda: show_ocr_decision_inspector(app))
    row = _row(ordinary)
    _check(row, "辅助线模式", app.auxiliary_mode_var, app.toggle_auxiliary_mode)
    _button(row, "撤销辅助线", app._auxiliary_controller.undo)

    # Spatial pages have their own operations and never invoke PDIC separator
    # drawing by accident. Traditional controls remain intact and reversible.
    row = _row(illustrated)
    _button(row, "选择 V", lambda: open_illustrated_dictionary_editor(app, action="select"))
    _button(row, "画框 B", lambda: open_illustrated_dictionary_editor(app, action="box"))
    row = _row(illustrated)
    _button(row, "显示/隐藏网格", lambda: open_illustrated_dictionary_editor(app, action="grid"))
    _button(row, "管理辅助线…", lambda: open_illustrated_dictionary_editor(app, action="guides"))
    row = _row(illustrated)
    _button(row, "对齐 / 分布…", lambda: open_illustrated_dictionary_editor(app, action="align"))
    _button(row, "组合 / 取消组合…", lambda: open_illustrated_dictionary_editor(app, action="align"))
    row = _row(illustrated)
    _button(row, "撤销", lambda: open_illustrated_dictionary_editor(app, action="undo"))
    _button(row, "重做", lambda: open_illustrated_dictionary_editor(app, action="redo"))
    _button(_row(illustrated), "主画布文字框编辑 / 校对",
            lambda: open_illustrated_dictionary_editor(app))
    _button(_row(illustrated), "全页 OCR 检测与文字组归并",
            lambda: open_illustrated_dictionary_editor(app, action="detect"))
    _button(_row(illustrated), "接受本页 OCR 候选",
            lambda: open_illustrated_dictionary_editor(app, action="accept"))
    _button(_row(illustrated), "图解词典多语言索引导出",
            lambda: open_illustrated_dictionary_editor(app, action="export"))
    ttk.Label(
        illustrated,
        text="图解模式在主界面图片上编辑；Shift 多选、标尺拖出辅助线。"
             "右键提供等距、等宽、锁定、拆分合并和更多对象操作。",
        wraplength=280, justify="left",
    ).pack(fill="x", pady=6)

    def refresh():
        illustrated.pack_forget()
        ordinary.pack_forget()
        if effective_page_kind(app.settings, getattr(app, "current_page", None)) == "illustrated":
            illustrated.pack(fill="x")
        else:
            ordinary.pack(fill="x")
    panel.refresh_from_settings = refresh  # type: ignore[attr-defined]
    refresh()
    return panel


# All seven workspace panels now have a purpose-built compact presentation.
# Keep the original app methods and progress-state widget references intact.
POSTPRODUCTION_ACTIONS = (
    (("画线行导出", "split_single_lines_selected_scope"),
     ("未画线行导出", "export_unlined_rows_selected_scope")),
    (("词条切图", "split_entries_selected_scope"),
     ("插图切图", "split_illustrations_selected_scope")),
    (("项目详情", "open_project_details"),
     ("导出PicDic索引", "export_picdic_index")),
    (("PicDic制作", "build_picdic"),
     ("导出训练标记包", "export_training_package")),
)

POSTPRODUCTION_HELP = {
    "画线行导出": "使用上方【切图宽度(%栏)】按校对单行裁切逻辑导出至 QT/PSW；不生成 .PSWords。启用【Layout前白化插图】时，导出 PNG 使用与【精修画线】相同的临时插图白化；复用模式缺少 PPP 时按原图导出，不改原图或 PPP。按页合并及并行数在【设置中心 → 切图】配置。",
    "未画线行导出": "按【切图宽度(%栏)】截取栏左候选行；勾选设置中心的【未画线行导出过滤 → 空白】后，只输出左侧连续白宽占比超过阈值（默认50%）的完整原框PNG（轻微孤立噪点视为空白，不修剪左白边，可按页合并）。启用【Layout前白化插图】时，行恢复、空白过滤与导出 PNG 均使用与【精修画线】一致的临时白化；复用模式缺少 PPP 时按原图导出，不改原图或 PPP。不生成清单文件。",
    "词条切图": "按照所选范围和【设置中心 → 切图】的参数导出完整词条 PNG。",
    "插图切图": "按所选范围导出 PPP 标注的独立插图 PNG。",
    "项目详情": "编辑词典名称、语言、正文页码范围等项目级元数据。",
    "导出PicDic索引": "从已保存的 PDIC 导出词条文字、X/Y 百分比和页码索引。",
    "PicDic制作": "从生成的切图创建 PicDic DSL 与图片包。",
    "导出训练标记包": "导出已确认的 PDIC、PPP、OCR 候选和坐标上下文。",
}


def build_postproduction_menu(app: Any, parent: tk.Misc) -> ttk.Frame:
    """New compact export menu with independent crop and display widths."""
    panel = _panel(parent)
    width_row = _row(panel)
    _label(width_row, "切图宽度(%)")
    width_entry = _entry(
        width_row, app.quick_vars["crop_width_percent"], 5, app._quick_parameter_changed,
    )
    app._attach_tooltip(
        width_entry,
        "按当前栏宽百分比控制画线/未画线单行切图；与向右比例%独立。",
    )
    app._crop_width_equivalence = CropWidthEquivalence(app)
    # The shared popup is 280px wide: keep the full label and editable value
    # immediately below the column field instead of clipping either input.
    page_width_row = _row(panel)
    _label(page_width_row, "相当于整页宽(%):")
    page_width_entry = _entry(
        page_width_row, app._crop_width_equivalence.page_percent_var, 7,
        app._crop_width_equivalence.commit_page,
    )
    app._attach_tooltip(
        page_width_entry,
        "对应当前页整图横向标尺的比例；按当前页第一栏的有效栏宽换算。"
        "修改两者任一项都会联动；多栏宽度不同、旋转或自动版面变化时仅作参考。",
    )
    for group in POSTPRODUCTION_ACTIONS:
        row = _row(panel)
        for caption, method in group:
            button = _button(row, caption, getattr(app, method))
            if caption == "画线行导出":
                app._pc_single_line_crop_button = button
            elif caption == "未画线行导出":
                app._pc_unlined_export_button = button
            app._attach_tooltip(button, POSTPRODUCTION_HELP[caption])
    return panel


__all__ = [
    "LAYOUT_ROWS", "ACTION_GROUPS",
    "build_preprocess_menu", "build_layout_menu",
    "build_ocr_menu", "build_drawing_menu", "build_postproduction_menu",
]
