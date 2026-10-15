"""Shared native [X] overlay button for entry and auxiliary separators.

A real Tk child owns cursor and tooltip events, so pointer/tooltip behavior is
limited to the button and automatically returns to its canvas on pointer exit.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable


DELETE_BUTTON_FONT = ("TkDefaultFont", 9, "bold")


def create_overlay_delete_button(
    canvas: tk.Misc, *,
    command: Callable[[], None],
    attach_tooltip: Callable[[tk.Widget, str], None],
    tooltip: str,
) -> tk.Button:
    """Return a consistently styled, independently clickable separator X."""
    button = tk.Button(
        canvas,
        text="[X]",
        width=3,
        font=DELETE_BUTTON_FONT,
        takefocus=False,
        relief="flat",
        bd=0,
        highlightthickness=0,
        padx=1,
        pady=0,
        cursor="hand2",
        fg="#ffffff",
        bg="#9d042f",
        activeforeground="#ffffff",
        activebackground="#9d042f",
        command=command,
    )
    button._pc_skip_classic_appearance = True
    attach_tooltip(button, tooltip)
    return button
