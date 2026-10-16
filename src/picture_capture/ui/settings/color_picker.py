"""Reusable live color-preview buttons for every Settings Center *_color field.

A native tk.Button displays the actual background color (ttk styles often
ignore per-widget background on Windows). The adjacent hex input stays fully
editable; existing StringVar autosave / validation remains authoritative.
"""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import colorchooser, ttk

_RGB = re.compile(r"^#[0-9a-fA-F]{6}$")


def normalized_hex(text: str) -> str | None:
    value = str(text)
    return value.lower() if _RGB.fullmatch(value) else None


def contrast_foreground(color: str) -> str:
    """Black/white text with WCAG-style sRGB relative luminance."""
    color = normalized_hex(color)
    if color is None:
        return "#202020"
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= 0.04045
              else ((channel + 0.055) / 1.055) ** 2.4
              for channel in channels]
    luminance = sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722)))
    return "#161616" if luminance > 0.179 else "#ffffff"


def validate_color_controls(values: dict) -> None:
    """Fail closed before settings autosave mutates any color field."""
    for name, var in values.items():
        if name.endswith("_color") and normalized_hex(str(var.get())) is None:
            raise ValueError(f"{name} 必须是六位 #RRGGBB 颜色（不能有空格）。")


def make_color_widget(parent: tk.Misc, value: tk.Variable) -> ttk.Frame:
    """Single shared input + selectable swatch; no duplicate picker buttons."""
    frame = ttk.Frame(parent)
    frame.columnconfigure(0, weight=1)
    entry = ttk.Entry(frame, textvariable=value, width=18)
    entry.grid(row=0, column=0, sticky="ew")
    button = tk.Button(frame, text="选色…", relief="raised", padx=10, pady=3,
                       bd=1, cursor="hand2")
    button.grid(row=0, column=1, padx=(8, 0), sticky="ew")

    def update_swatch(*_args) -> None:
        chosen = normalized_hex(str(value.get()))
        if chosen is None:
            button.configure(bg="#e5e7eb", fg="#202020",
                             activebackground="#e5e7eb",
                             activeforeground="#202020", text="颜色无效")
        else:
            foreground = contrast_foreground(chosen)
            button.configure(bg=chosen, fg=foreground,
                             activebackground=chosen,
                             activeforeground=foreground, text="选色…")

    def pick() -> None:
        current = normalized_hex(str(value.get())) or "#ffffff"
        chosen = colorchooser.askcolor(color=current, parent=frame.winfo_toplevel())[1]
        if chosen:
            value.set(chosen)  # same StringVar/autosave as manual hex edits

    button.configure(command=pick)
    value.trace_add("write", update_swatch)
    update_swatch()
    return frame
