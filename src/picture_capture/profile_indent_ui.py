from __future__ import annotations

"""High-level indentation semantics for the Project Profile UI.

The historical Boolean ``profile_cjk_brackets_in_body`` is reused only as a
storage bit *after* parser/profile semantics version 2.  Older projects may have
set that Boolean for the unrelated question “do bracket words also occur inside
definitions”; interpreting it as indentation polarity would be unsafe.

Migration rule:
* version < 2: indentation type defaults to 词头缩进, regardless of the old bit;
* once the user explicitly chooses/saves an indentation type, version becomes 2
  and the bit stores 词头缩进(False) / 正文缩进(True).

Thus no old project is silently reinterpreted, while settings.json remains fully
backward-compatible without adding an unknown field to the slotted dataclass.
"""

import tkinter as tk
from tkinter import ttk

from .models import AppSettings
from .profile_setup import ProjectProfileWizard as _BaseProjectProfileWizard


INDENT_TYPE_CHOICES = ("词头缩进", "正文缩进")
INDENT_SEMANTICS_VERSION = 2


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

        # Hide the historical implementation-detail question. It is not the same
        # concept as indentation polarity and must no longer drive detection.
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
            wraplength=max(180, getattr(self, "_wizard_content_width", 520) - 170),
            justify="left",
        ).grid(row=1, column=2, sticky="w", padx=(6, 0), pady=2)
        self.cjk_indent_type_combo.bind(
            "<<ComboboxSelected>>", self._indent_type_changed,
        )

    def _indent_type_changed(self, _event=None) -> None:
        apply_indent_type_label(self.working, self.cjk_indent_type_var.get())
        self.cjk_brackets_in_body_var.set(
            self.cjk_indent_type_var.get() == "正文缩进"
        )
        self._profile_revision += 1
        self._mark_validation_stale()
        self._refresh_summary()

    def _settings_from_ui(self) -> AppSettings:
        # Let the established wizard populate every ordinary field first; then
        # upgrade the semantics version and persist the explicit indentation
        # choice so base code cannot reset the version to 1 afterward.
        settings = super()._settings_from_ui()
        if hasattr(self, "cjk_indent_type_var"):
            apply_indent_type_label(settings, self.cjk_indent_type_var.get())
            self.cjk_brackets_in_body_var.set(
                self.cjk_indent_type_var.get() == "正文缩进"
            )
        return settings
