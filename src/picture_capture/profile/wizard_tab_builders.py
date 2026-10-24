"""Canonical builders for the Profile Wizard body template and headword structure tabs.

The historical ProjectProfileWizard method names and callbacks remain unchanged.
All configurable globals are passed by the caller at call time.
"""
from __future__ import annotations


def build_template_tab(self, tab, *, deps) -> None:
    ttk = deps["ttk"]
    tk = deps["tk"]
    SEPARATOR_LABEL_TO_VALUE = deps["SEPARATOR_LABEL_TO_VALUE"]
    HEADER_LABEL_TO_VALUE = deps["HEADER_LABEL_TO_VALUE"]
    FOOTER_LABEL_TO_VALUE = deps["FOOTER_LABEL_TO_VALUE"]
    SIDE_LABEL_TO_VALUE = deps["SIDE_LABEL_TO_VALUE"]
    tab.columnconfigure(0, weight=1)
    ttk.Label(
        tab, text="② 正文在哪里？",
        font=("TkDefaultFont", 12, "bold"),
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(
        tab,
        text="左侧定义正文与排除区域；右侧始终用一张真实代表页即时预览。A/B 表示相邻扫描页。",
        foreground="#666666", wraplength=self._wizard_left_width,
    ).grid(row=1, column=0, sticky="w", pady=(2, 8))

    body = ttk.LabelFrame(tab, text="正文与分栏", padding=9)
    body.grid(row=2, column=0, sticky="ew")
    body.columnconfigure(1, weight=1)
    ttk.Label(body, text="正文栏数：").grid(row=0, column=0, sticky="e", pady=5)
    self.columns_spin = tk.Spinbox(
        body, from_=1, to=8, width=5, textvariable=self.columns_var,
    )
    self.columns_spin.grid(row=0, column=1, sticky="w", pady=5)
    ttk.Label(
        body,
        text="代表页会自动分析并建议栏数；确认后作为本项目的稳定栏数使用。",
        foreground="#666666", wraplength=self._wizard_left_width,
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 5))
    ttk.Label(body, text="中央分隔线：").grid(row=2, column=0, sticky="e", pady=5)
    ttk.Combobox(
        body, textvariable=self.separator_var, state="readonly", width=18,
        values=tuple(SEPARATOR_LABEL_TO_VALUE.keys()),
    ).grid(row=2, column=1, sticky="w", pady=5)

    self.analysis_suggestion_var = tk.StringVar(
        value="进入本步骤时会分析当前代表页，也可随时重新分析。"
    )
    ttk.Label(
        body, textvariable=self.analysis_suggestion_var,
        wraplength=self._wizard_left_width,
    ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 4))
    analysis_buttons = ttk.Frame(body)
    analysis_buttons.grid(row=4, column=0, columnspan=2, sticky="w")
    self.analyze_button = ttk.Button(
        analysis_buttons, text="重新分析代表页",
        command=self.analyze_representative_pages,
    )
    self.analyze_button.pack(side="left")
    self.apply_analysis_button = ttk.Button(
        analysis_buttons, text="应用建议",
        command=self.apply_analysis_suggestion, state="disabled",
    )
    self.apply_analysis_button.pack(side="left", padx=(6, 0))

    column_adjust = ttk.LabelFrame(body, text="栏左线微调", padding=(8, 6))
    column_adjust.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    column_adjust.columnconfigure(0, weight=1)
    ttk.Label(
        column_adjust,
        text="点击右侧预览中的栏左线选择；选中线显示为橙色。每次移动约 0.1% 单栏宽。",
        foreground="#666666", wraplength=self._wizard_left_width,
    ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 5))
    ttk.Label(
        column_adjust, textvariable=self.column_adjust_status_var,
    ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 5))
    ttk.Button(
        column_adjust, text="← 左移 0.1%",
        command=lambda: self._shift_selected_column(-1),
    ).grid(row=2, column=0, sticky="w")
    ttk.Button(
        column_adjust, text="右移 0.1% →",
        command=lambda: self._shift_selected_column(1),
    ).grid(row=2, column=1, sticky="w", padx=(6, 0))
    ttk.Button(
        column_adjust, text="重置当前", command=self._reset_selected_column,
    ).grid(row=2, column=2, sticky="w", padx=(12, 0))
    ttk.Button(
        column_adjust, text="重置全部", command=self._reset_all_column_offsets,
    ).grid(row=2, column=3, sticky="w", padx=(6, 0))
    self._refresh_column_adjust_status()

    edges = ttk.LabelFrame(
        tab, text="页眉 / 页尾 / 页边", padding=9,
    )
    edges.grid(row=3, column=0, sticky="ew", pady=(10, 0))
    edges.columnconfigure(1, weight=1)
    self._mode_row(
        edges, 0, "页眉：", self.header_mode_var,
        tuple(HEADER_LABEL_TO_VALUE.keys()),
    )
    ttk.Label(
        edges, text="排除高度%",
    ).grid(row=1, column=0, sticky="e")
    self.header_percent_spin = tk.Spinbox(
        edges, from_=0, to=35, increment=0.5, width=6,
        textvariable=self.header_percent_var,
    )
    self.header_percent_spin.grid(row=1, column=1, sticky="w")
    self._mode_row(
        edges, 2, "页尾：", self.footer_mode_var,
        tuple(FOOTER_LABEL_TO_VALUE.keys()),
    )
    ttk.Label(
        edges, text="排除高度%",
    ).grid(row=3, column=0, sticky="e")
    self.footer_percent_spin = tk.Spinbox(
        edges, from_=0, to=35, increment=0.5, width=6,
        textvariable=self.footer_percent_var,
    )
    self.footer_percent_spin.grid(row=3, column=1, sticky="w")
    ttk.Label(
        edges, text="页边内容：",
    ).grid(row=4, column=0, sticky="e", pady=5)
    ttk.Combobox(
        edges, textvariable=self.side_mode_var, state="readonly", width=22,
        values=tuple(SIDE_LABEL_TO_VALUE.keys()),
    ).grid(row=4, column=1, sticky="w", pady=5)

    ttk.Label(
        edges, text="固定页边宽度%",
    ).grid(row=5, column=0, sticky="e")
    self.side_percent_spin = tk.Spinbox(
        edges, from_=0, to=30, increment=0.5, width=6,
        textvariable=self.side_percent_var,
    )
    self.side_percent_spin.grid(row=5, column=1, sticky="w")

    ttk.Label(
        edges, text="A 页排除宽度%",
    ).grid(row=6, column=0, sticky="e", pady=(4, 0))
    self.side_percent_a_spin = tk.Spinbox(
        edges, from_=0, to=30, increment=0.5, width=6,
        textvariable=self.side_percent_a_var,
    )
    self.side_percent_a_spin.grid(row=6, column=1, sticky="w", pady=(4, 0))
    ttk.Label(
        edges, text="B 页排除宽度%",
    ).grid(row=7, column=0, sticky="e", pady=(4, 0))
    self.side_percent_b_spin = tk.Spinbox(
        edges, from_=0, to=30, increment=0.5, width=6,
        textvariable=self.side_percent_b_var,
    )
    self.side_percent_b_spin.grid(row=7, column=1, sticky="w", pady=(4, 0))

    ttk.Label(
        edges, text="A/B 起始页：",
    ).grid(row=8, column=0, sticky="e", pady=(10, 4))
    self.first_variant_combo = ttk.Combobox(
        edges, textvariable=self.first_variant_var,
        state="readonly", width=8, values=("A", "B"),
    )
    self.first_variant_combo.grid(row=8, column=1, sticky="w", pady=(10, 4))
    ttk.Label(
        edges,
        text=(
            "选“外侧/内侧交替”时，A 与 B 的页边宽度分别控制，"
            "不要求两边比例一致；第一张扫描若属于 B 页，可在这里整体翻转。"
        ),
        foreground="#666666",
        wraplength=self._wizard_left_width,
    ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(8, 0))

    for variable in (
        self.header_mode_var, self.footer_mode_var, self.side_mode_var,
    ):
        variable.trace_add(
            "write", lambda *_args: self.after_idle(self._refresh_template_controls)
        )
    self._refresh_template_controls()




def build_headword_tab(self, tab, *, deps) -> None:
    ttk = deps["ttk"]
    tk = deps["tk"]
    VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE = deps["VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE"]
    VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE = deps["VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE"]
    tab.columnconfigure(1, weight=1)
    ttk.Label(tab, text="③ 什么才算一个新词条？", font=("TkDefaultFont", 12, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w"
    )
    ttk.Label(
        tab,
        text="词头结构只控制词头识别，不再偷偷改变横/竖排、分栏或 OCR 语言。",
        foreground="#666666",
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))

    ttk.Label(tab, text="词头结构：").grid(row=2, column=0, sticky="e", padx=(0, 8))
    self.headword_combo = ttk.Combobox(
        tab, textvariable=self.headword_profile_var, state="readonly", width=48,
        values=tuple(label for label, _key in self.profile_choices),
    )
    self.headword_combo.grid(row=2, column=1, sticky="ew")
    self.headword_combo.bind("<<ComboboxSelected>>", lambda _e: self._headword_changed())

    ttk.Label(tab, text="自定义结构名称：").grid(row=3, column=0, sticky="e", padx=(0, 8), pady=7)
    self.custom_name_entry = ttk.Entry(tab, textvariable=self.custom_name_var)
    self.custom_name_entry.grid(row=3, column=1, sticky="ew", pady=7)
    self.custom_name_var.trace_add("write", lambda *_args: self.after_idle(self._custom_name_changed))

    self.headword_description_var = tk.StringVar(value="")
    ttk.Label(
        tab, textvariable=self.headword_description_var,
        wraplength=self._wizard_content_width, justify="left",
    ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 4))

    structures = ttk.LabelFrame(
        tab, text="完整词头结构（词头前 + 词头本体 + 词头后）", padding=10,
    )
    structures.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    structures.columnconfigure(0, weight=1)
    self.headword_structure_frame = structures
    ttk.Label(
        structures,
        text="词头前 / 词头本体：",
        font=("TkDefaultFont", 10, "bold"),
    ).grid(row=0, column=0, sticky="w", pady=(0, 4))
    for row, (label, variable) in enumerate((
        ("普通左缘短词可以作为词头", self.ordinary_left_edge_var),
        ("【括号词】可以作为词头", self.cjk_allow_bracketed_var),
        ("大字单字可以作为词头", self.cjk_allow_single_var),
        ("固定符号开头（○ / ● / ◆ …；不包括【括号】）可以作为词头", self.marker_prefix_var),
        ("编号开头（1. / 2. / …）可以作为词头", self.numbered_prefix_var),
    )):
        ttk.Checkbutton(
            structures, text=label, variable=variable,
            command=self._headword_structure_changed,
        ).grid(row=row + 1, column=0, sticky="w", pady=2)
    ttk.Checkbutton(
        structures,
        text="按 OCR 语言排除不兼容的词头首字符（推荐）",
        variable=self.headword_script_guard_var,
        command=self._headword_structure_changed,
    ).grid(row=6, column=0, sticky="w", pady=(5, 2))
    ttk.Label(
        structures,
        text="例如英语/意大利语等会排除汉字、假名、韩文开头；日语允许汉字/假名，中文允许汉字。",
        foreground="#666666", wraplength=self._wizard_content_width,
    ).grid(row=7, column=0, sticky="w", pady=(0, 4))
    ttk.Label(
        structures,
        text="这里决定“谁有资格成为候选”。取消某一项后，该结构不会再靠后续阈值被误救回来。",
        foreground="#666666", wraplength=self._wizard_content_width,
    ).grid(row=8, column=0, sticky="w", pady=(6, 0))
    self.headword_structure_summary_var = tk.StringVar(value="")
    ttk.Label(
        structures, textvariable=self.headword_structure_summary_var,
        foreground="#555555", wraplength=self._wizard_content_width,
    ).grid(row=9, column=0, sticky="w", pady=(4, 0))

    self.tail_structure_frame = ttk.LabelFrame(
        structures, text="词头后结构（哪些内容可以作为新词条证据）", padding=8,
    )
    self.tail_structure_frame.grid(row=10, column=0, sticky="ew", pady=(8, 0))
    self.tail_structure_frame.columnconfigure(0, weight=1)
    for tail_row, (label, variable) in enumerate((
        ("词性 POS（s.m. / v.tr. / agg. / adj. …）", self.tail_allow_pos_var),
        ("词形 / 屈折变化（复数、阴阳性、变位提示等）", self.tail_allow_inflection_var),
        ("变体 / 性数变化（如 , da / , ria 等紧随词头的变体）", self.tail_allow_variant_var),
        ("发音 / 音标（[...] 或 /.../）可以作为结构证据", self.tail_allow_pronunciation_var),
        ("描述型结构（前缀、后缀、缩写、sigla/abbreviazione 等）", self.tail_allow_descriptor_var),
    )):
        ttk.Checkbutton(
            self.tail_structure_frame,
            text=label,
            variable=variable,
            command=self._headword_structure_changed,
        ).grid(row=tail_row, column=0, sticky="w", pady=2)
    ttk.Separator(
        self.tail_structure_frame, orient="horizontal",
    ).grid(row=5, column=0, sticky="ew", pady=6)
    ttk.Checkbutton(
        self.tail_structure_frame,
        text="普通左缘词至少需要命中一种上面勾选的词后结构",
        variable=self.tail_require_selected_var,
        command=self._headword_structure_changed,
    ).grid(row=6, column=0, sticky="w", pady=2)
    ttk.Checkbutton(
        self.tail_structure_frame,
        text="词后结构 OCR 失败时，允许“严格左缘 + 粗体”视觉补救",
        variable=self.tail_allow_visual_rescue_var,
        command=self._headword_structure_changed,
    ).grid(row=7, column=0, sticky="w", pady=2)
    ttk.Label(
        self.tail_structure_frame,
        text="视觉补救使用下方可见的【栏左缘容差】【粗体倍率】【候选强度】；不再另设隐藏的粗体/行高门槛。",
        foreground="#666666", wraplength=self._wizard_content_width,
    ).grid(row=8, column=0, sticky="w", pady=(2, 2))
    ttk.Label(
        self.tail_structure_frame,
        text="固定符号、编号等已勾选的强前缀仍可独立作为边界证据；此处主要控制普通左缘词的词后证据。",
        foreground="#666666", wraplength=self._wizard_content_width,
    ).grid(row=9, column=0, sticky="w", pady=(5, 2))
    ttk.Label(
        self.tail_structure_frame,
        textvariable=self.tail_structure_summary_var,
        foreground="#555555", wraplength=self._wizard_content_width,
    ).grid(row=10, column=0, sticky="w", pady=(3, 0))

    self.symbol_inventory_frame = ttk.LabelFrame(
        structures, text="本词典固定词头符号集", padding=8,
    )
    self.symbol_inventory_frame.grid(row=11, column=0, sticky="ew", pady=(8, 0))
    # Keep the user-editable symbol fields visibly wide. Long help text must
    # wrap below them instead of consuming the grid width and collapsing Entry.
    self.symbol_inventory_frame.columnconfigure(1, weight=1, minsize=180)
    self.symbol_inventory_frame.columnconfigure(2, weight=0)
    symbol_hint_wrap = max(220, self._wizard_content_width - 140)
    symbol_full_wrap = max(280, self._wizard_content_width - 40)

    ttk.Checkbutton(
        self.symbol_inventory_frame,
        text="启用独立入口标记符号集（○ / ● / ◆ …）",
        variable=self.symbol_inventory_enabled_var,
        command=self._headword_structure_changed,
    ).grid(row=0, column=0, columnspan=3, sticky="w", pady=2)

    ttk.Label(
        self.symbol_inventory_frame, text="独立入口标记：",
    ).grid(row=1, column=0, sticky="e", padx=(0, 6), pady=3)
    ttk.Entry(
        self.symbol_inventory_frame,
        textvariable=self.entry_marker_symbols_var,
        width=24,
    ).grid(row=1, column=1, columnspan=2, sticky="ew", pady=3)
    ttk.Label(
        self.symbol_inventory_frame,
        text="仅指 ○●◆ 等独立前缀；【不要填这里】。可连续输入，也可用空格/逗号分隔。",
        foreground="#666666",
        wraplength=symbol_hint_wrap,
        justify="left",
    ).grid(row=2, column=1, columnspan=2, sticky="w", pady=(0, 5))

    ttk.Label(
        self.symbol_inventory_frame, text="括号词头起始：",
    ).grid(row=3, column=0, sticky="e", padx=(0, 6), pady=3)
    ttk.Entry(
        self.symbol_inventory_frame,
        textvariable=self.bracket_open_symbols_var,
        width=24,
    ).grid(row=3, column=1, columnspan=2, sticky="ew", pady=3)
    ttk.Label(
        self.symbol_inventory_frame,
        text="默认【；括号内文字才是词头。该栏由“【括号词】”结构独立控制，不受上方独立入口标记开关影响；若词典使用〔［「等，再按实际版式添加。",
        foreground="#666666",
        wraplength=symbol_hint_wrap,
        justify="left",
    ).grid(row=4, column=1, columnspan=2, sticky="w", pady=(0, 5))

    ttk.Checkbutton(
        self.symbol_inventory_frame,
        text="OCR 漏掉/错认符号时允许视觉形状补救",
        variable=self.symbol_visual_rescue_var,
        command=self._headword_structure_changed,
    ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(2, 0))
    ttk.Label(
        self.symbol_inventory_frame,
        text="默认关闭；只有确认 OCR 经常漏掉括号/入口符号时再开启。括号仍按 bracket_open 角色处理，不会变成独立入口标记。",
        foreground="#666666",
        wraplength=symbol_full_wrap,
        justify="left",
    ).grid(row=6, column=0, columnspan=3, sticky="w", padx=(22, 0), pady=(0, 4))

    ttk.Checkbutton(
        self.symbol_inventory_frame,
        text="使用同栏 marker lane 过滤正文中的相似符号",
        variable=self.symbol_lane_required_var,
        command=self._headword_structure_changed,
    ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(2, 0))
    ttk.Label(
        self.symbol_inventory_frame,
        text="开启后，只接受落在本栏稳定标记带附近的视觉符号，可减少正文里相似圆点、方块或括号造成的误检。",
        foreground="#666666",
        wraplength=symbol_full_wrap,
        justify="left",
    ).grid(row=8, column=0, columnspan=3, sticky="w", padx=(22, 0), pady=(0, 4))

    ttk.Label(
        self.symbol_inventory_frame, text="lane 容差：",
    ).grid(row=9, column=0, sticky="e", padx=(0, 6), pady=3)
    tk.Spinbox(
        self.symbol_inventory_frame,
        from_=20, to=120, increment=5, width=7,
        textvariable=self.symbol_lane_tolerance_var,
    ).grid(row=9, column=1, sticky="w", pady=3)
    ttk.Label(
        self.symbol_inventory_frame,
        text="% 行高（越小越严格；默认 50%）",
        foreground="#666666",
        wraplength=symbol_hint_wrap,
        justify="left",
    ).grid(row=10, column=1, columnspan=2, sticky="w", pady=(0, 4))

    effective = ttk.Frame(self.symbol_inventory_frame)
    effective.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(4, 2))
    ttk.Label(
        effective,
        textvariable=self.effective_entry_markers_var,
        foreground="#555555",
        wraplength=symbol_full_wrap,
        justify="left",
    ).pack(anchor="w")
    ttk.Label(
        effective,
        textvariable=self.effective_bracket_markers_var,
        foreground="#555555",
        wraplength=symbol_full_wrap,
        justify="left",
    ).pack(anchor="w")

    visual_templates = ttk.LabelFrame(
        self.symbol_inventory_frame, text="本词典视觉标记样本", padding=7,
    )
    visual_templates.grid(
        row=12, column=0, columnspan=3, sticky="ew", pady=(8, 0)
    )
    visual_templates.columnconfigure(1, weight=1)

    ttk.Label(visual_templates, text="识别方式：").grid(
        row=0, column=0, sticky="e", padx=(0, 6), pady=3
    )
    ttk.Combobox(
        visual_templates,
        textvariable=self.symbol_template_mode_var,
        values=tuple(VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE),
        state="readonly",
        width=22,
    ).grid(row=0, column=1, sticky="w", pady=3)

    ttk.Label(visual_templates, text="样本组织：").grid(
        row=1, column=0, sticky="e", padx=(0, 6), pady=3
    )
    ttk.Combobox(
        visual_templates,
        textvariable=self.symbol_template_group_var,
        values=tuple(VISUAL_TEMPLATE_GROUP_LABEL_TO_VALUE),
        state="readonly",
        width=22,
    ).grid(row=1, column=1, sticky="w", pady=3)

    ttk.Label(visual_templates, text="最低匹配分数：").grid(
        row=2, column=0, sticky="e", padx=(0, 6), pady=3
    )
    tk.Spinbox(
        visual_templates,
        from_=0.35, to=0.95, increment=0.02, width=7,
        textvariable=self.symbol_template_threshold_var,
        format="%.2f",
    ).grid(row=2, column=1, sticky="w", pady=3)
    ttk.Label(
        visual_templates,
        text="默认 0.68；真实扫描差异较大时可适度降低",
        foreground="#666666",
        wraplength=symbol_hint_wrap,
        justify="left",
    ).grid(row=2, column=2, sticky="w", padx=(6, 0), pady=3)

    ttk.Checkbutton(
        visual_templates,
        text="在 OCR 诊断中记录模板匹配分数与样本来源",
        variable=self.symbol_template_debug_var,
        command=self._headword_specificity_changed,
    ).grid(row=3, column=0, columnspan=3, sticky="w", pady=2)

    ttk.Label(
        visual_templates,
        textvariable=self.visual_marker_sample_count_var,
        wraplength=symbol_full_wrap,
        justify="left",
    ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(5, 3))

    sample_buttons = ttk.Frame(visual_templates)
    sample_buttons.grid(row=5, column=0, columnspan=3, sticky="w")
    ttk.Button(
        sample_buttons,
        text="从页面采样…",
        command=self._capture_visual_marker_sample,
    ).pack(side="left")
    ttk.Button(
        sample_buttons,
        text="查看/删除样本",
        command=self._show_visual_marker_samples,
    ).pack(side="left", padx=(6, 0))
    ttk.Button(
        sample_buttons,
        text="清空样本",
        command=self._clear_visual_marker_samples,
    ).pack(side="left", padx=(6, 0))
    ttk.Label(
        visual_templates,
        text="直接框选真实印刷符号。采【时按“括号起始”保存，不会当成独立入口标记；每类建议采 2–5 个不同页面样本。",
        foreground="#666666",
        wraplength=symbol_full_wrap,
        justify="left",
    ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(5, 0))

    specificity = ttk.LabelFrame(
        tab, text="词头专属性（当前结构的视觉证据）", padding=10,
    )
    specificity.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(12, 0))
    specificity.columnconfigure(1, weight=1)
    self.headword_specificity_frame = specificity
    self.headword_specificity_hint_var = tk.StringVar(value="")
    ttk.Label(
        specificity, textvariable=self.headword_specificity_hint_var,
        foreground="#666666", wraplength=self._wizard_left_width,
    ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 7))

    ttk.Label(specificity, text="栏左缘容差：").grid(row=1, column=0, sticky="e", pady=3)
    tk.Spinbox(
        specificity, from_=0.0, to=100.0, increment=0.1, width=7,
        textvariable=self.headword_left_tolerance_var, format="%.2f",
    ).grid(row=1, column=1, sticky="w", pady=3)
    ttk.Label(
        specificity,
        text="% 单栏宽（允许词头起点偏离栏左边界的最大距离；越小越严格）",
        foreground="#666666",
    ).grid(row=1, column=2, sticky="w")

    ttk.Label(specificity, text="文字大小倍率 ≥").grid(row=2, column=0, sticky="e", pady=3)
    tk.Spinbox(
        specificity, from_=0.5, to=3.0, increment=0.02, width=7,
        textvariable=self.headword_height_ratio_var, format="%.2f",
    ).grid(row=2, column=1, sticky="w", pady=3)

    ttk.Label(specificity, text="粗体倍率 ≥").grid(row=3, column=0, sticky="e", pady=3)
    tk.Spinbox(
        specificity, from_=0.5, to=3.0, increment=0.02, width=7,
        textvariable=self.headword_boldness_ratio_var, format="%.2f",
    ).grid(row=3, column=1, sticky="w", pady=3)

    ttk.Label(specificity, text="候选强度 ≥").grid(row=4, column=0, sticky="e", pady=3)
    tk.Spinbox(
        specificity, from_=0.0, to=12.0, increment=0.25, width=7,
        textvariable=self.headword_min_score_var, format="%.2f",
    ).grid(row=4, column=1, sticky="w", pady=3)

    self.cjk_specificity_frame = ttk.LabelFrame(
        specificity, text="CJK 单字 / 括号词附加条件", padding=7,
    )
    self.cjk_specificity_frame.grid(
        row=5, column=0, columnspan=3, sticky="ew", pady=(8, 0)
    )
    for row, (label, variable) in enumerate((
        ("必须靠近栏左缘", self.cjk_require_left_edge_var),
        ("释义正文中也经常出现【括号词】", self.cjk_brackets_in_body_var),
        ("只有视觉明显突出时才把单字/括号词当词头", self.cjk_require_visual_var),
        ("分析大字右侧留白（仅辅助“大字单字”判断）", self.cjk_right_context_enabled_var),
    )):
        ttk.Checkbutton(
            self.cjk_specificity_frame, text=label, variable=variable,
            command=self._headword_specificity_changed,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=2)

    ttk.Label(
        self.cjk_specificity_frame, text="大字右侧检测宽度：",
    ).grid(row=4, column=0, sticky="e", pady=(3, 0))
    tk.Spinbox(
        self.cjk_specificity_frame, from_=30, to=200, increment=5, width=7,
        textvariable=self.cjk_right_context_width_var,
    ).grid(row=4, column=1, sticky="w", pady=(3, 0))
    ttk.Label(
        self.cjk_specificity_frame,
        text="% 大字高度（默认 80%；同时分析整体、下部留白和相对正文密度）",
        foreground="#666666",
    ).grid(row=4, column=2, sticky="w", pady=(3, 0))

    self.headword_tuning_status_var = tk.StringVar(value="")
    ttk.Label(
        specificity, textvariable=self.headword_tuning_status_var,
        foreground="#555555",
    ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))

    help_box = ttk.LabelFrame(tab, text="理解方式", padding=10)
    help_box.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(14, 0))
    help_box.columnconfigure(0, weight=1)
    self.headword_help_frame = help_box



def mode_row(
    parent, row: int, label: str, variable: tk.StringVar, values: tuple[str, ...],
    *, label_style: str | None = None, deps) -> None:
    ttk = deps["ttk"]
    kwargs = {"style": label_style} if label_style else {}
    ttk.Label(parent, text=label, **kwargs).grid(
        row=row, column=0, sticky="e", pady=5
    )
    ttk.Combobox(
        parent, textvariable=variable, state="readonly", width=22,
        values=values,
    ).grid(row=row, column=1, sticky="w", pady=5)
