from __future__ import annotations

"""Multi-mode Project Profile validation UI.

Step 4 of Project Profile is a user-facing validation bench, not an automatic
model selector.  The user can run ordinary, OCR and combined drawing on the
same representative pages, inspect each result page-by-page, switch among saved
mode results without rerunning them, and then choose which tested mode should
become the project's default detection method.

The implementation deliberately wraps the existing wizard instead of importing
``profile_setup`` so it composes with the page-template/indent extension without
creating another profile/processing import cycle.
"""

from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any

from PIL import Image


VALIDATION_MODES: tuple[tuple[str, str], ...] = (
    ("left_edge", "普通画线"),
    ("paddleocr", "OCR画线"),
    ("combined", "融合画线"),
)
VALIDATION_MODE_LABELS = dict(VALIDATION_MODES)
_VALIDATION_MODE_KEYS = frozenset(VALIDATION_MODE_LABELS)


def normalize_validation_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in _VALIDATION_MODE_KEYS else "paddleocr"


def mode_uses_ocr(mode: str) -> bool:
    return normalize_validation_mode(mode) in {"paddleocr", "combined"}


def _understanding_summary(understanding: Any) -> str:
    """Return a compact, user-facing Page Understanding summary."""
    layout = understanding.layout
    columns = len(getattr(layout, "columns", []) or [])
    line_height = max(
        1.0, float(getattr(layout, "ordinary_line_height", 0.0) or 0.0)
    )
    indent_type = str(getattr(layout, "indent_type", "") or "")
    indent_label = {
        "body": "正文缩进",
        "none": "无明显缩进",
        "headword": "词头缩进",
    }.get(indent_type, "词头缩进")
    physical = bool(getattr(understanding, "physical_reliable", False))
    semantic = bool(getattr(understanding, "semantic_reliable", False))
    role_model = str(
        getattr(understanding, "role_model", "generic") or "generic"
    )
    display = bool(getattr(layout, "has_display_heads", False))
    semantic_count = len(getattr(understanding, "semantic_entries", []) or [])
    generic_body = bool(
        getattr(understanding, "generic_body_indent_reliable", False)
    )
    symbol_evidence = getattr(understanding, "symbol_evidence", None)
    entry_markers = len(
        getattr(symbol_evidence, "entry_markers", []) or []
    ) if symbol_evidence is not None else 0
    bracket_openers = len(
        getattr(symbol_evidence, "bracket_openers", []) or []
    ) if symbol_evidence is not None else 0

    if role_model == "cjk":
        if indent_type == "none":
            role_text = "CJK词条结构：缩进不参与判定"
        else:
            role_text = (
                f"CJK词条结构：{'已建立' if semantic else '未稳定'}"
                f"（版式词条 {semantic_count}）"
            )
        display_text = f"大字头：{'有' if display else '未检出'}"
    else:
        if indent_type == "none":
            role_text = "通用版式角色：不使用缩进方向判定"
        else:
            role_text = (
                "通用版式角色："
                + ("正文缩进 lane 已建立" if generic_body else "仅使用物理页面结构")
            )
        display_text = ""

    pieces = [
        f"页面理解：{'可靠' if physical else '未稳定'}",
        f"{columns} 栏",
        f"普通字/行高≈{line_height:.0f}px",
        f"缩进版式：{indent_label}",
        role_text,
    ]
    if display_text:
        pieces.append(display_text)
    if entry_markers or bracket_openers:
        pieces.append(
            f"符号样本：入口 {entry_markers} / 括号 {bracket_openers}"
        )
    return " ｜ ".join(pieces)


def build_validation_mode_wizard(base_class: type[Any]) -> type[Any]:
    """Wrap a ProjectProfileWizard with explicit multi-mode validation."""

    class ProjectProfileWizard(base_class):
        def _build_vars(self) -> None:
            super()._build_vars()
            initial = normalize_validation_mode(
                getattr(self.working, "detection_method", "paddleocr")
            )
            self.validation_default_method_var = tk.StringVar(value=initial)
            self._active_validation_mode = initial
            self._validation_results_by_mode: dict[str, list[tuple]] = {}
            self._validation_understanding_by_mode: dict[str, dict[int, str]] = {}
            self._validation_mode_revision: dict[str, int] = {}
            self._validation_mode_status_vars: dict[str, tk.StringVar] = {}
            self._validation_mode_buttons: dict[str, ttk.Button] = {}
            self._validation_mode_view_buttons: dict[str, ttk.Button] = {}

        def _build_validation_tab(self, tab: ttk.Frame) -> None:
            tab.columnconfigure(0, weight=1)
            ttk.Label(
                tab,
                text="④ 多模式测试后再确认",
                font=("TkDefaultFont", 12, "bold"),
            ).grid(row=0, column=0, sticky="w")
            ttk.Label(
                tab,
                text=(
                    "在同一组代表页上分别试跑普通画线、OCR画线和融合画线。"
                    "测试不写 PDIC；OCR相关模式会强制重新识别。"
                    "请逐页查看右侧结果，再由你决定本项目默认使用哪一种模式。"
                ),
                foreground="#666666",
                wraplength=self._wizard_left_width,
                justify="left",
            ).grid(row=1, column=0, sticky="w", pady=(2, 8))

            understanding = ttk.LabelFrame(
                tab, text="页面理解（Page Understanding）", padding=(8, 6),
            )
            understanding.grid(row=2, column=0, sticky="ew")
            understanding.columnconfigure(0, weight=1)
            self.validation_understanding_var = tk.StringVar(
                value="尚未测试；运行任一模式后显示当前预览页的页面理解结果。"
            )
            ttk.Label(
                understanding,
                textvariable=self.validation_understanding_var,
                foreground="#555555",
                wraplength=self._wizard_left_width,
                justify="left",
            ).grid(row=0, column=0, sticky="w")

            tests = ttk.LabelFrame(tab, text="分别测试", padding=(8, 7))
            tests.grid(row=3, column=0, sticky="ew", pady=(10, 0))
            tests.columnconfigure(2, weight=1)
            for row, (mode, label) in enumerate(VALIDATION_MODES):
                button = ttk.Button(
                    tests,
                    text=f"测试 {label}",
                    command=lambda value=mode: self.validate_profile(value),
                )
                button.grid(row=row, column=0, sticky="w", pady=3)
                view = ttk.Button(
                    tests,
                    text="查看结果",
                    command=lambda value=mode: self._show_validation_mode(value),
                    state="disabled",
                )
                view.grid(row=row, column=1, sticky="w", padx=(6, 0), pady=3)
                status = tk.StringVar(value="尚未测试")
                ttk.Label(
                    tests,
                    textvariable=status,
                    wraplength=max(220, self._wizard_left_width - 225),
                ).grid(row=row, column=2, sticky="w", padx=(10, 0), pady=3)
                self._validation_mode_buttons[mode] = button
                self._validation_mode_view_buttons[mode] = view
                self._validation_mode_status_vars[mode] = status

            default_box = ttk.LabelFrame(
                tab, text="项目默认画线方式", padding=(8, 7),
            )
            default_box.grid(row=4, column=0, sticky="ew", pady=(10, 0))
            ttk.Label(
                default_box,
                text="软件不会替你评选“最佳模式”；请根据上面的真实试跑结果自行选择。",
                foreground="#666666",
                wraplength=self._wizard_left_width,
            ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 5))
            for column, (mode, label) in enumerate(VALIDATION_MODES):
                ttk.Radiobutton(
                    default_box,
                    text=label,
                    variable=self.validation_default_method_var,
                    value=mode,
                    command=self._validation_default_mode_changed,
                ).grid(row=1, column=column, sticky="w", padx=(0, 12))

            self.validation_status_var = tk.StringVar(value="尚未完成默认模式验证")
            ttk.Label(
                tab,
                textvariable=self.validation_status_var,
                wraplength=self._wizard_left_width,
            ).grid(row=5, column=0, sticky="w", pady=(9, 0))

            self.validation_diagnostic_var = tk.StringVar(value="尚无测试结果")
            ttk.Label(
                tab,
                textvariable=self.validation_diagnostic_var,
                foreground="#555555",
                justify="left",
                wraplength=self._wizard_left_width,
            ).grid(row=6, column=0, sticky="ew", pady=(7, 0))

            # Keep the existing feedback tool, but make it explicit that its
            # automatic tuning is intended for OCR-bearing modes.  Ordinary
            # Page Understanding/layout issues should be corrected in steps 2/3.
            feedback = ttk.LabelFrame(
                tab, text="当前查看模式的结果是否合适？", padding=(8, 6),
            )
            feedback.grid(row=7, column=0, sticky="ew", pady=(10, 0))
            feedback.columnconfigure(3, weight=1)
            ttk.Label(
                feedback,
                text=(
                    "OCR/融合模式可用“偏多/偏少”微调词头规则；"
                    "普通画线若不合适，请优先回到第②/③步修改版面或词头结构。"
                ),
                foreground="#666666",
                wraplength=self._wizard_left_width,
            ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 5))
            self.feedback_too_many_button = ttk.Button(
                feedback,
                text="偏多",
                command=lambda: self._apply_validation_feedback("too_many"),
                state="disabled",
            )
            self.feedback_too_many_button.grid(row=1, column=0, padx=(0, 4))
            self.feedback_good_button = ttk.Button(
                feedback,
                text="合适",
                command=lambda: self._apply_validation_feedback("good"),
                state="disabled",
            )
            self.feedback_good_button.grid(row=1, column=1, padx=4)
            self.feedback_too_few_button = ttk.Button(
                feedback,
                text="偏少",
                command=lambda: self._apply_validation_feedback("too_few"),
                state="disabled",
            )
            self.feedback_too_few_button.grid(row=1, column=2, padx=4)
            self.validation_feedback_var = tk.StringVar(value="")
            ttk.Label(
                feedback,
                textvariable=self.validation_feedback_var,
                wraplength=max(220, self._wizard_left_width - 250),
            ).grid(row=1, column=3, sticky="w", padx=(10, 0))

        def _show_right_image_page(self, index: int) -> None:
            super()._show_right_image_page(index)
            if int(index) == 3 and hasattr(self, "right_heading_var"):
                self.right_heading_var.set("多模式 / 多页测试结果")

        def _settings_from_ui(self):
            settings = super()._settings_from_ui()
            if hasattr(self, "validation_default_method_var"):
                settings.detection_method = normalize_validation_mode(
                    self.validation_default_method_var.get()
                )
            return settings

        def _validation_default_mode_changed(self) -> None:
            mode = normalize_validation_mode(self.validation_default_method_var.get())
            self.working.detection_method = mode
            self._sync_default_validation_state()
            self._refresh_summary()
            if self._validation_results_by_mode.get(mode):
                self._show_validation_mode(mode)

        def _sync_default_validation_state(self) -> None:
            mode = normalize_validation_mode(self.validation_default_method_var.get())
            revision = self._validation_mode_revision.get(mode, -1)
            results = self._validation_results_by_mode.get(mode, [])
            valid = bool(results) and revision == self._profile_revision and all(
                row[4] is not None for row in results
            )
            if valid:
                pages = [row[1] for row in results if row[4] is not None]
                self.working.profile_last_validated_pages = list(pages)
                self.validation_status_var.set(
                    f"默认模式：{VALIDATION_MODE_LABELS[mode]} · 已验证 {len(pages)} 个代表页"
                )
            else:
                self.working.profile_last_validated_pages = []
                self.validation_status_var.set(
                    f"默认模式：{VALIDATION_MODE_LABELS[mode]} · 尚未按当前 Profile 完整验证"
                )

        def _mark_validation_stale(self) -> None:
            super()._mark_validation_stale()
            if not hasattr(self, "_validation_mode_status_vars"):
                return
            for mode, status in self._validation_mode_status_vars.items():
                if mode in self._validation_results_by_mode:
                    status.set("设置已修改；旧结果仅供参考，请重新测试")
            if hasattr(self, "validation_understanding_var"):
                self.validation_understanding_var.set(
                    "Profile 设置已修改；页面理解需要重新测试。"
                )

        def _set_mode_buttons(self, state: str) -> None:
            for button in getattr(self, "_validation_mode_buttons", {}).values():
                button.configure(state=state)

        def _show_validation_mode(self, mode: str) -> None:
            mode = normalize_validation_mode(mode)
            results = self._validation_results_by_mode.get(mode, [])
            if not results:
                return
            self._active_validation_mode = mode
            self._validation_results = list(results)
            self.validation_preview_slot = min(
                int(self.validation_preview_slot), len(results) - 1
            )
            if mode_uses_ocr(mode):
                revision_ok = self._validation_mode_revision.get(mode) == self._profile_revision
                self._set_feedback_buttons("normal" if revision_ok else "disabled")
                if revision_ok:
                    self.validation_feedback_var.set("")
            else:
                self._set_feedback_buttons("disabled")
                self.validation_feedback_var.set(
                    "普通画线只展示结果；若不合适，请调整第②页面模板或第③词头结构后重测。"
                )
            self._render_validation_result()

        def validate_profile(self, mode: str | None = None) -> None:
            if self._closing or self._validation_running:
                return
            mode = normalize_validation_mode(
                mode or self.validation_default_method_var.get()
            )
            label = VALIDATION_MODE_LABELS[mode]
            if self.parent._batch_active:
                self.validation_status_var.set(
                    "批量任务运行中；结束或停止后再测试 Project Profile。"
                )
                return
            if self.parent._ui_worker_key_active("profile-validation"):
                self.validation_status_var.set(
                    "上一轮 Profile 测试仍在安全结束，请稍后重试。"
                )
                return

            settings = self._settings_from_ui()
            settings.detection_method = mode
            if mode_uses_ocr(mode):
                settings.paddle_use_paddleocr = True
            indices = list(self.sample_indices)
            if not indices:
                return

            from .image_utils import normalize_page_rgb
            from .page_sections import read_page_sections
            from .page_understanding import understand_page
            from .paddle_headwords import HEADWORD_FILTER_RULES_FILENAME
            from .processing import detect_entries
            from .project_storage import (
                headword_filter_rules_path,
                ocr_cache_root,
            )

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
            self._active_validation_mode = mode
            self._set_mode_buttons("disabled")
            self._validation_mode_status_vars[mode].set(
                f"正在测试 {label}…"
            )
            self.validation_status_var.set(
                f"正在用 {label} 测试 {len(indices)} 个代表页…"
            )
            self.validation_diagnostic_var.set(
                f"测试方式：{label}"
                + ("（OCR强制重新识别）" if mode_uses_ocr(mode) else "")
            )
            self.validation_understanding_var.set("正在恢复页面理解…")
            self._validation_results = []
            self.validation_preview_slot = 0
            self.validation_caption_var.set("")
            self.validation_prev_button.configure(state="disabled")
            self.validation_next_button.configure(state="disabled")
            self._set_feedback_buttons("disabled")
            self.validation_feedback_var.set("")
            for child in self.validation_frame.winfo_children():
                child.destroy()
            ttk.Label(
                self.validation_frame,
                text=f"正在生成 {label} 测试结果…",
            ).grid(row=0, column=0, sticky="n", pady=30)

            filter_path = headword_filter_rules_path(
                project_root, HEADWORD_FILTER_RULES_FILENAME,
            )

            def worker():
                results: list[tuple] = []
                understanding_summaries: dict[int, str] = {}
                for index in indices:
                    if stop_event.is_set():
                        break
                    path = paths[index]
                    try:
                        with Image.open(path) as opened:
                            image = normalize_page_rgb(opened)
                        sections = read_page_sections(path)
                        cache_path = (
                            ocr_cache_root(project_root) / f"{path.stem}.json"
                            if mode_uses_ocr(mode) else None
                        )
                        entries, geometry = detect_entries(
                            image,
                            settings,
                            paddle_cache_path=cache_path,
                            force_paddle_refresh=mode_uses_ocr(mode),
                            paddle_filter_rules_path=filter_path,
                            profile_page_index=index,
                            page_sections=sections,
                        )
                        preview = base_class._marker_preview(
                            image, entries, geometry, settings, index, preview_width,
                        )
                        understanding = understand_page(
                            image,
                            settings,
                            page_index=index,
                            page_sections=sections,
                        )
                        understanding_text = _understanding_summary(understanding)
                        understanding_summaries[index] = understanding_text
                        if mode_uses_ocr(mode):
                            coverage = base_class._validation_coverage_summary(
                                cache_path, entries, geometry, settings,
                            )
                            coverage = coverage.replace(
                                "测试方式：PaddleOCR（强制重新识别）",
                                f"测试方式：{label}（OCR强制重新识别）",
                                1,
                            )
                        else:
                            coverage = f"测试方式：{label}｜检出 {len(entries)} 个词条"
                        coverage = understanding_text + "\n" + coverage
                        results.append((
                            index,
                            path.name,
                            len(entries),
                            len(geometry.column_starts),
                            preview,
                            coverage,
                            None,
                        ))
                    except Exception as exc:
                        results.append((
                            index, path.name, 0, 0, None, "", str(exc)
                        ))
                    if stop_event.is_set():
                        break
                return results, understanding_summaries

            def done(payload) -> None:
                try:
                    if not self.winfo_exists():
                        return
                except tk.TclError:
                    return
                self._validation_running = False
                self._set_mode_buttons("normal")
                if stop_event.is_set():
                    if self._validation_close_requested:
                        self.after_idle(self.destroy)
                        return
                    self.validation_status_var.set("Profile 测试已安全停止。")
                    return
                results, summaries = payload
                self._finish_validation_mode(mode, results, summaries)

            def failed(exc, detail) -> None:
                if detail:
                    print(detail)
                try:
                    if not self.winfo_exists():
                        return
                except tk.TclError:
                    return
                self._validation_running = False
                self._set_mode_buttons("normal")
                if self._validation_close_requested:
                    self.after_idle(self.destroy)
                    return
                self._validation_mode_status_vars[mode].set(f"测试失败：{exc}")
                self.validation_status_var.set(f"{label} 测试失败：{exc}")

            self.parent._start_ui_worker(
                "profile-validation", worker, done, failed, wait_on_close=True,
            )

        def _finish_validation_mode(
            self,
            mode: str,
            results: list[tuple],
            understanding_summaries: dict[int, str],
        ) -> None:
            revision_changed = self._validation_revision_started != self._profile_revision
            self._validation_results_by_mode[mode] = list(results)
            self._validation_understanding_by_mode[mode] = dict(
                understanding_summaries
            )
            self._validation_results = list(results)
            self._active_validation_mode = mode
            self.validation_preview_slot = 0

            failures = sum(1 for row in results if row[4] is None)
            success = len(results) - failures
            counts = [int(row[2]) for row in results if row[4] is not None]
            count_text = (
                f"；每页检出 {min(counts)}–{max(counts)} 条"
                if counts else ""
            )
            if revision_changed:
                self._validation_mode_status_vars[mode].set(
                    "测试期间设置已改变；结果仅供参考，请重测"
                )
            elif failures:
                self._validation_mode_status_vars[mode].set(
                    f"{success}/{len(results)} 页成功{count_text}"
                )
            else:
                self._validation_mode_revision[mode] = self._profile_revision
                self._validation_mode_status_vars[mode].set(
                    f"{len(results)} 页完成{count_text}"
                )
            self._validation_mode_view_buttons[mode].configure(
                state="normal" if results else "disabled"
            )

            self._sync_default_validation_state()
            self._show_validation_mode(mode)

        def _move_validation_preview(self, delta: int) -> None:
            results = self._validation_results_by_mode.get(
                self._active_validation_mode, []
            )
            if not results:
                return
            self._validation_results = results
            self.validation_preview_slot = (
                int(self.validation_preview_slot) + int(delta)
            ) % len(results)
            self._render_validation_result()

        def _render_validation_result(self) -> None:
            results = self._validation_results_by_mode.get(
                self._active_validation_mode, []
            )
            self._validation_results = list(results)
            if not results:
                for child in self.validation_frame.winfo_children():
                    child.destroy()
                self._validation_photos.clear()
                label = VALIDATION_MODE_LABELS[self._active_validation_mode]
                self.validation_caption_var.set("")
                self.validation_diagnostic_var.set(f"{label}：尚无测试结果")
                self.validation_understanding_var.set(
                    "运行任一模式后显示当前预览页的页面理解结果。"
                )
                self.validation_prev_button.configure(state="disabled")
                self.validation_next_button.configure(state="disabled")
                return

            # Reuse the proven image rendering/fit code from the base wizard.
            super()._render_validation_result()
            self.validation_preview_slot %= len(results)
            index = int(results[self.validation_preview_slot][0])
            summaries = self._validation_understanding_by_mode.get(
                self._active_validation_mode, {}
            )
            self.validation_understanding_var.set(
                summaries.get(index, "当前页页面理解摘要未生成。")
            )
            label = VALIDATION_MODE_LABELS[self._active_validation_mode]
            self.validation_caption_var.set(
                f"{label} · {self.validation_caption_var.get()}"
            )

    ProjectProfileWizard.__name__ = "ProjectProfileWizard"
    ProjectProfileWizard.__qualname__ = "ProjectProfileWizard"
    return ProjectProfileWizard
