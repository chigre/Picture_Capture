"""Profile Wizard validation controls and structure-specific feedback tuning."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from tkinter import ttk


def build_validation_tab(self, tab: ttk.Frame, *, deps) -> None:
    ttk = deps["ttk"]
    tk = deps["tk"]
    tab.columnconfigure(0, weight=1)
    ttk.Label(
        tab, text="④ 多页测试后再确认",
        font=("TkDefaultFont", 12, "bold"),
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(
        tab,
        text="测试只处理代表页，不写 PDIC；PaddleOCR 强制重新识别，不复用旧 OCR 缓存。右侧一次显示一页，可左右翻页。",
        foreground="#666666", wraplength=self._wizard_left_width,
    ).grid(row=1, column=0, sticky="w", pady=(2, 8))

    bar = ttk.Frame(tab)
    bar.grid(row=2, column=0, sticky="ew")
    self.validate_button = ttk.Button(
        bar, text="测试当前 Profile", command=self.validate_profile,
    )
    self.validate_button.pack(side="left")
    self.validation_status_var = tk.StringVar(value="尚未测试")
    ttk.Label(
        bar, textvariable=self.validation_status_var,
        wraplength=max(260, self._wizard_left_width - 160),
    ).pack(side="left", padx=(10, 0))

    self.validation_diagnostic_var = tk.StringVar(
        value="测试方式：PaddleOCR（强制重新识别）｜尚未运行测试"
    )
    ttk.Label(
        tab, textvariable=self.validation_diagnostic_var,
        foreground="#555555", justify="left",
        wraplength=self._wizard_left_width,
    ).grid(row=3, column=0, sticky="ew", pady=(8, 0))

    feedback = ttk.LabelFrame(tab, text="结果是否合适？", padding=(8, 6))
    feedback.grid(row=4, column=0, sticky="ew", pady=(10, 0))
    feedback.columnconfigure(3, weight=1)
    ttk.Label(
        feedback,
        text="偏多会按当前词头类型收紧；偏少会放宽。调整后重新测试，直到右侧画线结果合适。",
        foreground="#666666", wraplength=self._wizard_left_width,
    ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 5))
    self.feedback_too_many_button = ttk.Button(
        feedback, text="偏多",
        command=lambda: self._apply_validation_feedback("too_many"),
        state="disabled",
    )
    self.feedback_too_many_button.grid(row=1, column=0, padx=(0, 4))
    self.feedback_good_button = ttk.Button(
        feedback, text="合适",
        command=lambda: self._apply_validation_feedback("good"),
        state="disabled",
    )
    self.feedback_good_button.grid(row=1, column=1, padx=4)
    self.feedback_too_few_button = ttk.Button(
        feedback, text="偏少",
        command=lambda: self._apply_validation_feedback("too_few"),
        state="disabled",
    )
    self.feedback_too_few_button.grid(row=1, column=2, padx=4)
    self.validation_feedback_var = tk.StringVar(value="")
    ttk.Label(
        feedback, textvariable=self.validation_feedback_var,
        wraplength=max(260, self._wizard_left_width - 260),
    ).grid(row=1, column=3, sticky="w", padx=(10, 0))




def apply_validation_feedback(self, result: str) -> None:
    if not self._validation_results:
        return
    if result == "good":
        self.validation_feedback_var.set("已确认当前结果合适，可保存 Profile。")
        self.validation_status_var.set("当前多页测试结果已确认合适")
        return

    old_level = max(-2, min(2, int(self.headword_tuning_level_var.get())))
    delta = 1 if result == "too_many" else -1
    new_level = max(-2, min(2, old_level + delta))
    self.headword_tuning_level_var.set(new_level)

    key = self._current_profile_key()
    if new_level != old_level:
        if key == "cjk_visual":
            self.headword_left_tolerance_var.set(max(
                0.0, round(float(self.headword_left_tolerance_var.get()) - 0.5 * delta, 2)
            ))
            self.headword_height_ratio_var.set(max(
                0.5, round(float(self.headword_height_ratio_var.get()) + 0.04 * delta, 2)
            ))
            self.headword_boldness_ratio_var.set(max(
                0.5, round(float(self.headword_boldness_ratio_var.get()) + 0.05 * delta, 2)
            ))
            self.headword_min_score_var.set(max(
                0.0, round(float(self.headword_min_score_var.get()) + 0.25 * delta, 2)
            ))
            if result == "too_many":
                # Keep real CJK big-character recall: tighten left-edge and
                # visible numeric thresholds, but do not silently enable the
                # extra strong-visual gate that previously dropped true heads.
                self.cjk_require_left_edge_var.set(True)
        elif key in {"latin_regular", "legacy_spanish_structured"}:
            self.headword_left_tolerance_var.set(max(
                0.0, round(float(self.headword_left_tolerance_var.get()) - 0.5 * delta, 2)
            ))
            self.headword_boldness_ratio_var.set(max(
                0.5, round(float(self.headword_boldness_ratio_var.get()) + 0.06 * delta, 2)
            ))
            self.headword_min_score_var.set(max(
                0.0, round(float(self.headword_min_score_var.get()) + 0.50 * delta, 2)
            ))
        elif key in {"numbered_prefix", "marker_prefixed"}:
            self.headword_left_tolerance_var.set(max(
                0.0, round(float(self.headword_left_tolerance_var.get()) - 0.4 * delta, 2)
            ))
        else:
            self.headword_left_tolerance_var.set(max(
                0.0, round(float(self.headword_left_tolerance_var.get()) - 0.4 * delta, 2)
            ))
            self.headword_min_score_var.set(max(
                0.0, round(float(self.headword_min_score_var.get()) + 0.35 * delta, 2)
            ))

    self._profile_revision += 1
    self._mark_validation_stale()
    self._refresh_headword_tuning_status()
    self._refresh_summary()
    direction = "收紧" if result == "too_many" else "放宽"
    if new_level == old_level:
        self.validation_feedback_var.set(
            f"已经达到自动{direction}上限（{new_level:+d}）；请在第③步直接勾选/取消不属于本词典的词头结构。"
        )
    else:
        self.validation_feedback_var.set(
            f"已按当前词头类型{direction}到 {new_level:+d} 级；请重新测试。"
        )
    self.validation_status_var.set("识别规则已调整，需要重新测试")
    self._set_feedback_buttons("disabled")



# Runs in the caller's Tk event-loop; no widget operations on background workers.

def set_feedback_buttons(self, state: str) -> None:
    if not hasattr(self, "feedback_too_many_button"):
        return
    for button in (
        self.feedback_too_many_button,
        self.feedback_good_button,
        self.feedback_too_few_button,
    ):
        button.configure(state=state)

def poll_validation_queue(self, *, queue_module) -> None:
    if self._validation_queue is None:
        return
    try:
        results = self._validation_queue.get_nowait()
    except queue_module.Empty:
        if self.winfo_exists() and self._validation_running:
            self.after(100, self._poll_validation_queue)
        return
    self._validation_queue = None
    self._finish_validation(results)

def set_validation_fit(self, mode: str, *, tk_module) -> None:
    self.validation_fit_mode = "width" if mode == "width" else "height"
    if self._validation_results:
        self._render_validation_result()
    try:
        self.right_canvas.yview_moveto(0.0)
    except tk_module.TclError:
        pass

def move_validation_preview(self, delta: int) -> None:
    if not self._validation_results:
        return
    self.validation_preview_slot = (
        int(self.validation_preview_slot) + int(delta)
    ) % len(self._validation_results)
    self._render_validation_result()
