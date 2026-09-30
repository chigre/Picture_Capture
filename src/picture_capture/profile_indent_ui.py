from __future__ import annotations

"""High-level page-layout semantics and lazy Project Profile UI extension.

Indentation polarity is a *page-template* property, not a subtype of CJK
headwords.  The helpers remain independent from ``profile_setup`` so low-level
layout inference can read the explicit user meaning without creating a
processing/profile_setup circular dependency.

The historical ``profile_cjk_brackets_in_body`` storage slot is retained for
backward compatibility.  Project Profile indentation semantics v3 deliberately
uses all three JSON-compatible states of that slot:

* ``False`` -> 词头缩进;
* ``True``  -> 正文缩进;
* ``None``  -> 无明显缩进.

Projects saved before v3 used only the first two states and therefore migrate
losslessly.  ``无明显缩进`` means indentation must not be used as positive or
negative entry-role evidence; OCR, typography and explicit marker evidence can
still identify entries on the same physical lane as body text.

The Project Profile also mirrors the existing ordinary-layout policy settings.
There is still only one source of truth: ``ordinary_auto_layout`` plus its seven
per-field switches.  The page-template step is simply the correct user-facing
place to edit them.
"""

import tkinter as tk
from tkinter import ttk
from typing import Any

from .models import AppSettings


INDENT_TYPE_CHOICES = ("词头缩进", "正文缩进", "无明显缩进")
INDENT_SEMANTICS_VERSION = 3

AUTO_LAYOUT_FIELDS: tuple[tuple[str, str], ...] = (
    ("分栏数", "ordinary_auto_columns"),
    ("正文起始Y", "ordinary_auto_start_y"),
    ("首栏X", "ordinary_auto_manual_x"),
    ("单栏宽", "ordinary_auto_column_width"),
    ("栏间空", "ordinary_auto_gutter"),
    ("普通字/行高", "ordinary_auto_character_height"),
    ("行间空", "ordinary_auto_row_padding"),
)


def _indent_semantics_saved(settings: AppSettings) -> bool:
    return int(getattr(settings, "profile_parser_controls_version", 0) or 0) >= 2


def indent_type_label(settings: AppSettings) -> str:
    """Return the explicit page-template indentation semantics.

    v2 projects only ever persisted True/False and retain that meaning.  v3 may
    additionally persist ``None`` for pages where entry and body starts share
    the same lane.
    """
    if not _indent_semantics_saved(settings):
        return "词头缩进"
    raw = getattr(settings, "profile_cjk_brackets_in_body", False)
    version = int(getattr(settings, "profile_parser_controls_version", 0) or 0)
    if version >= INDENT_SEMANTICS_VERSION and raw is None:
        return "无明显缩进"
    return "正文缩进" if bool(raw) else "词头缩进"


def apply_indent_type_label(settings: AppSettings, label: str) -> None:
    normalized = str(label or "词头缩进")
    if normalized == "无明显缩进":
        # The historical field is intentionally tri-stated only from v3 onward.
        # JSON serializes this as null; older True/False projects remain intact.
        settings.profile_cjk_brackets_in_body = None  # type: ignore[assignment]
    else:
        settings.profile_cjk_brackets_in_body = normalized == "正文缩进"
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
                width=14,
            )
            self.cjk_indent_type_combo.grid(row=0, column=1, sticky="w", pady=3)
            ttk.Label(
                indent,
                text=(
                    "这是整本词典的页面排版语义，与词头是大字、【】、编号或普通文字无关。\n"
                    "词头缩进＝entry 比正文更靠栏内；正文缩进＝正文比 entry 更靠栏内；"
                    "无明显缩进＝两者基本同栏起点，不使用缩进方向判定词条。"
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
            label = self.cjk_indent_type_var.get()
            apply_indent_type_label(self.working, label)
            # Keep the hidden legacy Boolean variable synchronized for the base
            # wizard.  ``无明显缩进`` has no Boolean representation; our
            # _settings_from_ui override reapplies the tri-state *after* the base
            # serializer has run, so False here is only a harmless UI fallback.
            self.cjk_brackets_in_body_var.set(label == "正文缩进")
            self._profile_revision += 1
            self._mark_validation_stale()
            self._refresh_summary()

        def _settings_from_ui(self) -> AppSettings:
            settings = super()._settings_from_ui()
            if hasattr(self, "cjk_indent_type_var"):
                label = self.cjk_indent_type_var.get()
                apply_indent_type_label(settings, label)
                self.cjk_brackets_in_body_var.set(label == "正文缩进")
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

    # Step 4 is a separate concern from indentation/layout editing.  Compose the
    # multi-mode validation bench last so it can consume the fully extended
    # wizard while remaining independently testable.
    from .profile_validation_modes import build_validation_mode_wizard

    return build_validation_mode_wizard(ProjectProfileWizard)
