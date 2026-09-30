from __future__ import annotations

"""High-level indentation semantics for the Project Profile UI.

The historical setting ``profile_cjk_brackets_in_body`` is retained as the
on-disk compatibility bit so existing projects need no migration.  The user no
longer sees that low-level question.  Instead the Project Profile exposes the
layout fact the detector actually needs:

* 词头缩进: entry blocks are farther inside the column than body text;
* 正文缩进: body text is farther inside the column than entry blocks.

Keeping this translation in one small adapter also prevents UI wording from
leaking into the image-analysis modules.
"""

import tkinter as tk
from tkinter import ttk

from .models import AppSettings
from .profile_setup import ProjectProfileWizard as _BaseProjectProfileWizard


INDENT_TYPE_CHOICES = ("词头缩进", "正文缩进")


def indent_type_label(settings: AppSettings) -> str:
    return (
        "正文缩进"
        if bool(getattr(settings, "profile_cjk_brackets_in_body", False))
        else "词头缩进"
    )


def apply_indent_type_label(settings: AppSettings, label: str) -> None:
    settings.profile_cjk_brackets_in_body = str(label) == "正文缩进"


class ProjectProfileWizard(_BaseProjectProfileWizard):
    """Project Profile with an explicit CJK indentation-polarity control."""

    def _build_vars(self) -> None:
        super()._build_vars()
        self.cjk_indent_type_var = tk.StringVar(
            value=indent_type_label(self.working)
        )

    def _build_headword_tab(self, tab: ttk.Frame) -> None:
        super()._build_headword_tab(tab)
        frame = getattr(self, "cjk_specificity_frame", None)
        if frame is None:
            return

        # Hide the historical implementation-detail question.  It used the same
        # persisted bit but asked whether bracket words occur in definitions,
        # which is not equivalent to indentation polarity and confused the
        # downstream model.
        for child in frame.winfo_children():
            try:
                if child.cget("text") == "释义正文中也经常出现【括号词】":
                    child.grid_remove()
            except (tk.TclError, AttributeError):
                continue

        ttk.Label(frame, text="缩进类型：").grid(
            row=1, column=0, sticky="e", pady=2
        )
        self.cjk_indent_type_combo = ttk.Combobox(
            frame,
            textvariable=self.cjk_indent_type_var,
            values=INDENT_TYPE_CHOICES,
            state="readonly",
            width=12,
        )
        self.cjk_indent_type_combo.grid(
            row=1, column=1, sticky="w", pady=2
        )
        ttk.Label(
            frame,
            text="词头缩进＝词头比正文更靠栏内；正文缩进＝正文比词头更靠栏内。",
            foreground="#666666",
            wraplength=max(180, self._wizard_content_width - 170),
            justify="left",
        ).grid(row=1, column=2, sticky="w", padx=(6, 0), pady=2)
        self.cjk_indent_type_combo.bind(
            "<<ComboboxSelected>>", self._indent_type_changed,
        )

    def _indent_type_changed(self, _event=None) -> None:
        apply_indent_type_label(self.working, self.cjk_indent_type_var.get())
        # Keep the base BooleanVar synchronized because _settings_from_ui in the
        # established wizard owns persistence of the compatibility field.
        self.cjk_brackets_in_body_var.set(
            self.cjk_indent_type_var.get() == "正文缩进"
        )
        self._profile_revision += 1
        self._mark_validation_stale()
        self._refresh_summary()

    def _settings_from_ui(self) -> AppSettings:
        if hasattr(self, "cjk_indent_type_var"):
            self.cjk_brackets_in_body_var.set(
                self.cjk_indent_type_var.get() == "正文缩进"
            )
        return super()._settings_from_ui()
