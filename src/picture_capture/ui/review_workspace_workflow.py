"""Canonical review-window layout, asynchronous crop preparation and row painting.

This leaf owns physical GUI implementation, while ReviewWindow in app.py
keeps its original Tk callback names, signatures and live patchpoints.
No imports from the heavyweight app module or native OCR engines.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..proofreading.simplified_review import source_word_conflicts

if TYPE_CHECKING:
    import tkinter as tk
    from PIL import Image


@dataclass(frozen=True)
class ReviewWorkspaceDeps:
    """Original app-level UI helpers captured afresh for each callback."""
    ttk: object
    tk: object
    Image: object
    font: object
    preferred_font_family: object
    AUTO_FONT_FAMILY: object
    _format_layout_percent: object
    _review_crop_context: object
    _review_line_box: object
    sync_review_entry_classification: object
    normalize_page_rgb: object
    review_auto_fit_zoom: object
    _entry_font_spec: object
    _review_editor_font_size: object
    resolve_content_font_family: object
    _focused_review_is_single_character: object
    simplified_entry_key: object
    replace: object
    appearance_palette: object


def _build(self, deps: ReviewWorkspaceDeps) -> None:
    ttk = deps.ttk
    tk = deps.tk
    Image = deps.Image
    font = deps.font
    preferred_font_family = deps.preferred_font_family
    AUTO_FONT_FAMILY = deps.AUTO_FONT_FAMILY
    panes = ttk.Panedwindow(self, orient="horizontal")
    panes.pack(fill="both", expand=True)
    self.review_panes = panes
    left = ttk.Frame(panes, style="PCR.Surface.TFrame")
    right = ttk.Frame(panes, padding=(8, 6), style="PCR.Surface.TFrame")
    panes.add(left, weight=0)
    panes.add(right, weight=1)

    # Left: high-frequency review actions first; low-frequency helpers stay folded.
    controls = ttk.Frame(left, padding=(7, 6, 7, 4), style="PCR.Toolbar.TFrame")
    controls.pack(fill="x")
    row1 = ttk.Frame(controls, style="PCR.Toolbar.TFrame")
    row1.pack(fill="x", pady=(0, 4))
    self.review_control_row = row1
    self._review_flat_button(row1, "保存", self.save, role="primary").pack(side="left")
    self._review_flat_button(row1, "撤销保存", self.undo_saved_review).pack(side="left", padx=(4, 0))
    self._review_flat_button(row1, "重做保存", self.redo_saved_review).pack(side="left", padx=(4, 0))
    # Add non-conflicting session-save shortcuts. Plain Ctrl+Z/Y remain
    # owned by the focused text editor / platform, never hijacked here.
    self.bind("<Control-Alt-z>", lambda _event: self.undo_saved_review())
    self.bind("<Control-Alt-y>", lambda _event: self.redo_saved_review())
    self._sync_autosave_label()
    ttk.Checkbutton(
        row1, textvariable=self.autosave_label_var, variable=self.parent.autosave_var,
        command=self._toggle_shared_autosave,
    ).pack(side="left", padx=(6, 0))
    ttk.Label(row1, text="校对模式：", style="PCR.Toolbar.TLabel").pack(side="left", padx=(8, 0))
    ttk.Radiobutton(
        row1, text="单页", variable=self.review_mode_var, value="single",
        command=self._change_review_mode,
    ).pack(side="left", padx=(2, 0))
    ttk.Radiobutton(
        row1, text="筛选", variable=self.review_mode_var, value="filter",
        command=self._change_review_mode,
    ).pack(side="left", padx=(2, 0))
    ttk.Button(
        row1, text="排序规则", command=self.open_sort_rules, style="PCR.Compact.TButton"
    ).pack(side="left", padx=(10, 0))
    ttk.Radiobutton(
        row1, text="当前页", variable=self.order_scope_var, value="current"
    ).pack(side="left", padx=(8, 0))
    ttk.Radiobutton(
        row1, text="所有页", variable=self.order_scope_var, value="all"
    ).pack(side="left", padx=(4, 0))
    ttk.Button(
        row1, text="排序检查", width=7, command=self.run_order_check,
        style="PCR.Compact.TButton",
    ).pack(side="left", padx=(5, 0))
    if getattr(self.parent.settings, "proofreading_event_capture", False):
        # Explicit, second-stage source-image review; never an autosave
        # action or implicit approval of a PDIC correction.
        ttk.Button(
            row1, text="核验记录", width=8,
            command=self._open_proofreading_visual_verification,
            style="PCR.Compact.TButton",
        ).pack(side="left", padx=(6, 0))
    ttk.Separator(controls, orient="horizontal").pack(fill="x", pady=(5, 0))

    focused = ttk.Frame(
        left, padding=(7, 3), style="PCR.Surface.TFrame"
    )
    focused.pack(fill="x", padx=(7, 7), pady=(0, 5))
    self.focused_panel_title = tk.StringVar(value="▸ 重点筛选校对")
    self.focused_panel_toggle = ttk.Label(
        focused, textvariable=self.focused_panel_title,
        style="PCR.Header.TLabel", cursor="hand2",
    )
    self.focused_panel_toggle.pack(fill="x")
    self.focused_panel_toggle.bind("<Button-1>", lambda _event: self._toggle_focused_panel())
    ttk.Separator(focused, orient="horizontal").pack(fill="x", pady=(3, 0))
    self.focused_panel_body = ttk.Frame(focused, style="PCR.Surface.TFrame")
    filter_row1 = ttk.Frame(self.focused_panel_body, style="PCR.Surface.TFrame")
    filter_row1.pack(fill="x")
    ttk.Button(
        filter_row1, text="筛选", command=self.run_focused_filter,
        style="PCR.Compact.TButton",
    ).pack(side="left")
    ttk.Label(filter_row1, text="页面范围").pack(side="left", padx=(7, 2))
    ttk.Entry(
        filter_row1, textvariable=self.focused_page_range_var, width=12,
        style="PCR.Compact.TEntry",
    ).pack(side="left")
    ttk.Checkbutton(
        filter_row1, text="OCR不匹配", variable=self.focused_include_mismatch_var,
    ).pack(side="left", padx=(8, 0))
    ttk.Checkbutton(
        filter_row1, text="含特定字符", variable=self.focused_include_characters_var,
    ).pack(side="left", padx=(7, 0))
    ttk.Checkbutton(
        filter_row1, text="排除单字符", variable=self.focused_exclude_single_var,
    ).pack(side="left", padx=(7, 0))
    ttk.Checkbutton(
        filter_row1, text="排除参考词表", variable=self.focused_exclude_reference_var,
    ).pack(side="left", padx=(7, 0))

    filter_row2 = ttk.Frame(self.focused_panel_body, style="PCR.Surface.TFrame")
    filter_row2.pack(fill="x", pady=(4, 0))
    ttk.Label(filter_row2, text="特定字符（用','分隔）：").pack(side="left")
    ttk.Entry(
        filter_row2, textvariable=self.focused_characters_var,
        style="PCR.Compact.TEntry",
    ).pack(side="left", fill="x", expand=True, padx=(3, 8))
    ttk.Label(filter_row2, text="单批显示数量：").pack(side="left")
    ttk.Spinbox(
        filter_row2, from_=1, to=500, increment=1, width=6,
        textvariable=self.focused_batch_size_var, style="PCR.Compact.TSpinbox",
    ).pack(side="left")
    filter_risk_row = ttk.Frame(self.focused_panel_body, style="PCR.Surface.TFrame")
    filter_risk_row.pack(fill="x", pady=(3, 0))
    ttk.Checkbutton(
        filter_risk_row,
        text="本次筛选：已核验来源的高风险优先（默认关闭）",
        variable=self.focused_risk_priority_var,
    ).pack(side="left")
    ttk.Checkbutton(
        filter_risk_row,
        text="下次 OCR 批量画线记录来源证明（需重新识别，默认关闭）",
        variable=self.focused_risk_capture_var,
    ).pack(side="left", padx=(9, 0))
    ttk.Label(
        filter_risk_row, text="勾选变化后请点击「筛选」生效。"
    ).pack(side="left", padx=(7, 0))
    # Main review strip: vertical previous/next buttons flank the scrollable rows.
    strip = ttk.Frame(left, style="PCR.Surface.TFrame")
    strip.pack(fill="both", expand=True, padx=(4, 4), pady=(0, 4))
    # Page navigation is intentionally a little darker than ordinary
    # controls so it remains easy to find while proofreading without
    # competing visually with the crop/text rows.
    review_nav_bg = "#d7d7d7"
    review_nav_active_bg = "#c8c8c8"
    self.prev_page_button = tk.Button(
        strip, text="上\n一\n页", width=3, command=lambda: self.change_page(-1),
        bg=review_nav_bg, activebackground=review_nav_active_bg,
        relief="flat", bd=0, highlightthickness=0, cursor="hand2",
    )
    self.prev_page_button.pack(side="left", fill="y", padx=(0, 4))
    # Reserve both navigation controls before the expanding editor pane;
    # otherwise pack can squeeze the right-hand button out of narrow windows.
    self.next_page_button = tk.Button(
        strip, text="下\n一\n页", width=3, command=lambda: self.change_page(1),
        bg=review_nav_bg, activebackground=review_nav_active_bg,
        relief="flat", bd=0, highlightthickness=0, cursor="hand2",
    )
    self.next_page_button.pack(side="right", fill="y", padx=(4, 0))
    editor_area = ttk.Frame(strip, style="PCR.Surface.TFrame")
    editor_area.pack(side="left", fill="both", expand=True)
    self.review_editor_area = editor_area

    # Fixed current-word preview: independent of window resizing.
    self.active_crop_host = ttk.Frame(editor_area, style="PCR.Surface.TFrame")
    self.active_crop_host.pack(side="top", fill="x")
    self.active_crop_host.pack_propagate(False)
    self.active_crop_host.configure(height=1)
    self.active_crop_frame = tk.Frame(self.active_crop_host, bd=2, relief="solid",
                                      highlightthickness=1, highlightbackground="#4F7CAC")
    # Absolute coordinates inside a fixed-height slot, never pack-centered
    # or stretched by horizontal window resize.
    self.active_crop_frame.place(x=6, y=4, anchor="nw")
    self.active_crop_label = tk.Label(self.active_crop_frame, bd=0, padx=0, pady=0)
    self.active_crop_label.pack()
    self.active_crop_photo = None
    self._active_crop_fixed_size: tuple[int, int] | None = None
    # Keep fixed-preview zoom in sync with inline crops.
    self._active_crop_fixed_zoom: float | None = None
    self._review_display_crops: list[Image.Image] = []
    self._review_row_pictures: list[ttk.Label] = []

    self.canvas = tk.Canvas(
        editor_area,
        highlightthickness=0,
        borderwidth=0,
        bg="#f6f7f9",
    )
    scroll = ttk.Scrollbar(editor_area, orient="vertical", command=self.canvas.yview)
    self.canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    self.canvas.pack(fill="both", expand=True)
    self.rows = ttk.Frame(self.canvas, style="PCR.Surface.TFrame")
    self.rows_window = self.canvas.create_window((0, 0), window=self.rows, anchor="nw")
    self.rows.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
    self.canvas.bind("<Configure>", self._review_canvas_configured)
    for widget in (self.canvas, self.rows):
        widget.bind("<MouseWheel>", self.scroll_rows)
        widget.bind("<Button-4>", lambda e: self.scroll_rows_linux(-1))
        widget.bind("<Button-5>", lambda e: self.scroll_rows_linux(1))

    # Right: only the reference list starts open; all helpers start folded.
    review_info = self._review_collapsible_section(
        right, "display", "显示设置", padding=6, fill="x", pady=(0, 6)
    )
    extended_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
    extended_row.pack(fill="x", pady=(0, 3))
    ttk.Label(extended_row, text="切片更大高度范围倍数:").pack(side="left")
    extended_spin = ttk.Spinbox(
        extended_row, from_=1.0, to=10.0, increment=0.1, width=6,
        textvariable=self.review_extended_crop_multiplier_var,
        style="PCR.Compact.TSpinbox",
    )
    extended_spin.pack(side="left", padx=(5, 0))
    extended_spin.bind(
        "<Return>", lambda _event: self._apply_review_extended_crop_multiplier_setting()
    )
    extended_spin.bind(
        "<FocusOut>",
        lambda _event: self._apply_review_extended_crop_multiplier_setting(
            revert_invalid=True
        ),
    )

    def add_review_height_control(
        label: str,
        percent_var: tk.StringVar,
        pixel_var: tk.StringVar,
        *,
        allow_zero: bool = False,
    ) -> ttk.Spinbox:
        control_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
        control_row.pack(fill="x", pady=(0, 3))
        ttk.Label(control_row, text=label).pack(side="left")
        percent_spin = ttk.Spinbox(
            control_row,
            from_=0.0 if allow_zero else 0.01,
            to=100.0,
            increment=0.01,
            width=6,
            textvariable=percent_var,
            style="PCR.Compact.TSpinbox",
        )
        percent_spin.pack(side="left")
        ttk.Label(control_row, text="%").pack(side="left", padx=(2, 6))
        ttk.Spinbox(
            control_row,
            from_=0 if allow_zero else 1,
            to=500,
            increment=1,
            width=6,
            textvariable=pixel_var,
            style="PCR.Compact.TSpinbox",
        ).pack(side="left")
        ttk.Label(control_row, text="px").pack(side="left", padx=(2, 0))
        return percent_spin

    self.review_line_height_spin = add_review_height_control(
        "普通字/行高：", self.review_line_height_var, self.review_line_height_px_var
    )
    add_review_height_control(
        "行间空：",
        self.review_row_padding_var,
        self.review_row_padding_px_var,
        allow_zero=True,
    )
    add_review_height_control(
        "普通词条行切图高：",
        self.review_regular_crop_height_var,
        self.review_regular_crop_height_px_var,
    )
    self.review_single_cjk_line_height_spin = add_review_height_control(
        "大字头切图高：",
        self.review_single_cjk_line_height_var,
        self.review_single_cjk_line_height_px_var,
    )

    zoom_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
    zoom_row.pack(fill="x")
    ttk.Label(zoom_row, text="词条切图显示大小：").pack(side="left")
    ttk.Button(
        zoom_row, text="−", width=3, command=lambda: self.change_review_zoom(0.8),
        style="PCR.Tool.TButton",
    ).pack(side="left")
    review_zoom_entry = ttk.Entry(
        zoom_row, textvariable=self.review_zoom_var, width=10, justify="center",
        style="PCR.Compact.TEntry",
    )
    review_zoom_entry.pack(side="left", padx=2)
    review_zoom_entry.bind("<Return>", self.apply_review_zoom_text)
    review_zoom_entry.bind("<FocusOut>", self.apply_review_zoom_text)
    ttk.Button(
        zoom_row, text="+", width=3, command=lambda: self.change_review_zoom(1.25),
        style="PCR.Tool.TButton",
    ).pack(side="left")
    ttk.Button(
        zoom_row, text="自动", width=5, command=self.reset_review_zoom,
        style="PCR.Compact.TButton",
    ).pack(side="left", padx=(4, 0))

    padding_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
    padding_row.pack(fill="x", pady=(4, 0))
    ttk.Label(
        padding_row, text="文本左边距：", style="PCR.Black.TLabel"
    ).pack(side="left")
    self.review_left_padding_spin = ttk.Spinbox(
        padding_row, from_=0, to=80, increment=1, width=4,
        textvariable=self.review_left_padding_var, style="PCR.Compact.TSpinbox",
    )
    self.review_left_padding_spin.pack(side="left")
    ttk.Label(
        padding_row, text="px", style="PCR.Body.TLabel"
    ).pack(side="left", padx=(2, 9))
    ttk.Label(
        padding_row, text="上下边距：", style="PCR.Black.TLabel"
    ).pack(side="left")
    self.review_vertical_padding_spin = ttk.Spinbox(
        padding_row, from_=0, to=30, increment=1, width=4,
        textvariable=self.review_vertical_padding_var, style="PCR.Compact.TSpinbox",
    )
    self.review_vertical_padding_spin.pack(side="left")
    ttk.Label(
        padding_row, text="px", style="PCR.Body.TLabel"
    ).pack(side="left", padx=(2, 0))

    font_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
    font_row.pack(fill="x", pady=(5, 0))
    ttk.Label(font_row, text="词条字体：").pack(side="left")
    review_families = (AUTO_FONT_FAMILY, *tuple(sorted(set(font.families()), key=str.casefold)))
    self.review_font_combo = ttk.Combobox(
        font_row, textvariable=self.review_font_family_var, values=review_families,
        state="normal", width=15, style="PCR.Compact.TCombobox",
    )
    self.review_font_combo.pack(side="left")
    self.review_font_size_spin = ttk.Spinbox(
        font_row, from_=6, to=96, increment=1, width=4,
        textvariable=self.review_font_size_var, style="PCR.Compact.TSpinbox",
    )
    self.review_font_size_spin.pack(side="left")
    ttk.Checkbutton(font_row, text="粗", variable=self.review_font_bold_var).pack(side="left", padx=(7, 0))
    ttk.Checkbutton(font_row, text="斜", variable=self.review_font_italic_var).pack(side="left", padx=(5, 0))

    simplified_font_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
    simplified_font_row.pack(fill="x", pady=(4, 0))
    ttk.Label(simplified_font_row, text="简体字体：").pack(side="left")
    self.review_simplified_font_combo = ttk.Combobox(
        simplified_font_row, textvariable=self.review_simplified_font_family_var,
        values=review_families, state="normal", width=15,
        style="PCR.Compact.TCombobox",
    )
    self.review_simplified_font_combo.pack(side="left")
    self.review_simplified_font_size_spin = ttk.Spinbox(
        simplified_font_row, from_=6, to=96, increment=1, width=4,
        textvariable=self.review_simplified_font_size_var, style="PCR.Compact.TSpinbox",
    )
    self.review_simplified_font_size_spin.pack(side="left")
    ttk.Checkbutton(
        simplified_font_row, text="粗", variable=self.review_simplified_font_bold_var
    ).pack(side="left", padx=(7, 0))
    ttk.Checkbutton(
        simplified_font_row, text="斜", variable=self.review_simplified_font_italic_var
    ).pack(side="left", padx=(5, 0))

    digit_box = self._review_collapsible_section(
        right, "digit", "数字替换映射", padding=6, fill="x", pady=(0, 6)
    )
    digit_rows = [
        ttk.Frame(digit_box, style="PCR.Surface.TFrame"),
        ttk.Frame(digit_box, style="PCR.Surface.TFrame"),
    ]
    digit_rows[0].pack(fill="x")
    digit_rows[1].pack(fill="x", pady=(3, 0))
    ttk.Checkbutton(
        digit_rows[0], text="启用", variable=self.replace_digits,
        style="PCR.Body.TCheckbutton",
    ).pack(side="left", padx=(0, 8))
    for index, digit in enumerate(self.DIGIT_KEYS):
        host = digit_rows[0 if index < 5 else 1]
        ttk.Label(host, text=f"{digit}→").pack(side="left", padx=(2, 0))
        ttk.Entry(
            host, textvariable=self.digit_map_vars[index], width=3, justify="center",
            style="PCR.Compact.TEntry",
        ).pack(side="left", padx=(0, 5))

    accent_box = self._review_collapsible_section(
        right, "accent", "变音字符", padding=6, fill="x", pady=(0, 6)
    )
    ttk.Label(
        accent_box, text="左键输入；右键复制", style="PCR.Muted.TLabel",
    ).pack(anchor="w", pady=(0, 3))
    for label, chars in self.ACCENT_GROUPS:
        accent_row = ttk.Frame(accent_box, style="PCR.Surface.TFrame")
        accent_row.pack(fill="x", pady=1)
        ttk.Label(accent_row, text=label, width=4, anchor="e").pack(side="left", padx=(0, 4))
        for char in chars:
            accent_button = ttk.Button(
                accent_row, text=char, width=3,
                command=lambda c=char: self.insert_char(c),
                style="PCR.Tool.TButton",
            )
            accent_button.pack(side="left", padx=1)
            accent_button.bind(
                "<Button-3>", lambda _event, c=char: self.copy_char(c), add="+"
            )
    # Keep the four OCR sources on a single compact line. Each available
    # result remains clickable, preserving the previous quick-fill workflow.
    ocr_box = self._review_collapsible_section(
        right, "ocr", "OCR结果", padding=6, fill="x", pady=(0, 6)
    )
    ocr_compare_row = ttk.Frame(ocr_box, style="PCR.Surface.TFrame")
    ocr_compare_row.pack(fill="x")
    ttk.Label(
        ocr_compare_row, text="与OCR比较：", style="PCR.Body.TLabel"
    ).pack(side="left")
    self.review_ocr_compare_combo = ttk.Combobox(
        ocr_compare_row, textvariable=self.review_ocr_compare_var,
        values=tuple(self.OCR_COMPARE_LABEL_TO_KEY), state="readonly", width=10,
        style="PCR.Compact.TCombobox",
    )
    self.review_ocr_compare_combo.pack(side="left", padx=(2, 0))
    self.review_ocr_compare_combo.bind(
        "<<ComboboxSelected>>", self._change_review_ocr_compare_source
    )
    ttk.Checkbutton(
        ocr_compare_row, text="简体化词条", variable=self.review_show_simplified_var,
        command=self._toggle_review_simplified, style="PCR.Body.TCheckbutton",
    ).pack(side="left", padx=(8, 0))
    ttk.Button(
        ocr_compare_row, text="重新简体化", command=self.regenerate_simplified_current_page,
        style="PCR.Compact.TButton",
    ).pack(side="left", padx=(6, 0))

    ocr_row = ttk.Frame(ocr_box, style="PCR.Surface.TFrame")
    ocr_row.pack(fill="x", pady=(4, 0))
    self.ocr_options = ttk.Frame(ocr_row, style="PCR.Surface.TFrame")
    self.ocr_options.pack(side="left", fill="x", expand=True)

    network_box = self._review_collapsible_section(
        right, "network", "词条联网核验结果",
        padding=6, fill="x", pady=(0, 6),
    )
    network_actions = ttk.Frame(network_box, style="PCR.Surface.TFrame")
    network_actions.pack(fill="x")
    ttk.Checkbutton(
        network_actions, text="自动检查", variable=self.network_lookup_enabled_var,
        command=self._toggle_network_lookup,
    ).pack(side="left")
    ttk.Button(
        network_actions, text="立即",
        command=lambda: self._schedule_network_lookup(force=True),
        style="PCR.Compact.TButton",
    ).pack(side="left", padx=(5, 0))
    self.cc_cedict_lookup_button = ttk.Button(
        network_actions, textvariable=self.cc_cedict_lookup_var,
        command=self.manage_cc_cedict, style="PCR.Tool.TButton",
    )
    self.cc_cedict_lookup_button.pack(side="left", padx=(5, 0))
    self.cc_simplified_compare_button = ttk.Button(
        network_actions, textvariable=self.cc_simplified_compare_var,
        command=self.show_cc_simplified_comparison, style="PCR.Tool.TButton",
    )
    self.cc_simplified_compare_button.pack(side="left", padx=(5, 0))

    network_actions_more = ttk.Frame(network_box, style="PCR.Surface.TFrame")
    network_actions_more.pack(fill="x", pady=(4, 0))
    ttk.Button(
        network_actions_more, textvariable=self.moedict_lookup_var,
        command=lambda: self.open_lookup_source("萌典"), style="PCR.Tool.TButton",
    ).pack(side="left")
    ttk.Button(
        network_actions_more, textvariable=self.wiktionary_lookup_var,
        command=lambda: self.open_lookup_source("维基词典"), style="PCR.Tool.TButton",
    ).pack(side="left", padx=(5, 0))
    ttk.Button(
        network_actions_more, text="网络搜索", command=self.open_network_web_search,
        style="PCR.Tool.TButton",
    ).pack(side="left", padx=(5, 0))
    self.network_status_label = tk.Label(
        network_box,
        textvariable=self.network_lookup_status_var,
        anchor="w",
        justify="left",
        fg="#555555",
        bg="#f6f7f9",
    )
    self.network_status_label.pack(fill="x", pady=(4, 0))
    self._refresh_cc_cedict_button_idle()

    ref_box = self._review_collapsible_section(
        right, "reference", "参考词表",
        padding=6, fill="both", expand=True, pady=(0, 0),
    )
    ref_actions = ttk.Frame(ref_box, style="PCR.Surface.TFrame")
    ref_actions.pack(fill="x", pady=(0, 3))
    ttk.Button(
        ref_actions, text="选择文件", command=self.choose_wordslist_file,
        style="PCR.Compact.TButton",
    ).pack(side="left")
    ttk.Label(ref_actions, text="定位：").pack(side="left", padx=(8, 2))
    self.wordslist_locator_combo = ttk.Combobox(
        ref_actions, textvariable=self.wordslist_locator_var,
        values=tuple(self.WORDSLIST_LOCATOR_LABEL_TO_KEY), state="readonly", width=18,
        style="PCR.Compact.TCombobox",
    )
    self.wordslist_locator_combo.pack(side="left")
    self.wordslist_locator_combo.bind("<<ComboboxSelected>>", self._change_wordslist_locator_mode)
    ttk.Button(
        ref_actions, text="从所选词开始填充至本页结束", command=self.fill_words,
        style="PCR.Compact.TButton",
    ).pack(side="left", padx=(8, 0))

    word_nav = ttk.Frame(ref_box, style="PCR.Surface.TFrame")
    word_nav.pack(fill="x", pady=(0, 0))
    self.word_window_var = tk.StringVar(value="wordslist.txt | 0-0 / 0")
    ttk.Label(
        word_nav, textvariable=self.word_window_var, style="PCR.Body.TLabel"
    ).pack(side="left", fill="x", expand=True)
    word_nav_buttons = ttk.Frame(word_nav, style="PCR.Surface.TFrame")
    word_nav_buttons.pack(side="right")
    ttk.Button(
        word_nav_buttons, text="前100", width=7, command=lambda: self.shift_wordslist_window(-1),
        style="PCR.Tool.TButton",
    ).pack(side="left")
    ttk.Button(
        word_nav_buttons, text="后100", width=7, command=lambda: self.shift_wordslist_window(1),
        style="PCR.Tool.TButton",
    ).pack(side="left", padx=(4, 0))

    word_family = preferred_font_family(
        self, ("Cambria", "Times New Roman", "Times", "DejaVu Serif")
    )
    number_family = preferred_font_family(
        self, ("Segoe UI", "Arial", "Helvetica", "DejaVu Sans")
    )
    self.word_list = tk.Text(
        ref_box,
        exportselection=False,
        font=(word_family, 14),
        wrap="none",
        state="disabled",
        cursor="hand2",
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground="#d8dde5",
        highlightcolor="#d8dde5",
        selectbackground="#dce8f7",
        selectforeground="#30343b",
    )
    self.word_list.tag_configure(
        "wordslist_number", font=(number_family, 10), foreground="#6b7280"
    )
    self.word_list.tag_configure("wordslist_word", font=(word_family, 14))
    self.word_list.tag_configure(
        "wordslist_target", background="#d9d9d9", foreground="#111827"
    )
    # The reference list owns its row highlighting and mixed typography.
    self.word_list._pc_skip_classic_appearance = True
    self.word_list.pack(fill="both", expand=True, pady=(4, 0))
    self._configure_word_list_appearance()
    self.word_list.bind("<ButtonRelease-1>", self.use_selected_word)
    self.refresh_wordslist_display()


def _request_render_rows(
    self, deps: ReviewWorkspaceDeps, *, focus_index: int | None = None, reset_scroll: bool = False,
) -> None:
    """Prepare proofreading crops off-thread; materialize Tk widgets only on Tk."""
    ttk = deps.ttk
    tk = deps.tk
    Image = deps.Image
    _format_layout_percent = deps._format_layout_percent
    _review_crop_context = deps._review_crop_context
    _review_line_box = deps._review_line_box
    sync_review_entry_classification = deps.sync_review_entry_classification
    normalize_page_rgb = deps.normalize_page_rgb
    review_auto_fit_zoom = deps.review_auto_fit_zoom
    replace = deps.replace
    sync_review_entry_classification(self)
    if getattr(self, "_filter_rows_active", False):
        return
    project = getattr(self.parent, "project", None)
    current_page = getattr(self.parent, "current_page", None)
    parent_image = getattr(self.parent, "image", None)
    if project is None or current_page is None or parent_image is None:
        # Keep lightweight unit/embedding stubs compatible without ever
        # making the production path fall back to synchronous image work.
        fallback = self.__dict__.get("render_rows")
        if callable(fallback):
            fallback()
        return
    if focus_index is None:
        focus_index = self.active_index
    self._review_render_focus_index = max(0, int(focus_index))

    page = self.parent.current_page
    page_index = int(self.parent.current_index)
    settings = replace(self.parent.settings)
    requested_auto_zoom = bool(self.review_zoom_auto)
    review_zoom = max(0.01, float(self.review_zoom))
    auto_image_area_width = self._review_image_area_width()
    viewer_width = max(1, int(self.parent.canvas.winfo_width()))
    source_entries = self.parent._ordered_entries_reading_order()
    # Existing text widgets can contain unsaved edits. Snapshot only values
    # bound to the same Entry objects, never another row with the same index.
    visible_text = {
        id(entry): var.get()
        for entry, var in zip(self._bound_row_entries(), self.vars)
    }
    editor_texts = tuple(visible_text.get(id(entry), entry.word) for entry in source_entries)
    ordered_snapshot = [replace(entry) for entry in source_entries]
    # Bind crop snapshots to Entry identity, not just coordinates/text;
    # otherwise two equal-valued entries may swap rows during the worker.
    signature = tuple(
        (id(source), int(entry.x), int(entry.y), str(entry.word))
        for source, entry in zip(source_entries, ordered_snapshot)
    )
    page_stem = page.stem

    def worker():
        with Image.open(page) as opened:
            image = normalize_page_rgb(opened)
        review_settings, geometry = _review_crop_context(
            image, settings, viewer_width, page_index,
        )
        # Every editor row uses the visible text length, not obsolete
        # regular/oversized classification or OCR-detected glyph height.
        raw_crops: list[Image.Image] = []
        for index, entry in enumerate(ordered_snapshot):
            next_entry = (
                ordered_snapshot[index + 1]
                if index + 1 < len(ordered_snapshot) else None
            )
            box = _review_line_box(
                entry, geometry, image, review_settings, next_entry,
                editor_text=editor_texts[index],
            )
            raw_crops.append(image.crop(box).convert("RGB"))
        effective_zoom = review_zoom
        if requested_auto_zoom and raw_crops:
            widest_crop = max(crop.width for crop in raw_crops)
            effective_zoom = review_auto_fit_zoom(
                widest_crop, auto_image_area_width, 0.99,
            )
        crops = [
            crop.resize(
                (
                    max(1, round(crop.width * effective_zoom)),
                    max(1, round(crop.height * effective_zoom)),
                ),
                Image.Resampling.LANCZOS,
            )
            for crop in raw_crops
        ]
        return page_stem, signature, crops, effective_zoom, requested_auto_zoom

    def done(payload) -> None:
        try:
            if not self.winfo_exists() or self._prefetch_closed:
                return
        except tk.TclError:
            return
        result_stem, result_signature, crops, effective_zoom, requested_auto_zoom = payload
        if requested_auto_zoom != bool(self.review_zoom_auto):
            self._request_render_rows(focus_index=self._review_render_focus_index)
            return
        if not self.parent.current_page or self.parent.current_page.stem != result_stem:
            return
        current_signature = tuple(
            (id(entry), int(entry.x), int(entry.y), str(entry.word))
            for entry in self.parent._ordered_entries_reading_order()
        )
        if current_signature != result_signature:
            self._request_render_rows(focus_index=self._review_render_focus_index)
            return
        if requested_auto_zoom:
            self.review_zoom = max(0.01, float(effective_zoom))
            self.review_zoom_var.set(f"自动 {_format_layout_percent(self.review_zoom * 100.0)}%")
            self.parent.settings.review_zoom_percent = 0.0
        target_focus = self._review_render_focus_index
        self.render_rows(preloaded_crops=crops)
        if reset_scroll:
            self._reset_rows_scroll_top()
        if self.editors:
            self.focus_index(min(target_focus, len(self.editors) - 1))

    def failed(exc, detail) -> None:
        if detail:
            print(detail)
        try:
            if not self.winfo_exists() or self._prefetch_closed:
                return
        except tk.TclError:
            return
        self.parent.status_var.set(f"校对裁剪生成失败：{exc}")
        if not self.rows.winfo_children():
            ttk.Label(
                self.rows, text=f"校对裁剪生成失败：{exc}",
            ).grid(row=0, column=0, sticky="ew", padx=8, pady=20)

    self.parent._start_ui_worker(
        self._review_render_worker_key, worker, done, failed,
    )


def render_rows(self, deps: ReviewWorkspaceDeps, preloaded_crops: list[Image.Image] | None = None) -> None:
    tk = deps.tk
    Image = deps.Image
    font = deps.font
    _entry_font_spec = deps._entry_font_spec
    _review_editor_font_size = deps._review_editor_font_size
    resolve_content_font_family = deps.resolve_content_font_family
    _focused_review_is_single_character = deps._focused_review_is_single_character
    simplified_entry_key = deps.simplified_entry_key
    if getattr(self, "_filter_rows_active", False):
        return
    if preloaded_crops is None:
        self._request_render_rows(focus_index=self.active_index)
        return
    current_stem = self.parent.current_page.stem if self.parent.current_page else ""
    if self._rendered_page_stem and self._rendered_page_stem == current_stem:
        self._capture_simplified_edits(self._rendered_page_stem)
    # Pending height-switch jobs belong to the outgoing rendered rows.
    for job in getattr(self, "_review_crop_height_jobs", {}).values():
        try:
            self.after_cancel(job)
        except tk.TclError:
            pass
    self._review_crop_height_jobs = {}
    self._review_crop_single_flags = []
    self._review_crop_render_generation = getattr(
        self, "_review_crop_render_generation", 0
    ) + 1
    for child in self.rows.winfo_children():
        child.destroy()
    self.vars.clear(); self.row_entries.clear(); self.editors.clear(); self.editor_frames.clear(); self.simplified_vars.clear(); self.simplified_editors.clear(); self.simplified_search_buttons.clear(); self.simplified_actual_values.clear(); self.simplified_manual_flags.clear(); self.simplified_auto_refresh_flags.clear(); self.editor_crop_widths.clear(); self.thumbnails.clear()
    if getattr(self, "_active_crop_page_stem", None) != current_stem:
        self._active_crop_fixed_size = None
        self._active_crop_page_stem = current_stem
    from .review_transaction_actions import history_page_changed
    history_page_changed(self, current_stem)
    self._rendered_page_stem = current_stem
    self.__dict__.pop("_r3_simplified_capture_blocked", None)
    simplified_records = self._simplified_page_records(current_stem) if current_stem else {}
    if not self.parent.image:
        return
    ordered = self.parent._ordered_entries_reading_order()
    if len(preloaded_crops) < len(ordered):
        self._request_render_rows(focus_index=self.active_index)
        return
    self._review_display_crops = list(preloaded_crops)
    self._review_row_pictures.clear()
    words = self.parent._project_words if self.parent.project else set()
    from .review_crop_sequence import create_review_crop_with_index
    for index, entry in enumerate(ordered):
        next_entry = ordered[index + 1] if index + 1 < len(ordered) else None
        # Crop and LANCZOS resize are completed by a worker before this
        # UI-only materialization step. ImageTk creation stays on Tk.
        crop = preloaded_crops[index]
        self.editor_crop_widths.append(crop.width)
        # Each inline slice already has its text-dependent crop height:
        # one-character headwords use 大字头切图高, others use ordinary.
        photo = self._ordinary_review_photo(index)
        picture, sequence_label, crop_row = create_review_crop_with_index(
            self, self.rows, photo=photo, index=index, total=len(ordered),
        )
        self.thumbnails.append(photo)
        self._review_row_pictures.append(picture)
        var = tk.StringVar(value=entry.word)
        # Review zoom changes only the cropped line image.  Text-entry font
        # size is a user setting and remains fixed while zooming the image.
        editor_font_size = _review_editor_font_size(self.parent.settings)
        review_family = resolve_content_font_family(
            self,
            self.parent.settings.review_entry_font_family,
            self.parent.settings.ocr_language,
        )
        review_weight = "bold" if self.parent.settings.review_entry_font_bold else "normal"
        review_slant = "italic" if self.parent.settings.review_entry_font_italic else "roman"
        simplified_family = resolve_content_font_family(
            self,
            getattr(
                self.parent.settings,
                "review_simplified_font_family",
                self.parent.settings.review_entry_font_family,
            ),
            self.parent.settings.ocr_language,
        )
        simplified_font_size = max(6, int(getattr(self.parent.settings, "review_simplified_font_size", editor_font_size)))
        simplified_bold = bool(getattr(self.parent.settings, "review_simplified_font_bold", self.parent.settings.review_entry_font_bold))
        simplified_italic = bool(getattr(self.parent.settings, "review_simplified_font_italic", self.parent.settings.review_entry_font_italic))
        measure_font = font.Font(
            family=review_family, size=editor_font_size, weight=review_weight, slant=review_slant
        )
        char_px = max(1, measure_font.measure("0"))
        editor_width_chars = max(8, min(140, round(crop.width / char_px)))
        editor_bg, editor_fg, selection_bg, selection_fg = (
            self._review_membership_colors(entry.word in words)
        )
        editor_frame = tk.Frame(
            self.rows,
            bg=editor_bg,
            bd=0,
            relief="flat",
            highlightthickness=1,
            highlightbackground=editor_bg,
            highlightcolor=editor_bg,
        )
        # Membership colors are intentionally pale status colors in both
        # themes. Keep this frame out of the generic dark mapper.
        editor_frame._pc_skip_classic_appearance = True
        from .overlay_delete_button import fixed_overlay_control_font
        delete_button = tk.Button(
            editor_frame, text="[X]", width=3, takefocus=False,
            font=fixed_overlay_control_font(
                editor_frame, self.parent.settings.ocr_language,
            ),
            relief="flat", bd=0, padx=1, pady=0, cursor="hand2",
            fg="#8b1a1a", bg="#f3eeee", activebackground="#f4d9d9",
            command=lambda i=index: self.delete_review_entry(i),
        )
        delete_button.grid(row=0, column=0, sticky="nsw", padx=(0, 2))
        editor = tk.Entry(
            editor_frame, textvariable=var, width=1,
            font=_entry_font_spec(
                review_family, editor_font_size,
                self.parent.settings.review_entry_font_bold, self.parent.settings.review_entry_font_italic,
            ),
            bg=editor_bg,
            disabledbackground=editor_bg,
            foreground=editor_fg,
            disabledforeground=editor_fg,
            insertbackground=editor_fg,
            selectbackground=selection_bg,
            selectforeground=selection_fg,
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        # Membership surfaces use theme-aware status colours.
        editor._pc_skip_classic_appearance = True
        editor.grid(
            row=0, column=1, sticky="nsew",
            padx=(max(0, int(self.parent.settings.review_entry_left_padding)), 0),
            ipady=max(0, int(self.parent.settings.review_entry_vertical_padding)),
        )
        simplified_key = simplified_entry_key(entry.x, entry.y)
        saved_simplified = simplified_records.get(simplified_key)
        source_conflict = source_word_conflicts(saved_simplified, entry.word)
        saved_manual = bool(saved_simplified.get("manual", False)) if saved_simplified else False
        saved_text = str(saved_simplified.get("text", "")) if saved_simplified is not None else None
        if source_conflict:
            # Never display an old human correction as this PDIC word merely
            # because another Entry reused the original pixel coordinate.
            saved_manual = True
            saved_text = "⚠来源词条不一致，请核对原词"
        # v2.12.11: once a simplified record exists on disk, its text is the
        # source of truth on reopen, regardless of whether it was originally
        # generated by OpenCC or manually edited.  OpenCC is only used to
        # seed rows that have no persisted record yet.
        auto_refresh = saved_simplified is None
        if saved_simplified is not None:
            simplified_actual = saved_text
        else:
            simplified_actual = self._auto_simplified_value(entry.word)
        simplified_var = tk.StringVar(
            value=self._simplified_display_from_value(entry.word, simplified_actual, saved_manual)
        )
        simplified_editor = tk.Entry(
            editor_frame, textvariable=simplified_var, width=1,
            font=_entry_font_spec(
                simplified_family, simplified_font_size, simplified_bold, simplified_italic,
            ),
            bg="#f4f4f4", foreground="#303030",
            relief="flat", bd=0, highlightthickness=0, justify="left",
        )
        simplified_editor.grid(
            row=0, column=2, sticky="nsew", padx=(6, 0),
            ipady=max(0, int(self.parent.settings.review_entry_vertical_padding)),
        )
        if source_conflict:
            simplified_editor.configure(
                state="disabled", disabledforeground="#8b1a1a",
            )
        simplified_search_button = tk.Button(
            editor_frame, text="网查", width=4, takefocus=False,
            relief="flat", bd=0, padx=2, pady=0, cursor="hand2",
            bg="#eceff3", activebackground="#e1e5ea", foreground="#30343b",
            command=lambda i=index: self.lookup_simplified_online(i),
        )
        simplified_search_button.grid(row=0, column=3, sticky="ns", padx=(4, 0))
        editor_frame.columnconfigure(1, weight=1, uniform=f"review_pair_{index}")
        editor_frame.columnconfigure(2, weight=1, uniform=f"review_pair_{index}")
        editor_frame.columnconfigure(3, weight=0)
        editor_frame.grid(row=index * 2 + 1, column=0, sticky="ew", padx=6, pady=(2, 8))
        if not self.review_show_simplified_var.get():
            simplified_editor.grid_remove()
            simplified_search_button.grid_remove()
            editor_frame.columnconfigure(2, weight=0, uniform="")
        if self.parent._foreground_batch_state(self.parent.current_index) == "processing":
            delete_button.configure(state="disabled")
            editor.configure(state="disabled", disabledforeground="#555555")
            simplified_editor.configure(state="disabled", disabledforeground="#666666")
            simplified_search_button.configure(state="disabled")
        editor.bind("<FocusIn>", lambda _e, i=index: self.set_active(i))
        editor.bind("<KeyPress-grave>", lambda _e, i=index: self.delete_review_entry(i))
        editor.bind("<KeyPress>", self.parent._entry_keypress_batch_guard)
        editor.bind("<<Paste>>", lambda _e: None if self.parent._claim_page_for_manual_edit() else "break")
        editor.bind("<<Cut>>", lambda _e: None if self.parent._claim_page_for_manual_edit() else "break")
        editor.bind("<KeyRelease>", lambda e, i=index: self.on_key(e, i))
        editor.bind("<Return>", lambda _e, i=index: self.focus_index(i + 1))
        editor.bind("<Up>", lambda _e, i=index: self.focus_index(i - 1))
        editor.bind("<Down>", lambda _e, i=index: self.focus_index(i + 1))
        simplified_editor.bind("<FocusIn>", lambda _e, i=index: self._focus_simplified_editor(i))
        simplified_editor.bind("<KeyPress-grave>", lambda _e, i=index: self.delete_review_entry(i))
        simplified_editor.bind("<KeyPress>", self.parent._entry_keypress_batch_guard)
        simplified_editor.bind("<<Paste>>", lambda _e, i=index: self._claim_simplified_clipboard_edit(i))
        simplified_editor.bind("<<Cut>>", lambda _e, i=index: self._claim_simplified_clipboard_edit(i))
        simplified_editor.bind("<KeyRelease>", lambda e, i=index: self.on_simplified_key(e, i))
        # IME/text-service and native menu edits may not emit KeyRelease.
        simplified_editor.bind("<FocusOut>", lambda e, i=index: self.on_simplified_key(e, i))
        simplified_editor.bind("<Return>", lambda _e, i=index: self.focus_index(i + 1))
        for widget in (picture, sequence_label, crop_row, delete_button, editor_frame, editor, simplified_editor, simplified_search_button):
            widget.bind("<MouseWheel>", self.scroll_rows)
            widget.bind("<Button-4>", lambda e: self.scroll_rows_linux(-1))
            widget.bind("<Button-5>", lambda e: self.scroll_rows_linux(1))
        self.vars.append(var); self.row_entries.append(entry); self.editors.append(editor); self.editor_frames.append(editor_frame)
        self._review_crop_single_flags.append(_focused_review_is_single_character(var.get()))
        var.trace_add("write", lambda *_args, i=index: self._schedule_review_crop_height_update(i))
        self.simplified_vars.append(simplified_var); self.simplified_editors.append(simplified_editor)
        self.simplified_search_buttons.append(simplified_search_button)
        self.simplified_actual_values.append(simplified_actual)
        self.simplified_manual_flags.append(saved_manual)
        self.simplified_auto_refresh_flags.append(auto_refresh)
        materialized_record = {
            "x": int(entry.x), "y": int(entry.y), "source_word": entry.word,
            "text": "" if simplified_actual is None else str(simplified_actual), "manual": saved_manual,
        }
        # Materialize OpenCC only when this row has never had a saved
        # simplified record.  Merely reopening a page must not rewrite an
        # existing automatic or manual value.
        if saved_simplified is None:
            simplified_records[simplified_key] = materialized_record
            self._simplified_dirty_pages.add(current_stem)
    self.rows.columnconfigure(0, weight=1)
    self._update_title()
    self._refresh_editor_ocr_compare()
    if self.editors:
        self.editors[0].focus_set()
        self.set_active(0)
    self._schedule_adjacent_preload()
    self.parent._apply_current_appearance(self.rows)
    # Re-apply theme-aware membership colours after generic theming.
    for row_index, row_entry in enumerate(self.row_entries):
        self._set_editor_membership_color(
            row_index, row_entry.word in words
        )


def _change_review_mode(self, deps: ReviewWorkspaceDeps) -> None:
    """Switch modes without running a filter merely because 筛选 was selected."""
    if self.review_mode_var.get() != "single":
        self.parent.status_var.set("已选择筛选模式；设置条件后点击【筛选】才会刷新工作区。")
        return
    self._flush_focused_changes_now()
    if getattr(self, "_filter_rows_active", False) and (
        self._filter_save_running or self._filter_pending_changes
    ):
        # The save was scheduled asynchronously, not committed. Preserve
        # its visible editor rows and their original page/XY ownership until
        # completion; a failed worker restores pending edits for retry.
        self.review_mode_var.set("filter")
        self.parent.status_var.set(
            "筛选校对修改尚未保存完成，暂不能切换单页模式。"
        )
        return
    self._filter_rows_active = False
    self._set_filter_navigation(False)
    self.parent._invalidate_ui_worker(f"focused-filter-scan-{id(self)}")
    self.parent._invalidate_ui_worker(f"focused-filter-scan-rest-{id(self)}")
    self.parent._invalidate_ui_worker(f"focused-filter-render-{id(self)}")
    self.parent._invalidate_ui_worker(f"focused-filter-prefetch-{id(self)}")
    self._filter_batch_render_cache.clear()
    self._filter_prefetch_key = None
    self._filter_scan_complete = True
    self._request_render_rows(focus_index=0, reset_scroll=True)


def _set_filter_navigation(self, deps: ReviewWorkspaceDeps, active: bool) -> None:
    tk = deps.tk
    """Reuse the normal side navigation as batch navigation in filter mode."""
    try:
        self.prev_page_button.configure(text=("上\n一\n批" if active else "上\n一\n页"))
        self.next_page_button.configure(text=("下\n一\n批" if active else "下\n一\n页"))
    except tk.TclError:
        return


def _clear_review_workspace(self, deps: ReviewWorkspaceDeps, message: str = "") -> None:
    ttk = deps.ttk
    for child in self.rows.winfo_children():
        child.destroy()
    self.vars.clear()
    self.row_entries.clear()
    self.editors.clear()
    self.editor_frames.clear()
    self.simplified_vars.clear()
    self.simplified_editors.clear()
    self.simplified_search_buttons.clear()
    self.simplified_actual_values.clear()
    self.simplified_manual_flags.clear()
    self.simplified_auto_refresh_flags.clear()
    self.editor_crop_widths.clear()
    self.thumbnails.clear()
    self.filter_vars = []
    self.filter_editors = []
    self.filter_thumbnails = []
    self._filter_current_batch_targets = []
    if message:
        ttk.Label(
            self.rows, text=message, style="PCR.Body.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=24)
        self.rows.columnconfigure(0, weight=1)


def copy_char(self, deps: ReviewWorkspaceDeps, char: str) -> str:
    tk = deps.tk
    try:
        self.clipboard_clear()
        self.clipboard_append(str(char))
        self.update_idletasks()
        self.parent.status_var.set(f"已复制变音字符：{char}")
    except tk.TclError:
        pass
    return "break"


def _review_membership_colors(
    self, deps: ReviewWorkspaceDeps, in_wordslist: bool,
) -> tuple[str, str, str, str]:
    appearance_palette = deps.appearance_palette
    palette = appearance_palette(self.parent.appearance_mode)
    background = palette["review_present_bg"] if in_wordslist else palette["review_absent_bg"]
    return (
        background,
        palette["review_membership_fg"],
        palette["review_membership_select_bg"],
        palette["review_membership_select_fg"],
    )


def _configure_word_list_appearance(self, deps: ReviewWorkspaceDeps) -> None:
    tk = deps.tk
    appearance_palette = deps.appearance_palette
    palette = appearance_palette(self.parent.appearance_mode)
    dark = self.parent.appearance_mode == "dark"
    selection_bg = "#d9d9d9" if dark else "#dce8f7"
    try:
        self.word_list.configure(
            background=palette["input_bg"],
            foreground=palette["input_fg"],
            selectbackground=selection_bg,
            selectforeground="#111827",
            highlightbackground=palette["border"],
            highlightcolor=palette["border"],
        )
        self.word_list.tag_configure("wordslist_number", foreground=palette["muted"])
        self.word_list.tag_configure(
            "wordslist_target", background="#d9d9d9", foreground="#111827"
        )
    except tk.TclError:
        return
    self.word_list_default_bg = palette["input_bg"]
    self.word_list_default_fg = palette["input_fg"]


def _clear_word_list_rows(self, deps: ReviewWorkspaceDeps) -> None:
    tk = deps.tk
    self.word_selected_local_index = None
    try:
        self.word_list.configure(state="normal")
        self.word_list.delete("1.0", "end")
        self.word_list.configure(state="disabled")
    except tk.TclError:
        return


def _render_word_list_rows(self, deps: ReviewWorkspaceDeps, words: list[str]) -> None:
    tk = deps.tk
    self.word_selected_local_index = None
    try:
        self.word_list.configure(state="normal")
        self.word_list.delete("1.0", "end")
        digits = max(1, len(str(len(words))))
        for offset, global_index in enumerate(self.word_window_indices):
            self.word_list.insert(
                "end", f"{global_index + 1:>{digits}}", ("wordslist_number",)
            )
            self.word_list.insert(
                "end", f"  {words[global_index]}", ("wordslist_word",)
            )
            if offset + 1 < len(self.word_window_indices):
                self.word_list.insert("end", "\n")
        self.word_list.configure(state="disabled")
    except tk.TclError:
        return


def _set_word_list_highlight(self, deps: ReviewWorkspaceDeps, local: int | None) -> None:
    tk = deps.tk
    try:
        self.word_list.tag_remove("wordslist_target", "1.0", "end")
        if local is None or not (0 <= int(local) < len(self.word_window_indices)):
            return
        line = int(local) + 1
        self.word_list.tag_add(
            "wordslist_target", f"{line}.0", f"{line}.end"
        )
        self.word_list.tag_raise("wordslist_target")
        self.word_list.see(f"{line}.0")
    except tk.TclError:
        return


def _word_list_local_index_from_event(self, deps: ReviewWorkspaceDeps, event: tk.Event) -> int | None:
    tk = deps.tk
    try:
        line = int(str(self.word_list.index(f"@{event.x},{event.y}")).split(".", 1)[0])
    except (tk.TclError, ValueError):
        return None
    local = line - 1
    if not (0 <= local < len(self.word_window_indices)):
        return None
    return local


def _toggle_review_panel(self, deps: ReviewWorkspaceDeps, panel: str) -> None:
    if panel == "digit":
        expanded = not self.digit_map_expanded.get()
        self.digit_map_expanded.set(expanded)
        self.digit_panel_title.set(("▾ " if expanded else "▸ ") + "数字替换映射")
        if expanded:
            self.digit_panel_body.pack(fill="x")
        else:
            self.digit_panel_body.pack_forget()
        return
    expanded = not self.accent_panel_expanded.get()
    self.accent_panel_expanded.set(expanded)
    self.accent_panel_title.set(("▾ " if expanded else "▸ ") + "变音字符")
    if expanded:
        self.accent_panel_body.pack(fill="x")
    else:
        self.accent_panel_body.pack_forget()


def _sync_autosave_label(self, deps: ReviewWorkspaceDeps) -> None:
    seconds = max(1.0, float(getattr(self.parent.settings, "batch_interval", 1.0)))
    value = f"{seconds:g}"
    self.autosave_label_var.set(f"自动：{value} s")


def _toggle_shared_autosave(self, deps: ReviewWorkspaceDeps) -> None:
    """Update the shared autosave caption before toggling the app setting."""
    self._sync_autosave_label()
    self.parent.toggle_autosave()


def open_sort_rules(self, deps: ReviewWorkspaceDeps) -> None:
    # Reuse the same modeless Settings Center so the main image remains
    # available for reference while settings are edited.
    self.parent.open_settings(initial_tab="sort")


def run_order_check(self, deps: ReviewWorkspaceDeps) -> None:
    """Dispatch the existing all-pages/current-page scope without remapping it."""
    # The current Tk scope variable remains the single authority.
    self.check_order(self.order_scope_var.get() == "all")


def _update_title(self, deps: ReviewWorkspaceDeps) -> None:
    page = self.parent.current_page.name if self.parent.current_page else ""
    if getattr(self, "_filter_rows_active", False):
        total = len(self.filtered_targets)
        self.title(f"词条校对 — 筛选模式 — 共 {total} 条")
        return
    total = len(self.editors)
    current = self.active_index + 1 if total else 0
    remaining = max(0, total - current)
    self.title(f"词条校对 — {page} — 当前: {current} 剩余: {remaining} 合计: {total}")

