"""Profile Wizard live headword structure summaries and visible help."""
from __future__ import annotations


def refresh_headword_description(self, *, deps) -> None:
    ttk = deps["ttk"]
    dictionary_profile_preset = deps["dictionary_profile_preset"]
    HEADWORD_HELP_LINES = deps["HEADWORD_HELP_LINES"]
    HEADWORD_EXAMPLE_FILES = deps["HEADWORD_EXAMPLE_FILES"]
    Image = deps["Image"]
    ImageTk = deps["ImageTk"]
    themed_display_image = deps["themed_display_image"]
    key = self._current_profile_key()
    try:
        profile = dictionary_profile_preset(key)
    except Exception:
        return
    self.custom_name_entry.configure(state="normal" if key == "custom" else "disabled")
    self.headword_description_var.set(profile.description)
    self._refresh_headword_structure_summary()
    self._refresh_headword_specificity_visibility()
    hints = {
        "latin_regular": "常规边缘：严格栏左缘定位词头；POS/词形/变体等词后结构是显式证据。视觉补救直接使用本页可见的栏左缘容差、粗体倍率和候选强度，不再叠加隐藏阈值。",
        "cjk_visual": "视觉型：大字/括号结构及视觉突出程度是主证据；大字单字还可结合右侧留白/稀疏度。",
        "numbered_prefix": "编号型：编号前缀是主证据；字号/粗体属于辅助证据。",
        "marker_prefixed": "符号型：○ / ● / ◆ 等固定符号是主证据；字号/粗体属于辅助证据。",
        "custom": "自定义：基础视觉门槛可配合上方 parser 勾选逐页测试。",
    }
    if hasattr(self, "headword_specificity_hint_var"):
        self.headword_specificity_hint_var.set(
            hints.get(key, "当前结构的左缘、字号、粗体与候选强度门槛。")
        )
    self._refresh_headword_tuning_status()

    for child in self.headword_examples_frame.winfo_children():
        child.destroy()
    self._headword_example_photos.clear()

    example_file = HEADWORD_EXAMPLE_FILES.get(key)
    if example_file:
        image = self._headword_example_image(key)
        if image is not None:
            self.update_idletasks()
            right_width = int(getattr(self, "right_canvas", self).winfo_width())
            available = (
                right_width if right_width > 100 else self._wizard_image_width
            )
            image.thumbnail(
                (max(320, available - 20), 520), Image.Resampling.LANCZOS,
            )
            photo = ImageTk.PhotoImage(
                themed_display_image(
                    image, getattr(self.parent, "appearance_mode", "light")
                )
            )
            self._headword_example_photos.append(photo)
            ttk.Label(
                self.headword_examples_frame, image=photo,
            ).grid(row=0, column=0, columnspan=2, sticky="n", padx=5, pady=5)
        else:
            ttk.Label(
                self.headword_examples_frame,
                text=f"缺少样例图片：{example_file}",
                anchor="center", justify="center",
            ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=30)
    else:
        ttk.Label(
            self.headword_examples_frame,
            text="自定义结构不绑定内置样例，请用右侧多页测试确认识别效果。",
            anchor="center", justify="center",
            wraplength=self._wizard_image_width,
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=30)

    for child in self.headword_help_frame.winfo_children():
        child.destroy()
    lines = HEADWORD_HELP_LINES.get(key) or (
        "识别对象：按当前结构预设判断词条起始。",
        "建议：结合第④步多页测试确认是否稳定。",
    )
    for row, line in enumerate(lines):
        ttk.Label(
            self.headword_help_frame,
            text=line, wraplength=self._wizard_content_width, justify="left",
        ).grid(row=row, column=0, sticky="w", pady=3)



def refresh_headword_structure_summary(self) -> None:
    if not hasattr(self, "headword_structure_summary_var"):
        return
    active: list[str] = []
    if self.ordinary_left_edge_var.get():
        active.append("普通左缘短词")
    if self.cjk_allow_bracketed_var.get():
        active.append("【括号词】")
    if self.cjk_allow_single_var.get():
        active.append("大字单字")
    if self.marker_prefix_var.get():
        markers = self.entry_marker_symbols_var.get().strip()
        active.append(
            "固定符号" + (f"（{markers}）" if markers else "")
        )
    if self.numbered_prefix_var.get():
        active.append("编号前缀")
    script_guard_text = (
        "；按OCR语言过滤首字符"
        if self.headword_script_guard_var.get()
        else "；不限制首字符脚本"
    )
    self.headword_structure_summary_var.set(
        "当前词头前/本体："
        + ("、".join(active) if active else "无（不会自动生成词头）")
        + script_guard_text
    )
    tail_active: list[str] = []
    if self.tail_allow_pos_var.get():
        tail_active.append("POS")
    if self.tail_allow_inflection_var.get():
        tail_active.append("词形/屈折")
    if self.tail_allow_variant_var.get():
        tail_active.append("变体/性数")
    if self.tail_allow_pronunciation_var.get():
        tail_active.append("发音/音标")
    if self.tail_allow_descriptor_var.get():
        tail_active.append("描述型结构")
    require_text = (
        "普通左缘词必须命中其一"
        if self.tail_require_selected_var.get()
        else "词后结构仅作加分证据"
    )
    rescue_text = (
        "；允许粗体左缘补救"
        if self.tail_allow_visual_rescue_var.get()
        else ""
    )
    self.tail_structure_summary_var.set(
        "当前词后证据："
        + ("、".join(tail_active) if tail_active else "无")
        + f"｜{require_text}{rescue_text}"
    )



def refresh_headword_specificity_visibility(self) -> None:
    if not hasattr(self, "headword_specificity_frame"):
        return
    self.headword_specificity_frame.grid()
    show_cjk = bool(
        self.cjk_allow_bracketed_var.get() or self.cjk_allow_single_var.get()
    )
    if hasattr(self, "cjk_specificity_frame"):
        if show_cjk:
            self.cjk_specificity_frame.grid()
        else:
            self.cjk_specificity_frame.grid_remove()
    if hasattr(self, "symbol_inventory_frame"):
        show_symbols = bool(
            self.marker_prefix_var.get() or self.cjk_allow_bracketed_var.get()
        )
        if show_symbols:
            self.symbol_inventory_frame.grid()
        else:
            self.symbol_inventory_frame.grid_remove()

