"""Project Profile Wizard asynchronous representative-page layout analysis.

Revision guards and conditional auto-apply preserve prior wizard behavior.
"""
from __future__ import annotations


def analyze_representative_pages(self, auto_apply: bool = False, *, deps) -> None:
    queue = deps["queue"]
    threading = deps["threading"]
    Image = deps["Image"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    effective_page_settings = deps["effective_page_settings"]
    page_template_analysis_image = deps["page_template_analysis_image"]
    detect_layout_parameters = deps["detect_layout_parameters"]
    if self._closing or self._analysis_running or not self.sample_indices:
        return
    self._analysis_running = True
    self._analysis_revision_started = self._profile_revision
    self._analysis_auto_apply = bool(auto_apply)
    self.analyze_button.configure(state="disabled")
    self.analysis_suggestion_var.set("正在分析代表页版面…")
    settings = self._settings_from_ui()
    indices = list(self.sample_indices)
    paths = {index: self.project.images[index] for index in indices}
    result_queue: queue.Queue = queue.Queue(maxsize=1)
    self._analysis_queue = result_queue

    def worker() -> None:
        estimates = []
        errors: list[str] = []
        for index in indices:
            path = paths[index]
            try:
                with Image.open(path) as opened:
                    image = normalize_page_rgb(opened)
                page_settings = effective_page_settings(settings, image.size, index)
                analysis_image = page_template_analysis_image(image, page_settings, index)
                estimates.append(detect_layout_parameters(analysis_image, page_settings))
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        result_queue.put((estimates, errors))

    threading.Thread(target=worker, daemon=True).start()
    self.after(100, self._poll_analysis_queue)



def poll_analysis_queue(self, *, deps) -> None:
    queue = deps["queue"]
    if self._closing:
        self._analysis_queue = None
        return
    if self._analysis_queue is None:
        return
    try:
        estimates, errors = self._analysis_queue.get_nowait()
    except queue.Empty:
        if self.winfo_exists() and self._analysis_running:
            self.after(100, self._poll_analysis_queue)
        return
    self._analysis_queue = None
    self._finish_analysis(estimates, errors)



def finish_analysis(self, estimates, errors: list[str], *, deps) -> None:
    aggregate_layout_estimates = deps["aggregate_layout_estimates"]
    apply_profile_ink_height_suggestion = deps["apply_profile_ink_height_suggestion"]
    self._analysis_running = False
    self.analyze_button.configure(state="normal")
    if self._analysis_revision_started != self._profile_revision:
        self._analysis_suggestion = {}
        self._analysis_auto_apply = False
        self.analysis_suggestion_var.set(
            "分析期间 Profile 设置已改变；旧分析结果已丢弃，请重新分析代表页。"
        )
        self.apply_analysis_button.configure(state="disabled")
        return
    if not estimates:
        self.analysis_suggestion_var.set("代表页分析失败；可直接人工选择页面模板。")
        self.apply_analysis_button.configure(state="disabled")
        return
    aggregate, consistency = aggregate_layout_estimates(estimates, columns_policy="detect")
    height_note = apply_profile_ink_height_suggestion(aggregate, estimates)
    separator = "present" if sum(
        e.separator_x is not None for e in estimates
    ) > len(estimates) / 2 else "auto"
    self._analysis_suggestion = {
        **{name: int(value) for name, value in aggregate.items()},
        "separator": separator,
    }
    sep_text = "有中央分隔线" if separator == "present" else "分隔线待判"
    error_text = (f"；{len(errors)} 页未参与" if errors else "") + height_note
    self.analysis_suggestion_var.set(
        f"自动建议：{aggregate['columns']}栏 · {sep_text} · {consistency}{error_text}"
    )
    self.apply_analysis_button.configure(state="normal")
    total_samples = len(estimates) + len(errors)
    enough_for_auto = len(estimates) >= max(2, (total_samples + 1) // 2)
    if self._analysis_auto_apply and enough_for_auto:
        self.apply_analysis_suggestion()
        self.analysis_suggestion_var.set(
            f"已采用代表页建议：{aggregate['columns']}栏 · {sep_text} · {consistency}{error_text}；可直接修改。"
        )
    elif self._analysis_auto_apply and not enough_for_auto:
        self.analysis_suggestion_var.set(
            f"自动建议：{aggregate['columns']}栏 · {sep_text} · {consistency}{error_text}；"
            "成功样本不足，未自动应用，请检查代表页后手动决定。"
        )
    self._analysis_auto_apply = False



def apply_analysis_suggestion(self, *, deps) -> None:
    _label_for_value = deps["_label_for_value"]
    SEPARATOR_LABEL_TO_VALUE = deps["SEPARATOR_LABEL_TO_VALUE"]
    if not self._analysis_suggestion:
        return
    self.columns_var.set(int(self._analysis_suggestion.get("columns", self.columns_var.get())))
    self.working.column_start_offsets = [0] * max(1, int(self.columns_var.get()))
    self.selected_column_index = min(
        self._selected_column_index(), max(0, int(self.columns_var.get()) - 1)
    )
    self._refresh_column_adjust_status()
    old_character_height = max(1, int(self.working.character_height))
    body_indent_was_auto = int(self.working.body_indent) == old_character_height
    horizontal_tolerance_was_auto = (
        int(self.working.horizontal_tolerance)
        == max(1, round(old_character_height / 2.0))
    )
    for name in (
        "start_y", "bottom_y", "manual_x", "column_width", "gutter",
        "character_height", "row_padding",
    ):
        if name in self._analysis_suggestion:
            setattr(self.working, name, int(self._analysis_suggestion[name]))
    if "character_height" in self._analysis_suggestion:
        new_character_height = max(1, int(self.working.character_height))
        if body_indent_was_auto:
            self.working.body_indent = new_character_height
        if horizontal_tolerance_was_auto:
            self.working.horizontal_tolerance = max(
                1, round(new_character_height / 2.0)
            )
    separator_value = str(self._analysis_suggestion.get("separator", "auto"))
    self.separator_var.set(_label_for_value(
        SEPARATOR_LABEL_TO_VALUE, separator_value, "自动判断",
    ))

