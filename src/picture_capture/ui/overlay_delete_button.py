"""Shared native [X] overlay button for entry and auxiliary separators.

A real Tk child owns cursor and tooltip events, so pointer/tooltip behavior is
limited to the button and automatically returns to its canvas on pointer exit.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable

from ..ui_compat import AUTO_FONT_FAMILY, resolve_content_font_family


# Overlay controls use the OS/language recommended typeface, at a fixed
# point size independent from document zoom and configurable entry fonts.
OVERLAY_CONTROL_FONT_SIZE = 9


def fixed_overlay_control_font(widget: tk.Misc, ocr_language: str) -> tuple:
    return (
        resolve_content_font_family(widget, AUTO_FONT_FAMILY, ocr_language),
        OVERLAY_CONTROL_FONT_SIZE,
        "bold",
    )


def create_overlay_delete_button(
    canvas: tk.Misc, *,
    command: Callable[[], None],
    attach_tooltip: Callable[[tk.Widget, str], None],
    tooltip: str,
    ocr_language: str = "",
    kind: str = "auxiliary",
) -> tk.Button:
    """Return a consistently styled, independently clickable separator X."""
    button = tk.Button(
        canvas,
        text="[X]",
        width=3,
        font=fixed_overlay_control_font(canvas, ocr_language),
        takefocus=False,
        relief="flat",
        bd=0,
        highlightthickness=0,
        padx=1,
        pady=0,
        cursor="hand2",
        fg=("#ffffff" if kind == "entry" else "#222222"),
        bg=("#9d042f" if kind == "entry" else "#f5b83d"),
        activeforeground=("#ffffff" if kind == "entry" else "#222222"),
        activebackground=("#9d042f" if kind == "entry" else "#e9a820"),
        command=command,
    )
    button._pc_skip_classic_appearance = True
    attach_tooltip(button, tooltip)
    return button
