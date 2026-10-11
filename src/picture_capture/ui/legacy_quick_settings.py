from __future__ import annotations

"""Classic comprehensive quick-settings builder retained as a dedicated UI module.

This extraction keeps widget order, persistence callback registrations, and the
method signature intact. The PictureCaptureApp class owns its public method
through normal class-body function import, without runtime monkey-patching.
"""

import tkinter as tk
from tkinter import ttk, font

from ..appearance import APPEARANCE_MODE_VALUES
from ..layout_percent_helpers import LAYOUT_PERCENT_AXES
from ..ocr_action_guard import LENS_MODE_LABELS, LENS_MODE_VALUES
from ..ui_compat import AUTO_FONT_FAMILY, normalize_content_font_setting
from ..layout_visualization_ui_v3 import add_layout_visualization_controls
from ..ocr_crop_preview_ui import add_ocr_crop_preview_control
from ..illustration_fill_opacity import add_quick_illustration_fill_opacity_control
from ..overlay_opacity import add_quick_opacity_control


def build_quick_settings(self, parent: ttk.Frame) -> None:
    self.quick_vars: dict[str, tk.Variable] = {}
    self.quick_pixel_vars: dict[str, tk.StringVar] = {}
    self._quick_geometry_edit_source: dict[str, str] = {}
    self.quick_bool_vars: dict[str, tk.BooleanVar] = {}
    self.quick_field_casts: dict[str, type] = {}
    self.quick_field_labels: dict[str, ttk.Label] = {}

    def add_field(
        panel: ttk.Frame, row: int, col: int, label: str, name: str, cast: type,
        width: int = 7,
    ) -> None:
        label_widget = ttk.Label(
            panel, text=label, style="PC.FieldLabel.TLabel"
        )
        label_widget.grid(
            row=row, column=col, sticky="e", padx=(0, 3), pady=1
        )
        self.quick_field_labels[name] = label_widget
        var = tk.StringVar(value=str(getattr(self.settings, name)))
        self.quick_vars[name] = var
        self.quick_field_casts[name] = cast
        if name in LAYOUT_PERCENT_AXES:
            value_frame = ttk.Frame(panel)
            value_frame.grid(
                row=row, column=col + 1, sticky="ew", padx=(0, 6), pady=1
            )
            ttk.Entry(
                value_frame,
                textvariable=var,
                width=max(5, width - 1),
                justify="left",
                style="PC.Compact.TEntry",
            ).pack(side="left")
            ttk.Label(value_frame, text="%").pack(side="left", padx=(2, 4))
            pixel_var = tk.StringVar(value=str(int(getattr(self.settings, name))))
            self.quick_pixel_vars[name] = pixel_var
            ttk.Spinbox(
                value_frame,
                from_=0,
                to=100000,
                increment=1,
                width=6,
                textvariable=pixel_var,
            ).pack(side="left")
            ttk.Label(value_frame, text="px").pack(side="left", padx=(2, 0))
        else:
            ttk.Entry(
                panel,
                textvariable=var,
                width=width,
                justify="left",
                style="PC.Compact.TEntry",
            ).grid(row=row, column=col + 1, sticky="ew", padx=(0, 6), pady=1)

    preprocess = self._section_frame(
        parent, "图片预处理(前置)", padding=5, section_key="preprocess"
    )
    self.preprocess_panel = preprocess
    preprocess.pack(fill="x")
    preprocess.columnconfigure(0, weight=1)

    preprocess_mode_row = ttk.Frame(preprocess)
    preprocess_mode_row.grid(row=0, column=0, sticky="ew")
    self.preprocess_mode_button = ttk.Button(
        preprocess_mode_row,
        text="进入预处理模式",
        command=self.toggle_preprocess_mode,
        style="PC.Compact.TButton",
    )
    self.preprocess_mode_button.pack(side="left", fill="x", expand=True)
    ttk.Checkbutton(
        preprocess_mode_row,
        text="自动纠偏",
        variable=self.preprocess_auto_deskew_var,
        command=self._preprocess_settings_changed,
    ).pack(side="left", padx=(6, 0))
    ttk.Label(preprocess_mode_row, text="安全边界：").pack(side="left", padx=(8, 2))
    safety_spin = ttk.Spinbox(
        preprocess_mode_row,
        from_=0, to=500, increment=5, width=6,
        textvariable=self.preprocess_safety_var,
    )
    safety_spin.pack(side="left")
    ttk.Label(preprocess_mode_row, text="px").pack(side="left", padx=(2, 0))
    safety_spin.bind("<Return>", self._preprocess_settings_changed)
    safety_spin.bind("<FocusOut>", self._preprocess_settings_changed)

    preprocess_geometry_row = ttk.Frame(preprocess)
    preprocess_geometry_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
    ttk.Label(preprocess_geometry_row, text="几何纠正：").pack(side="left")
    geometry_combo = ttk.Combobox(
        preprocess_geometry_row,
        textvariable=self.preprocess_geometry_var,
        values=(
            "自动几何（推荐）",
            "轻量：旋转+裁边",
            "自动透视",
            "UVDoc展平（Paddle高级）",
        ),
        state="readonly",
        width=22,
    )
    geometry_combo.pack(side="left", fill="x", expand=True)
    geometry_combo.bind("<<ComboboxSelected>>", self._preprocess_settings_changed)
    manual_corner_button = ttk.Button(
        preprocess_geometry_row,
        text="手动四角",
        command=self.edit_preprocess_corners,
        style="PC.Compact.TButton",
    )
    manual_corner_button.pack(side="left", padx=(6, 0))
    reset_corner_button = ttk.Button(
        preprocess_geometry_row,
        text="重置四角",
        command=self.reset_preprocess_corners,
        style="PC.Compact.TButton",
    )
    reset_corner_button.pack(side="left", padx=(4, 0))
    self._attach_tooltip(
        manual_corner_button,
        "在原始整页图上拖动左上、右上、右下、左下四个控制点；手动四角优先于自动透视，也可在 UVDoc 前先做人工透视校正。",
    )
    self._attach_tooltip(
        reset_corner_button,
        "删除当前页的手动四角覆盖，恢复自动几何纠正。",
    )

    preprocess_action_row = ttk.Frame(preprocess)
    preprocess_action_row.grid(row=2, column=0, sticky="ew", pady=(4, 0))
    for col in range(4):
        preprocess_action_row.columnconfigure(col, weight=1, uniform="preprocess-actions")
    for col, (text_value, command) in enumerate((
        ("分析所选范围", self.analyze_preprocess_selected),
        ("上一需检查", lambda: self.jump_preprocess_review(-1)),
        ("下一需检查", lambda: self.jump_preprocess_review(1)),
        ("诊断信息", self.show_preprocess_diagnostics),
    )):
        ttk.Button(
            preprocess_action_row, text=text_value, command=command,
            style="PC.Compact.TButton",
        ).grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 4, 0))

    preprocess_canvas_row = ttk.Frame(preprocess)
    preprocess_canvas_row.grid(row=3, column=0, sticky="ew", pady=(4, 0))
    ttk.Checkbutton(
        preprocess_canvas_row,
        text="统一最终页面",
        variable=self.preprocess_export_canvas_var,
        command=self._preprocess_export_settings_changed,
    ).pack(side="left")
    canvas_mode_combo = ttk.Combobox(
        preprocess_canvas_row,
        textvariable=self.preprocess_export_canvas_mode_var,
        values=("本批最大裁剪尺寸", "自定义尺寸"),
        state="readonly",
        width=15,
    )
    canvas_mode_combo.pack(side="left", padx=(6, 0))
    canvas_mode_combo.bind(
        "<<ComboboxSelected>>", self._preprocess_export_settings_changed
    )
    ttk.Label(preprocess_canvas_row, text="页面宽×高：").pack(side="left", padx=(8, 2))
    canvas_width_spin = ttk.Spinbox(
        preprocess_canvas_row,
        from_=0, to=100000, increment=10, width=7,
        textvariable=self.preprocess_export_canvas_width_var,
    )
    canvas_width_spin.pack(side="left")
    ttk.Label(preprocess_canvas_row, text="×").pack(side="left", padx=2)
    canvas_height_spin = ttk.Spinbox(
        preprocess_canvas_row,
        from_=0, to=100000, increment=10, width=7,
        textvariable=self.preprocess_export_canvas_height_var,
    )
    canvas_height_spin.pack(side="left")
    for widget in (canvas_width_spin, canvas_height_spin):
        widget.bind("<Return>", self._preprocess_export_settings_changed)
        widget.bind("<FocusOut>", self._preprocess_export_settings_changed)

    preprocess_margin_row = ttk.Frame(preprocess)
    preprocess_margin_row.grid(row=4, column=0, sticky="ew", pady=(4, 0))
    ttk.Label(preprocess_margin_row, text="页边空(px)：").pack(side="left")
    margin_widgets = []
    for label, variable in (
        ("上", self.preprocess_export_margin_top_var),
        ("左", self.preprocess_export_margin_left_var),
        ("下", self.preprocess_export_margin_bottom_var),
        ("右", self.preprocess_export_margin_right_var),
    ):
        ttk.Label(preprocess_margin_row, text=f"{label}：").pack(
            side="left", padx=(5, 1)
        )
        spin = ttk.Spinbox(
            preprocess_margin_row,
            from_=0, to=100000, increment=5, width=5,
            textvariable=variable,
        )
        spin.pack(side="left")
        margin_widgets.append(spin)
    for widget in margin_widgets:
        widget.bind("<Return>", self._preprocess_export_settings_changed)
        widget.bind("<FocusOut>", self._preprocess_export_settings_changed)

    preprocess_align_row = ttk.Frame(preprocess)
    preprocess_align_row.grid(row=5, column=0, sticky="ew", pady=(4, 0))
    ttk.Label(preprocess_align_row, text="内容框排版 X：").pack(side="left")
    align_x_combo = ttk.Combobox(
        preprocess_align_row,
        textvariable=self.preprocess_export_align_x_var,
        values=("左对齐", "居中", "右对齐"),
        state="readonly",
        width=8,
    )
    align_x_combo.pack(side="left")
    align_x_combo.bind(
        "<<ComboboxSelected>>", self._preprocess_export_settings_changed
    )
    ttk.Label(preprocess_align_row, text="Y：").pack(side="left", padx=(8, 2))
    align_y_combo = ttk.Combobox(
        preprocess_align_row,
        textvariable=self.preprocess_export_align_y_var,
        values=("顶端对齐", "居中", "底部对齐"),
        state="readonly",
        width=8,
    )
    align_y_combo.pack(side="left")
    align_y_combo.bind(
        "<<ComboboxSelected>>", self._preprocess_export_settings_changed
    )
    ttk.Label(
        preprocess_align_row,
        text="内容框在版心内排版；不足部分填白",
        style="PC.FieldLabel.TLabel",
    ).pack(side="left", padx=(10, 0))

    preprocess_export_row = ttk.Frame(preprocess)
    preprocess_export_row.grid(row=6, column=0, sticky="ew", pady=(4, 0))
    for col in range(3):
        preprocess_export_row.columnconfigure(
            col, weight=1, uniform="preprocess-export"
        )
    ttk.Button(
        preprocess_export_row, text="导出检查小图",
        command=self.export_preprocess_previews,
        style="PC.Compact.TButton",
    ).grid(row=0, column=0, sticky="ew")
    ttk.Button(
        preprocess_export_row, text="导出预处理图片",
        command=self.export_preprocess_images,
        style="PC.Compact.TButton",
    ).grid(row=0, column=1, sticky="ew", padx=(4, 0))
    promote_button = ttk.Button(
        preprocess_export_row, text="所选设为工作图片",
        command=self.promote_preprocessed_working_images,
        style="PC.Compact.TButton",
    )
    promote_button.grid(row=0, column=2, sticky="ew", padx=(4, 0))
    self._attach_tooltip(
        promote_button,
        "仅处理当前页面范围：所选页需已有 processed 导出。原扫描图"
        "逐批移动到 __before__，处理后图片以原文件名成为后续工作图片；"
        "未选页面保持不变，__before__ 中同名原图绝不覆盖。",
    )

    self._attach_tooltip(
        self.preprocess_mode_button,
        "进入后锁定画线/OCR/SECTION/后期制作，只保留预处理、翻页和缩放。原扫描图不会被覆盖。",
    )

    normal = self._section_frame(
        parent,
        "一、版面参数",
        padding=5,
        section_key="normal",
    )
    normal.pack(fill="x")
    add_field(normal, 0, 0, "正文栏数：", "columns", int)
    add_field(normal, 0, 2, "正文起始Y：", "start_y", float)
    add_field(normal, 0, 4, "首栏X：", "manual_x", float)
    add_field(normal, 1, 0, "单栏宽：", "column_width", float)
    add_field(normal, 1, 2, "栏间空：", "gutter", float)
    # Shared, live percent/pixel fields for the compact Layout panel.
    # Legacy widgets stay hidden but remain the canonical Tk state owners.
    for field_row, caption, name in (
        (3, "典型单行字高：", "character_height"),
        (4, "典型行间空白：", "row_padding"),
        (5, "正文缩进：", "body_indent"),
        (6, "微调判据：", "horizontal_tolerance"),
    ):
        add_field(normal, field_row, 0, caption, name, float)

    row = ttk.Frame(normal); row.grid(row=2, column=0, columnspan=8, sticky="ew", pady=(4, 0))
    detect_layout_button = ttk.Button(
        row, text="检测版面参数", command=self.detect_layout_current,
        style="PC.Compact.TButton",
    )
    detect_layout_button.pack(side="left", fill="x", expand=True)
    self._attach_tooltip(
        detect_layout_button,
        "若所选页面数量≥2，参数为稳健中位数",
    )
    consistency_button = ttk.Button(
        row, text="检测版面一致性", command=self.detect_layout_consistency_selected,
        style="PC.Compact.TButton",
    )
    consistency_button.pack(side="left", fill="x", expand=True, padx=(5, 0))
    self._attach_tooltip(
        consistency_button,
        "快速扫描所选至少 2 页的页眉边界和正文左缘，生成一致性报告；不修改版面参数。",
    )
    ordinary_settings_button = ttk.Button(
        row, text="普通画线设置…",
        command=lambda: self.open_settings(initial_tab="normal"),
        style="PC.Compact.TButton",
    )
    ordinary_settings_button.pack(side="left", fill="x", expand=True, padx=(5, 0))
    self._attach_tooltip(
        ordinary_settings_button,
        "打开普通画线的专属参数；融合模式会直接复用这些几何参数。",
    )
    for col in (1, 3, 5, 7): normal.columnconfigure(col, weight=1)

    aux = self._section_frame(parent, "二、显示设置", padding=5, section_key="aux")
    aux.pack(fill="x", pady=(4, 0))
    ruler_var = tk.BooleanVar(value=bool(self.settings.show_rulers))
    section_var = tk.BooleanVar(value=bool(self.settings.show_page_sections))
    guide_var = tk.BooleanVar(value=bool(self.settings.show_column_guides))
    marker_var = tk.BooleanVar(value=bool(self.settings.show_headword_markers))
    self.quick_bool_vars["show_rulers"] = ruler_var
    self.quick_bool_vars["show_page_sections"] = section_var
    self.quick_bool_vars["show_column_guides"] = guide_var
    self.quick_bool_vars["show_headword_markers"] = marker_var
    self.quick_color_buttons: dict[str, tk.Button] = {}
    self.quick_color_vars: dict[str, tk.StringVar] = {
        "ruler_color": tk.StringVar(value=self.settings.ruler_color),
        "page_section_color": tk.StringVar(value=self.settings.page_section_color),
        "guide_color": tk.StringVar(value=self.settings.guide_color),
        "headword_marker_color": tk.StringVar(value=self.settings.headword_marker_color),
        "illustration_outline_color": tk.StringVar(value=self.settings.illustration_outline_color),
        "illustration_fill_color": tk.StringVar(value=self.settings.illustration_fill_color),
        "illustration_label_border_color": tk.StringVar(value=self.settings.illustration_label_border_color),
        "illustration_label_fill_color": tk.StringVar(value=self.settings.illustration_label_fill_color),
        "main_entry_default_color": tk.StringVar(value=self.settings.main_entry_default_color),
    }

    def color_button(row: ttk.Frame, name: str) -> tk.Button:
        button = tk.Button(row, text="", width=2, padx=0, pady=0, bd=1, highlightthickness=0)
        button.configure(command=lambda n=name, b=button: self.choose_overlay_color(n, b))
        button.pack(side="left", padx=(2, 5), fill="y")
        self.quick_color_buttons[name] = button
        self._style_color_button(button, str(self.quick_color_vars[name].get()))
        color_tips = {
            "ruler_color": "选择标尺线和刻度数字颜色。",
            "page_section_color": "选择 SECTION 边界线颜色。",
            "guide_color": "选择栏左垂线颜色。",
            "headword_marker_color": "选择词头横线颜色。",
            "illustration_outline_color": "选择插图轮廓颜色。",
            "illustration_fill_color": "选择插图区域背景色。",
            "illustration_label_border_color": "选择插图标签外框颜色。",
            "illustration_label_fill_color": "选择插图标签背景色。",
            "main_entry_default_color": "选择主画布词条文本框默认背景色。",
        }
        self._attach_tooltip(button, color_tips.get(name, "点击选择颜色。"))
        return button

    section_row = ttk.Frame(aux); section_row.grid(row=0, column=0, columnspan=4, sticky="ew")
    ttk.Checkbutton(
        section_row, text="显示标尺", variable=ruler_var,
        command=lambda: self._apply_overlay_visibility_toggle("show_rulers", ruler_var),
    ).pack(side="left")
    color_button(section_row, "ruler_color")
    ttk.Checkbutton(
        section_row, text="显示Section", variable=section_var,
        command=lambda: self._apply_overlay_visibility_toggle("show_page_sections", section_var),
    ).pack(side="left", padx=(6, 0))
    color_button(section_row, "page_section_color")
    ttk.Label(section_row, text="粗细：").pack(side="left")
    section_width_var = tk.StringVar(value=str(self.settings.page_section_width))
    self.quick_vars["page_section_width"] = section_width_var
    self.quick_field_casts["page_section_width"] = int
    ttk.Entry(
        section_row, textvariable=section_width_var, width=4, justify="left"
    ).pack(side="left", padx=(2, 10))
    add_ocr_crop_preview_control(self, section_row)

    line_row = ttk.Frame(aux); line_row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(2, 0))
    ttk.Checkbutton(line_row, text="栏左垂线", variable=guide_var, command=self._quick_parameter_changed).pack(side="left")
    color_button(line_row, "guide_color")
    ttk.Label(line_row, text="宽度：").pack(side="left")
    guide_value = tk.StringVar(value=str(self.settings.guide_width)); self.quick_vars["guide_width"] = guide_value; self.quick_field_casts["guide_width"] = int
    ttk.Entry(
        line_row, textvariable=guide_value, width=5, justify="left"
    ).pack(side="left", padx=(2, 10))
    add_quick_opacity_control(self, line_row, name="guide_opacity")
    ttk.Checkbutton(line_row, text="插图形状：轮廓", variable=self.polygon_var, command=self.redraw).pack(side="left")
    color_button(line_row, "illustration_outline_color")
    ttk.Label(line_row, text="粗细").pack(side="left")
    outline_width_var = tk.StringVar(value=str(self.settings.illustration_outline_width)); self.quick_vars["illustration_outline_width"] = outline_width_var; self.quick_field_casts["illustration_outline_width"] = int
    ttk.Entry(
        line_row, textvariable=outline_width_var, width=4, justify="left"
    ).pack(side="left", padx=(2, 5))
    ttk.Label(line_row, text="背景").pack(side="left")
    color_button(line_row, "illustration_fill_color")
    add_quick_illustration_fill_opacity_control(self, line_row)

    marker_row = ttk.Frame(aux); marker_row.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(2, 0))
    ttk.Checkbutton(marker_row, text="词头横线", variable=marker_var, command=self._quick_parameter_changed).pack(side="left")
    color_button(marker_row, "headword_marker_color")
    ttk.Label(marker_row, text="高度：").pack(side="left")
    marker_value = tk.StringVar(value=str(self.settings.marker_height)); self.quick_vars["marker_height"] = marker_value; self.quick_field_casts["marker_height"] = int
    ttk.Entry(
        marker_row, textvariable=marker_value, width=5, justify="left"
    ).pack(side="left", padx=(2, 10))
    add_quick_opacity_control(self, marker_row, name="headword_marker_opacity")
    label_visible_var = tk.BooleanVar(value=bool(self.settings.show_illustration_labels))
    self.quick_bool_vars["show_illustration_labels"] = label_visible_var
    ttk.Checkbutton(marker_row, text="显示插图标签", variable=label_visible_var, command=lambda: self._apply_overlay_visibility_toggle("show_illustration_labels", label_visible_var)).pack(side="left")
    color_button(marker_row, "illustration_label_border_color")
    ttk.Label(marker_row, text="粗细").pack(side="left")
    label_width_var = tk.StringVar(value=str(self.settings.illustration_label_border_width)); self.quick_vars["illustration_label_border_width"] = label_width_var; self.quick_field_casts["illustration_label_border_width"] = int
    ttk.Entry(
        marker_row, textvariable=label_width_var, width=4, justify="left"
    ).pack(side="left", padx=(2, 5))
    ttk.Label(marker_row, text="背景").pack(side="left")
    color_button(marker_row, "illustration_label_fill_color")

    entry_row = ttk.Frame(aux); entry_row.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(2, 0))
    ttk.Label(entry_row, text="词条文本框：宽度(字符)").pack(side="left")
    for name, width in (("main_entry_width_chars", 5), ("main_entry_x_ratio", 5)):
        shown = getattr(self.settings, name) * 100 if name == "main_entry_x_ratio" else getattr(self.settings, name)
        var = tk.StringVar(value=str(round(shown) if name == "main_entry_x_ratio" else shown)); self.quick_vars[name] = var; self.quick_field_casts[name] = int  # Both width and displayed offset% are integers.
        if name == "main_entry_x_ratio": ttk.Label(entry_row, text="偏移%").pack(side="left", padx=(8, 2))
        ttk.Entry(
            entry_row, textvariable=var, width=width, justify="left"
        ).pack(side="left")
    follow_var = tk.BooleanVar(value=bool(self.settings.main_entry_follow_zoom)); self.quick_bool_vars["main_entry_follow_zoom"] = follow_var
    ttk.Checkbutton(entry_row, text="跟随缩放", variable=follow_var).pack(side="left", padx=(8, 0))
    ttk.Label(entry_row, text="默认").pack(side="left", padx=(8, 0))
    color_button(entry_row, "main_entry_default_color")

    font_row = ttk.Frame(aux); font_row.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(2, 0))
    ttk.Label(font_row, text="词条字体").pack(side="left")
    family_var = tk.StringVar(value=normalize_content_font_setting(self.settings.main_entry_font_family)); self.quick_vars["main_entry_font_family"] = family_var; self.quick_field_casts["main_entry_font_family"] = str
    content_font_values = (AUTO_FONT_FAMILY, *tuple(sorted(set(font.families()), key=str.casefold)))
    ttk.Combobox(font_row, textvariable=family_var, values=content_font_values, width=18).pack(side="left")
    ttk.Label(font_row, text="字号").pack(side="left", padx=(8, 2))
    size_var = tk.StringVar(value=str(self.settings.main_entry_font_size)); self.quick_vars["main_entry_font_size"] = size_var; self.quick_field_casts["main_entry_font_size"] = int
    ttk.Entry(
        font_row, textvariable=size_var, width=5, justify="left"
    ).pack(side="left")
    for label, name in (("粗体", "main_entry_font_bold"), ("斜体", "main_entry_font_italic")):
        var = tk.BooleanVar(value=bool(getattr(self.settings, name))); self.quick_bool_vars[name] = var
        ttk.Checkbutton(font_row, text=label, variable=var).pack(side="left", padx=(7, 0))

    label_font_row = ttk.Frame(aux); label_font_row.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(2, 0))
    ttk.Label(label_font_row, text="标签字体").pack(side="left")
    label_family_var = tk.StringVar(value=normalize_content_font_setting(self.settings.illustration_label_font_family)); self.quick_vars["illustration_label_font_family"] = label_family_var; self.quick_field_casts["illustration_label_font_family"] = str
    ttk.Combobox(label_font_row, textvariable=label_family_var, values=content_font_values, width=18).pack(side="left")
    ttk.Label(label_font_row, text="字号").pack(side="left", padx=(8, 2))
    label_size_var = tk.StringVar(value=str(self.settings.illustration_label_font_size)); self.quick_vars["illustration_label_font_size"] = label_size_var; self.quick_field_casts["illustration_label_font_size"] = int
    ttk.Entry(
        label_font_row, textvariable=label_size_var, width=5, justify="left"
    ).pack(side="left")
    for label, name in (("粗体", "illustration_label_font_bold"), ("斜体", "illustration_label_font_italic")):
        var = tk.BooleanVar(value=bool(getattr(self.settings, name))); self.quick_bool_vars[name] = var
        ttk.Checkbutton(label_font_row, text=label, variable=var).pack(side="left", padx=(7, 0))

    from ..crop_preview_display_settings import add_crop_preview_font_controls
    add_crop_preview_font_controls(self, aux, content_font_values, normalize_content_font_setting)

    ocr_display_row = ttk.Frame(aux); ocr_display_row.grid(row=6, column=0, columnspan=4, sticky="ew")
    for label, name in (("显示OCR内容选择", "review_main_show_ocr_choices"), ("显示OCR对比底色结果", "review_main_show_ocr_background")):
        var = tk.BooleanVar(value=bool(getattr(self.settings, name))); self.quick_bool_vars[name] = var
        ttk.Checkbutton(
            ocr_display_row, text=label, variable=var,
            command=lambda n=name, v=var: self._apply_overlay_visibility_toggle(n, v),
        ).pack(side="left", padx=(0, 8))

    candidate_var = tk.BooleanVar(value=bool(self.settings.paddle_show_candidate_checkboxes)); self.quick_bool_vars["paddle_show_candidate_checkboxes"] = candidate_var
    ttk.Checkbutton(
        ocr_display_row, text="显示单行候选框", variable=candidate_var,
        command=lambda: self._apply_overlay_visibility_toggle(
            "paddle_show_candidate_checkboxes", candidate_var,
        ),
    ).pack(side="left", padx=(0, 8))

    option_row = ttk.Frame(aux); option_row.grid(row=7, column=0, columnspan=4, sticky="ew")
    ttk.Checkbutton(
        option_row, text="隐藏线框(插图除外)", variable=self.hide_var,
        command=self._toggle_hide_overlays,
    ).pack(side="left")
    ttk.Label(option_row, text="显示模式：").pack(side="left", padx=(10, 2))
    display_mode_combo = ttk.Combobox(
        option_row,
        textvariable=self.display_mode_var,
        values=("原图+标注", "二值+标注", "仅原图", "仅二值", "切图预览"),
        state="readonly",
        width=10,
    )
    display_mode_combo.pack(side="left", padx=(0, 8))
    display_mode_combo.bind("<<ComboboxSelected>>", self._apply_display_mode)
    ttk.Label(option_row, text="颜色模式：").pack(side="left")
    appearance_combo = ttk.Combobox(
        option_row, textvariable=self.appearance_mode_var,
        values=tuple(APPEARANCE_MODE_VALUES), state="readonly", width=8,
    )
    appearance_combo.pack(side="left")
    appearance_combo.bind("<<ComboboxSelected>>", self._appearance_mode_selected)
    self._attach_tooltip(
        appearance_combo,
        "浅色=正常界面；深色=夜间界面；跟随系统=自动响应 Windows/macOS/Linux 的系统颜色模式。",
    )
    save_row = ttk.Frame(aux); save_row.grid(row=8, column=0, columnspan=4, sticky="ew")
    ttk.Checkbutton(save_row, text="自动保存", variable=self.autosave_var, command=self.toggle_autosave).pack(side="left")
    ttk.Label(save_row, text="间隔时间(秒)").pack(side="left", padx=(8, 2))
    interval_var = tk.StringVar(value=str(round(float(self.settings.batch_interval)))); self.quick_vars["batch_interval"] = interval_var; self.quick_field_casts["batch_interval"] = int
    ttk.Entry(
        save_row, textvariable=interval_var, width=6, justify="left"
    ).pack(side="left")
    ttk.Label(save_row, text="向右比例%").pack(side="left", padx=(10, 2))
    ratio_var = tk.StringVar(value=str(self.settings.right_ratio)); self.quick_vars["right_ratio"] = ratio_var; self.quick_field_casts["right_ratio"] = float
    ttk.Entry(
        save_row, textvariable=ratio_var, width=6, justify="left"
    ).pack(side="left")

    aux.columnconfigure(1, weight=1); aux.columnconfigure(3, weight=1)
    add_layout_visualization_controls(self, aux)

    ocr = self._section_frame(parent, "三、共享 OCR 通道 / OCR画线", padding=5, section_key="ocr")
    ocr.pack(fill="x", pady=(4, 0))
    self.ocr_refresh_var = tk.StringVar(value="reuse")
    ttk.Label(ocr, text="识别策略：").grid(row=0, column=0, sticky="w")
    ttk.Radiobutton(
        ocr, text="使用有效缓存（推荐）",
        variable=self.ocr_refresh_var, value="reuse",
    ).grid(row=0, column=1, columnspan=2, sticky="w")
    ttk.Radiobutton(
        ocr, text="重新OCR（模型/图像改变时）",
        variable=self.ocr_refresh_var, value="force",
    ).grid(row=0, column=3, columnspan=3, sticky="w")
    add_field(ocr, 1, 0, "OCR语言：", "ocr_language", str, 8)
    add_field(ocr, 1, 2, "识别带宽%：", "paddle_band_width_ratio", float, 7)
    add_field(ocr, 1, 4, "左缘容差：", "paddle_left_tolerance", int, 7)
    engine_row = ttk.Frame(ocr); engine_row.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(4, 1))
    ttk.Label(engine_row, text="OCR引擎：").pack(side="left")
    for text, name in (("PaddleOCR", "paddle_use_paddleocr"), ("Tesseract", "paddle_compare_tesseract"), ("Google Lens", "paddle_enable_lens")):
        var = tk.BooleanVar(value=bool(getattr(self.settings, name))); self.quick_bool_vars[name] = var
        ttk.Checkbutton(engine_row, text=text, variable=var).pack(side="left", padx=(0, 5))
    self.lens_mode_var = tk.StringVar(
        value=LENS_MODE_LABELS.get(self.settings.paddle_lens_mode, LENS_MODE_LABELS["off"])
    )
    lens_row = ttk.Frame(ocr); lens_row.grid(row=3, column=0, columnspan=6, sticky="ew")
    ttk.Label(lens_row, text="Lens模式：").pack(side="left")
    ttk.Combobox(
        lens_row, textvariable=self.lens_mode_var, values=tuple(LENS_MODE_VALUES),
        state="readonly", width=34,
    ).pack(side="left", fill="x", expand=True)
    ttk.Label(lens_row, text="  Y安全空间：").pack(side="left")
    safety_var = tk.StringVar(value=str(self.settings.paddle_separator_safety_px))
    self.quick_vars["paddle_separator_safety_px"] = safety_var
    self.quick_field_casts["paddle_separator_safety_px"] = int
    ttk.Entry(
        lens_row, textvariable=safety_var, width=4, justify="left"
    ).pack(side="left", padx=(2, 2))
    ttk.Label(lens_row, text="px").pack(side="left")
    ocr_tools = ttk.Frame(ocr)
    ocr_tools.grid(row=4, column=0, columnspan=6, sticky="ew", pady=(4, 0))
    environment_button = ttk.Button(
        ocr_tools, text="环境中心", command=self.check_ocr_engines,
        style="PC.Compact.TButton",
    )
    environment_button.pack(side="left", fill="x", expand=True)
    self._attach_tooltip(
        environment_button,
        "检查 PaddleOCR / PaddlePaddle、Tesseract、Lens、OpenCC 等运行环境。",
    )
    ocr_settings_button = ttk.Button(
        ocr_tools, text="OCR画线设置…",
        command=lambda: self.open_settings(initial_tab="ocr"),
        style="PC.Compact.TButton",
    )
    ocr_settings_button.pack(side="left", fill="x", expand=True, padx=(5, 0))
    self._attach_tooltip(
        ocr_settings_button,
        "打开 OCR画线参数和高级候选规则；建议先在代表页确认具体错误模式。",
    )
    for col in (1, 3, 5): ocr.columnconfigure(col, weight=1)

    actions = self._section_frame(
        parent, "四、画线 / OCR / 插图 / 校对",
        padding=5, section_key="actions",
    )
    actions.pack(fill="x", pady=(4, 0))
    action_tooltips = {
        "普通画线": "只运行高速左缘几何画线；适合正文缩进稳定的词典，不调用 OCR 来决定词条位置。",
        "仅OCR": "只对已有画线调用共享 OCR 通道做局部文字识别；普通行与大字行使用不同高度框，不新增、删除或移动画线，默认仅填空白词条。",
        "融合画线+OCR": "普通几何与 OCR 候选先融合、救漏和去重，再对仍为空白的普通救漏线自动做局部 OCR 补字。",
        "OCR画线(默认)": "默认画线方式：由 OCR / parser / 视觉候选链识别词头并确定画线，同时得到 OCR 文字。",
        "清除画线": "清除当前页全部词条画线；不会删除扫描图片。",
        "清除文本": "清空当前页画线中的词条文字，但保留画线位置。",
        "精修画线": "仅在所选范围微调已有画线的 Y 位置，不新增或删除词条。",
        "新旧比较": "比较所选范围当前 PDIC 与页码-词条文本，定位新增、缺失或顺序差异。",
        "词条校对": "打开连续校对窗口，结合扫描图、OCR候选、简体和参考词表逐条核对。",
        "选择词条文件": "选择带页码的既有词条 TXT，供后续【填充词条】重复使用。",
        "填充词条": "按当前页面范围，用已选页码词条文件填充对应 PDIC 词条文本。",
        "修复排序": "按栏号 → Y 修复所选范围 PDIC 记录顺序；不重新 OCR、不改变词条坐标配对。",
        "备份PDIC": "将项目现有 PDIC 汇总为时间戳备份，适合批量修改前留档。",
        "恢复PDIC": "从备份文本覆盖恢复主界面所选范围的 PDIC；执行前请确认页面范围。",
        "插图识别": "在所选页面范围自动识别插图并写入 PPP；人工多边形会保留。",
        "编辑插图": "进入/退出插图多边形编辑模式，可新增、移动顶点并修改标签。",
        "压缩OCR缓存": "压缩当前页面范围的 PaddleOCR 缓存并删除可再生诊断副本；保留可复用 OCR 原始记录和人工选择，不需要重新 OCR。",
        "保存当前页": "立即保存当前页的画线/词条或插图编辑结果。",
    }
    rows = [
        (
            ("普通画线", self.run_normal_draw_action),
            ("仅OCR", self.ocr_ordinary_lines_text_selected_scope),
            ("融合画线+OCR", self.run_combined_draw_action),
            ("OCR画线(默认)", self.run_ocr_draw_action),
        ),
        (("清除画线", self.clear_entries), ("清除文本", self.clear_text), ("精修画线", self.refine_lines_selected_scope), ("新旧比较", self.compare_old_new_selected_scope), ("词条校对", self.open_review)),
        (("选择词条文件", self.select_existing_headwords_file), ("填充词条", self.fill_existing_headwords), ("修复排序", self.repair_pdic_order_selected_scope), ("备份PDIC", self.backup_pdic), ("恢复PDIC", self.restore_from_pdic_backup)),
        (
            ("插图识别", self.detect_illustrations_selected_scope),
            ("编辑插图", self.toggle_polygon_drawing),
            ("压缩OCR缓存", self.cleanup_paddleocr_temp_selected_scope),
            ("保存当前页", self.save_current_page),
        ),
    ]
    for ri, specs in enumerate(rows):
        row = ttk.Frame(actions)
        row.grid(row=ri, column=0, sticky="ew", pady=(0 if ri == 0 else 3, 0))
        for bi in range(len(specs)):
            row.columnconfigure(bi, weight=1, uniform=f"actions-row-{ri}")
        for bi, (text, command) in enumerate(specs):
            role = (
                "primary" if text == "OCR画线(默认)"
                else "success" if text == "保存当前页"
                else "primary" if text == "词条校对"
                else "neutral"
            )
            button = self._sidebar_action_button(row, text, command, role=role)
            tooltip = action_tooltips.get(text)
            if tooltip:
                self._attach_tooltip(button, tooltip)
            if text == "编辑插图":
                self.polygon_draw_button = button
            button.grid(
                row=0, column=bi, sticky="ew",
                padx=(0 if bi == 0 else 4, 0),
            )
    actions.columnconfigure(0, weight=1)
    aux_row = ttk.Frame(actions)
    aux_row.grid(row=len(rows), column=0, sticky="w", pady=3)
    ttk.Checkbutton(aux_row, text="辅助线模式", variable=self.auxiliary_mode_var,
                    command=self.toggle_auxiliary_mode).pack(side="left")
    ttk.Button(aux_row, text="撤销辅助线",
               command=self._auxiliary_controller.undo).pack(side="left", padx=8)

    postproduction = self._section_frame(
        parent, "五、后期词典制作", padding=5, section_key="postproduction"
    )
    postproduction.pack(fill="x", pady=(4, 0))
    production_tooltips = {
        "画线行导出": (
            "将【选定范围】内各页按校对界面相同的单行裁切逻辑批量输出到 QT/PSW；"
            "可在【设置中心 → 切图】选择是否按页合并，并复用切图并行进程数。"
        ),
        "未画线行导出": (
            "将【选定范围】内 Layout 已恢复、但当前 PDIC 没有横线的文字行导出到 QT/PSW_UNLINED。"
            "可在【设置中心 → 切图】启用【未画线行导出过滤 → 空白】只检查近空白候选；"
            "不以 entry/body 角色决定是否导出，并复用按页合并和切图并行进程设置。"
        ),
        "词条切图": "按所选页面范围和【设置中心 → 切图】生成完整词条切图。",
        "插图切图": "按所选范围导出需要独立输出的 PPP 插图。",
        "项目详情": "编辑词典名称、语言、正文页码范围等项目级元数据。",
        "导出PicDic索引": "从项目已保存 PDIC 导出“词条 / X% / Y% / 页码”文本索引。",
        "PicDic制作": "使用已生成的词条切图制作 PicDic DSL 与图片包。",
        "导出训练标记包": "导出已人工确认的 PDIC/PPP、OCR候选和坐标上下文，供模型或规则验证。",
    }
    production_rows = [
        (("画线行导出", self.split_single_lines_selected_scope), ("未画线行导出", self.export_unlined_rows_selected_scope), ("词条切图", self.split_entries_selected_scope), ("插图切图", self.split_illustrations_selected_scope)),
        (("项目详情", self.open_project_details), ("导出PicDic索引", self.export_picdic_index), ("PicDic制作", self.build_picdic)),
        (("导出训练标记包", self.export_training_package),),
    ]
    for ri, specs in enumerate(production_rows):
        row = ttk.Frame(postproduction)
        row.grid(row=ri, column=0, sticky="ew", pady=(0 if ri == 0 else 3, 0))
        for bi in range(len(specs)):
            row.columnconfigure(bi, weight=1, uniform=f"postproduction-row-{ri}")
        for bi, (text, command) in enumerate(specs):
            button = self._sidebar_action_button(row, text, command)
            if text == "画线行导出":
                self._pc_single_line_crop_button = button
            elif text == "未画线行导出":
                self._pc_unlined_export_button = button
            tooltip = production_tooltips.get(text)
            if tooltip:
                self._attach_tooltip(button, tooltip)
            button.grid(
                row=0, column=bi, sticky="ew",
                padx=(0 if bi == 0 else 4, 0),
            )
    postproduction.columnconfigure(0, weight=1)

    # Main-panel parameters are live: after a short debounce, valid values
    # are applied and persisted without requiring a separate Apply step.
    for _name, _var in self.quick_vars.items():
        try:
            if _name in self.quick_pixel_vars:
                _var.trace_add(
                    "write",
                    lambda *_args, n=_name: self._quick_percent_parameter_changed(n),
                )
            else:
                _var.trace_add("write", lambda *_args: self._quick_parameter_changed())
        except Exception:
            pass
    for _name, _var in self.quick_pixel_vars.items():
        try:
            _var.trace_add(
                "write",
                lambda *_args, n=_name: self._quick_pixel_parameter_changed(n),
            )
        except Exception:
            pass
    for _var in self.quick_bool_vars.values():
        try:
            _var.trace_add("write", lambda *_args: self._quick_parameter_changed())
        except Exception:
            pass
    self.lens_mode_var.trace_add("write", lambda *_args: self._quick_parameter_changed())
    self._quick_trace_ready = True

