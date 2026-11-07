"""Profile Wizard forced multi-page OCR verification; Tk UI only in callbacks."""
from __future__ import annotations


def validate_profile(self, *, deps) -> None:
    tk = deps["tk"]
    ttk = deps["ttk"]
    Path = deps["Path"]
    Image = deps["Image"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    headword_filter_rules_path = deps["headword_filter_rules_path"]
    HEADWORD_FILTER_RULES_FILENAME = deps["HEADWORD_FILTER_RULES_FILENAME"]
    ocr_cache_root = deps["ocr_cache_root"]
    detect_entries = deps["detect_entries"]
    ProjectProfileWizard = deps["ProjectProfileWizard"]
    if self._closing or self._validation_running:
        return
    if self.parent._batch_active:
        self.validation_status_var.set("批量任务运行中；结束或停止后再测试 Project Profile。")
        return
    if self.parent._ui_worker_key_active("profile-validation"):
        self.validation_status_var.set("上一轮 Profile 测试仍在安全结束，请稍后重试。")
        return
    settings = self._settings_from_ui()
    # Project Profile validates the normal OCR-based workflow even when an
    # old project last saved "普通画线" as its active detection method.
    settings.detection_method = "paddleocr"
    settings.paddle_use_paddleocr = True
    indices = list(self.sample_indices)
    if not indices:
        return
    project = self.project
    project_root = Path(project.root)
    paths = {index: project.images[index] for index in indices}
    self.update_idletasks()
    frame_width = int(self.validation_frame.winfo_width())
    preview_width = max(
        480,
        (frame_width - 20) if frame_width > 100
        else (int(self._wizard_image_width) - 8),
    )
    self._validation_running = True
    self._validation_revision_started = self._profile_revision
    self._validation_stop_event.clear()
    stop_event = self._validation_stop_event
    self.validate_button.configure(state="disabled")
    self.validation_status_var.set("正在强制重新识别并测试代表页…")
    self._validation_results = []
    self.validation_preview_slot = 0
    self.validation_caption_var.set("")
    self.validation_diagnostic_var.set(
        "测试方式：PaddleOCR（强制重新识别）｜正在生成逐栏诊断…"
    )
    self.validation_prev_button.configure(state="disabled")
    self.validation_next_button.configure(state="disabled")
    self._set_feedback_buttons("disabled")
    self.validation_feedback_var.set("")
    for child in self.validation_frame.winfo_children():
        child.destroy()
    ttk.Label(self.validation_frame, text="正在生成测试结果…").grid(
        row=0, column=0, sticky="n", pady=30,
    )
    filter_path = headword_filter_rules_path(project_root, HEADWORD_FILTER_RULES_FILENAME)

    def worker():
        results = []
        for index in indices:
            if stop_event.is_set():
                break
            path = paths[index]
            try:
                with Image.open(path) as opened:
                    image = normalize_page_rgb(opened)
                cache_path = (
                    ocr_cache_root(project_root) / f"{path.stem}.json"
                    if settings.detection_method == "paddleocr" else None
                )
                entries, geometry = detect_entries(
                    image, settings,
                    paddle_cache_path=cache_path,
                    force_paddle_refresh=True,
                    paddle_filter_rules_path=filter_path,
                    profile_page_index=index,
                )
                preview = ProjectProfileWizard._marker_preview(
                    image, entries, geometry, settings, index, preview_width,
                )
                coverage = ProjectProfileWizard._validation_coverage_summary(
                    cache_path, entries, geometry, settings,
                )
                results.append((
                    index, path.name, len(entries), len(geometry.column_starts),
                    preview, coverage, None,
                ))
            except Exception as exc:
                results.append((index, path.name, 0, 0, None, "", str(exc)))
            if stop_event.is_set():
                break
        return results

    def done(results) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self._validation_running = False
        if stop_event.is_set():
            if self._validation_close_requested:
                self.after_idle(self.destroy)
                return
            self.validation_status_var.set("Profile 测试已安全停止。")
            self.validate_button.configure(state="normal")
            return
        self._finish_validation(results)

    def failed(exc, detail) -> None:
        if detail:
            print(detail)
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self._validation_running = False
        if self._validation_close_requested:
            self.after_idle(self.destroy)
            return
        self.validate_button.configure(state="normal")
        self.validation_status_var.set(f"Profile 测试失败：{exc}")

    self.parent._start_ui_worker(
        "profile-validation", worker, done, failed, wait_on_close=True,
    )

