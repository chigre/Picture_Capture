from __future__ import annotations

import tkinter as tk
from tkinter import font, ttk


def _build_modern_dialog_heading(
    parent: tk.Misc, title: str, subtitle: str,
) -> ttk.Frame:
    """Build the shared heading block used by secondary work windows."""
    block = ttk.Frame(parent)
    block.pack(fill="x", pady=(0, 12))
    base = font.nametofont("TkDefaultFont").copy()
    heading_font = base.copy()
    heading_font.configure(
        size=max(13, abs(int(base.cget("size"))) + 4),
        weight="bold",
    )
    ttk.Label(block, text=title, font=heading_font).pack(anchor="w")
    subtitle_label = ttk.Label(
        block,
        text=subtitle,
        foreground="#666666",
        justify="left",
    )
    subtitle_label.pack(anchor="w", fill="x", pady=(3, 0))

    def resize_subtitle(event: tk.Event) -> None:
        try:
            subtitle_label.configure(wraplength=max(160, int(event.width) - 4))
        except tk.TclError:
            pass

    block.bind("<Configure>", resize_subtitle, add="+")
    return block


__all__ = ["_build_modern_dialog_heading"]
