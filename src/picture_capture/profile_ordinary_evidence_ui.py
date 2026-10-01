from __future__ import annotations

"""Project Profile UI for OCR-independent universal ordinary evidence.

The existing settings remain the single source of truth.  This wrapper moves the
user-facing controls to the headword-structure / symbol-evidence area where
their meaning is clear: sampled symbols and oversized heads are ordinary visual
entry evidence, not OCR settings.
"""

import tkinter as tk
from tkinter import ttk
from typing import Any


def build_ordinary_evidence_profile_wizard(base_class: type[Any]) -> type[Any]:
    class ProjectProfileWizard(base_class):
        def _build_headword_tab(self, tab: ttk.Frame) -> None:
            super()._build_headword_tab(tab)

            inventory = getattr(self, "symbol_inventory_frame", None)
            host = inventory or getattr(self, "cjk_specificity_frame", None)
            if host is None:
                return

            # Hide the older template-only sub-panel.  The same settings/actions
            # are exposed below together with the large-head detector so users
            # see one coherent ordinary-mode evidence section.
            if inventory is not None:
                for child in inventory.winfo_children():
                    try:
                        if child.cget("text") == "本词典视觉标记样本":
                            child.grid_remove()
                    except (tk.TclError, AttributeError):
                        continue

            rows: list[int] = []
            for child in host.winfo_children():
                try:
                    info = child.grid_info()
                    if info:
                        rows.append(int(info.get("row", 0)))
                except (tk.TclError, TypeError, ValueError):
                    continue
            row = (max(rows) + 1) if rows else 0

            panel = ttk.LabelFrame(
                host,
                text="普通画线：视觉词头证据（OCR-independent）",
                padding=7,
            )
            panel.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(9, 0))
            panel.columnconfigure(1, weight=1)
            self.ordinary_visual_evidence_frame = panel

            ttk.Label(
                panel,
                text=(
                    "通用普通模式会把三类证据做 OR 融合：缩进 Layout role、特定符号视觉样本、"
                    "大字头。无明显缩进的词典也可以只靠后两类画线。"
                ),
                foreground="#555555",
                wraplength=max(220, getattr(self, "_wizard_content_width", 520) - 45),
                justify="left",
            ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

            ttk.Checkbutton(
                panel,
                text="启用大字头 detector",
                variable=self.cjk_allow_single_var,
                command=self._headword_specificity_changed,
            ).grid(row=1, column=0, columnspan=3, sticky="w", pady=2)
            ttk.Label(
                panel,
                text="按字号/墨迹几何识别 oversized display head；不要求缩进，也不读取 OCR 文字。",
                foreground="#666666",
                wraplength=max(220, getattr(self, "_wizard_content_width", 520) - 45),
                justify="left",
            ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 5))

            ttk.Checkbutton(
                panel,
                text="启用特定符号视觉样本",
                variable=self.symbol_visual_rescue_var,
                command=self._headword_specificity_changed,
            ).grid(row=3, column=0, columnspan=3, sticky="w", pady=2)
            ttk.Label(
                panel,
                text=(
                    "用于【、〔、○、◆等词典特定入口结构。可从不同页面采多个样本；普通画线只在"
                    "每个 Layout 行首的小窗口匹配，正文中间的相似符号不会触发。"
                ),
                foreground="#666666",
                wraplength=max(220, getattr(self, "_wizard_content_width", 520) - 45),
                justify="left",
            ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 5))

            ttk.Label(panel, textvariable=self.visual_marker_sample_count_var).grid(
                row=5, column=0, columnspan=3, sticky="w", pady=(2, 3)
            )
            buttons = ttk.Frame(panel)
            buttons.grid(row=6, column=0, columnspan=3, sticky="w")
            ttk.Button(
                buttons,
                text="从页面采样…",
                command=self._capture_visual_marker_sample,
            ).pack(side="left")
            ttk.Button(
                buttons,
                text="查看/删除样本",
                command=self._show_visual_marker_samples,
            ).pack(side="left", padx=(6, 0))

            ttk.Label(panel, text="匹配阈值：").grid(
                row=7, column=0, sticky="e", padx=(0, 6), pady=(6, 2)
            )
            ttk.Spinbox(
                panel,
                from_=0.35,
                to=0.95,
                increment=0.01,
                textvariable=self.symbol_template_threshold_var,
                width=7,
                command=self._headword_specificity_changed,
            ).grid(row=7, column=1, sticky="w", pady=(6, 2))
            ttk.Label(
                panel,
                text="多个样本按最佳匹配（max/OR）使用，不要求一个候选同时匹配所有样本。",
                foreground="#666666",
                wraplength=max(220, getattr(self, "_wizard_content_width", 520) - 45),
                justify="left",
            ).grid(row=8, column=0, columnspan=3, sticky="w", pady=(2, 0))

    ProjectProfileWizard.__name__ = "ProjectProfileWizard"
    ProjectProfileWizard.__qualname__ = "ProjectProfileWizard"
    return ProjectProfileWizard
