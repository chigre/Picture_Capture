from __future__ import annotations

"""High-level page-layout semantics and lazy Project Profile UI extension.

Indentation polarity is a *page-template* property, not a subtype of CJK
headwords.  The helpers remain independent from ``profile_setup`` so low-level
layout inference can read the explicit user meaning (词头缩进 / 正文缩进) without
creating a processing/profile_setup circular dependency.

The historical Boolean ``profile_cjk_brackets_in_body`` remains only a
backward-compatible storage bit after semantics version 2:
* version < 2: indentation type defaults to 词头缩进;
* after the user explicitly saves the new choice, version 2 stores
  词头缩进(False) / 正文缩进(True).

The Project Profile also mirrors the existing ordinary-layout policy settings.
There is still only one source of truth: ``ordinary_auto_layout`` plus its seven
per-field switches.  The page-template step is simply the correct user-facing
place to edit them.
"""

import tkinter as tk
from tkinter import ttk
from typing import Any

from .models import AppSettings


INDENT_TYPE_CHOICES = ("词头缩进", "正文缩进")
INDENT_SEMANTICS_VERSION = 2

AUTO_LAYOUT_FIELDS: tuple[tuple[str, str], ...] = (
    ("分栏数", "ordinary_auto_columns"),
    ("正文起始Y", "ordinary_auto_start_y"),
    ("首栏X", "ordinary_auto_manual_x"),
    ("单栏宽", "ordinary_auto_column_width"),
    ("栏间空", "ordinary_auto_gutter"),
    ("普通字/行高", "ordinary_auto_character_height"),
    ("行间参数", "ordinary_auto_row_padding"),
)


def _indent_semantics_saved(settings: AppSettings) -> bool:
    return int(getattr(settings, "profile_parser_controls_version", 0) or 0) >= INDENT_SEMANTICS_VERSION


def indent_type_label(settings: AppSettings) -> str:
    if not _indent_semantics_saved(settings):
        return "词头缩进"
    return (
        "正文缩进"
        if bool(getattr(settings, "profile_cjk_brackets_in_body", False))
        else "词头缩进"
    )


def apply_indent_type_label(settings: AppSettings, label: str) -> None:
    settings.profile_cjk_brackets_in_body = str(label) == "正文缩进"
    settings.profile_parser_controls_version = max(
        INDENT_SEMANTICS_VERSION,
        int(getattr(settings, "profile_parser_controls_version", 0) or 0),
    )


def build_project_profile_wizard(base_class: type[Any]) -> type[Any]:
    """Return the page-layout-aware wizard subclass without importing profile_setup."""

    class ProjectProfileWizard(base_class):
        """Project Profile with explicit indentation and per-page layout policy."""

        def _build_vars(self) -> None:
            super()._build_vars()
            self.cjk_indent_type_var = tk.StringVar(
                value=indent_type_label(self.working)
            )
            self.layout_auto_var = tk.BooleanVar(
                value=bool(getattr(self.working, "ordinary_auto_layout", True))
            )
            self.layout_auto_field_vars: dict[str, tk.BooleanVar] = {
                field: tk.BooleanVar(
                    value=bool(getattr(self.working, field, False))
                )
                for _label, field in AUTO_LAYOUT_FIELDS
            }
            self._layout_auto_widgets: list[ttk.Checkbutton] = []

        def _build_template_tab(self, tab: ttk.Frame) -> None:
            super()._build_template_tab(tab)

            indent = ttk.LabelFrame(tab, text="缩进版式", padding=(9, 7))
            indent.grid(row=4, column=0, sticky="ew", pady=(10, 0))
            indent.columnconfigure(1, weight=1)
            ttk.Label(indent, text="词条与正文：").grid(
                row=0, column=0, sticky="e", padx=(0, 8), pady=3
            )
            self.cjk_indent_type_combo = ttk.Combobox(
                indent,
                textvariable=self.cjk_indent_type_var,
                values=INDENT_TYPE_CHOICES,
                state="readonly",
                width=12,
            )
            self.cjk_indent_type_combo.grid(row=0, column=1, sticky="w", pady=3)
            ttk.Label(
                indent,
                text=(
                    "这是整本词典的页面排版语义，与词头是大字、【】、编号或普通文字无关。\n"
                    "词头缩进＝entry 比正文更靠栏内；正文缩进＝正文比 entry 更靠栏内。"
                ),
                foreground="#666666",
                wraplength=max(180, getattr(self, "_wizard_content_width", 520) - 30),
                justify="left",
            ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 0))
            self.cjk_indent_type_combo.bind(
                "<<ComboboxSelected>>", self._indent_type_changed,
            )

            adaptive = ttk.LabelFrame(tab, text="逐页版面适配", padding=(9, 7))
            adaptive.grid(row=5, column=0, sticky="ew", pady=(10, 0))
            adaptive.columnconfigure(0, weight=1)
            ttk.Checkbutton(
                adaptive,
                text="使用自动版面参数（每页独立检测）",
                variable=self.layout_auto_var,
                command=self._layout_policy_changed,
            ).grid(row=0, column=0, columnspan=4, sticky="w")
            ttk.Label(
                adaptive,
                text=(
                    "开启后只把下方勾选字段替换为当前页检测值；未勾选字段继续使用 Project Profile 的固定值，"
                    "且本页结果不会传给下一页。缩进 family 仍在每页局部栏坐标中测量，以适应扫描平移/弯曲。"
                ),
                foreground="#666666",
                wraplength=max(180, getattr(self, "_wizard_content_width", 520) - 30),
                justify="left",
            ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(3, 7))

            for index, (label, field) in enumerate(AUTO_LAYOUT_FIELDS):
                widget = ttk.Checkbutton(
                    adaptive,
                    text=label,
                    variable=self.layout_auto_field_vars[field],
                    command=self._layout_policy_changed,
                )
                widget.grid(
                    row=2 + index // 4,
                    column=index % 4,
                    sticky="w",
                    padx=(0, 10),
                    pady=2,
                )
                self._layout_auto_widgets.append(widget)
            self._refresh_layout_policy_controls()

        def _build_headword_tab(self, tab: ttk.Frame) -> None:
            super()._build_headword_tab(tab)
            frame = getattr(self, "cjk_specificity_frame", None)
            if frame is None:
                return
            # This legacy question used the same persisted bit before the page-
            # template meaning was made explicit. Hide the duplicate control;
            # indentation now belongs exclusively to step 2 (页面模板).
            for child in frame.winfo_children():
                try:
                    if child.cget("text") == "释义正文中也经常出现【括号词】":
                        child.grid_remove()
                except (tk.TclError, AttributeError):
                    continue

        def _refresh_layout_policy_controls(self) -> None:
            enabled = bool(self.layout_auto_var.get())
            for widget in getattr(self, "_layout_auto_widgets", []):
                widget.configure(state="normal" if enabled else "disabled")

        def _layout_policy_changed(self) -> None:
            self._refresh_layout_policy_controls()
            self.working.ordinary_auto_layout = bool(self.layout_auto_var.get())
            for _label, field in AUTO_LAYOUT_FIELDS:
                setattr(
                    self.working,
                    field,
                    bool(self.layout_auto_field_vars[field].get()),
                )
            self._profile_revision += 1
            self._mark_validation_stale()
            self._refresh_summary()
            if hasattr(self, "template_preview_frame"):
                self.after_idle(self._refresh_template_preview)

        def _indent_type_changed(self, _event=None) -> None:
            apply_indent_type_label(self.working, self.cjk_indent_type_var.get())
            # Keep the hidden legacy variable synchronized because the base
            # wizard still serializes that compatibility field.
            self.cjk_brackets_in_body_var.set(
                self.cjk_indent_type_var.get() == "正文缩进"
            )
            self._profile_revision += 1
            self._mark_validation_stale()
            self._refresh_summary()

        def _settings_from_ui(self) -> AppSettings:
            settings = super()._settings_from_ui()
            if hasattr(self, "cjk_indent_type_var"):
                apply_indent_type_label(settings, self.cjk_indent_type_var.get())
                self.cjk_brackets_in_body_var.set(
                    self.cjk_indent_type_var.get() == "正文缩进"
                )
            if hasattr(self, "layout_auto_var"):
                settings.ordinary_auto_layout = bool(self.layout_auto_var.get())
                for _label, field in AUTO_LAYOUT_FIELDS:
                    setattr(
                        settings,
                        field,
                        bool(self.layout_auto_field_vars[field].get()),
                    )
            return settings

    ProjectProfileWizard.__name__ = "ProjectProfileWizard"
    ProjectProfileWizard.__qualname__ = "ProjectProfileWizard"
    return ProjectProfileWizard
