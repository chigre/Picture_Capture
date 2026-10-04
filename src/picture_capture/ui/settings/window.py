from __future__ import annotations

from typing import Any
import tkinter as tk
from tkinter import ttk

from ...appearance import appearance_palette


def configure_settings_appearance_styles(dialog: Any) -> None:
    style = ttk.Style(dialog)
    base = appearance_palette(dialog.parent.appearance_mode)
    if dialog.parent.appearance_mode == "dark":
        selected_bg = base["surface"]
        active_bg = base["button_hover"]
        idle_bg = base["surface_alt"]
        selected_fg = base["text"]
        idle_fg = base["muted"]
    else:
        selected_bg = str(style.lookup("TFrame", "background") or "#f6f7f9")
        active_bg = "#f1f3f6"
        idle_bg = "#e6eaf0"
        selected_fg = "#111827"
        idle_fg = "#4b5563"
    style.configure(
        "PC.Settings.TNotebook",
        background=selected_bg,
        borderwidth=0,
        tabmargins=(0, 2, 0, 0),
    )
    style.configure(
        "PC.Settings.TNotebook.Tab",
        padding=(13, 7),
        borderwidth=1,
        relief="raised",
        background=idle_bg,
        foreground=idle_fg,
    )
    style.map(
        "PC.Settings.TNotebook.Tab",
        background=[
            ("selected", selected_bg),
            ("active", active_bg),
            ("!selected", idle_bg),
        ],
        foreground=[
            ("selected", selected_fg),
            ("active", selected_fg),
            ("!selected", idle_fg),
        ],
        relief=[("selected", "sunken"), ("!selected", "raised")],
    )


def refresh_appearance(dialog: Any) -> None:
    """Apply the global appearance without touching unsaved setting values."""
    dialog._configure_settings_appearance_styles()
    dialog.parent._apply_current_appearance(dialog)
    dialog._schedule_settings_help_image_render()


def select_tab(dialog: Any, key: str | None) -> None:
    """Select a requested settings task when reusing the modeless window."""
    if not hasattr(dialog, "notebook") or not hasattr(dialog, "_settings_tabs"):
        return
    tab = dialog._settings_tabs.get(
        key or "common", dialog._settings_tabs["common"]
    )
    try:
        dialog.notebook.select(tab)
    except tk.TclError:
        pass
