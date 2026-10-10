"""Index-first workspace: quick tools live in an on-demand palette.

Keep the existing quick-settings builder and command bindings intact.  Only
their Tk parent changes, leaving the page index and project footer in the
persistent left sidebar.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any


def install_workspace_tools(app: Any, sidebar: ttk.Frame) -> None:
    """Build quick controls once in a hidden, scrollable non-modal palette."""
    palette = tk.Toplevel(app)
    palette.title("工作工具 · Picture Capture")
    palette.withdraw()
    palette.transient(app)
    palette.geometry("860x690")
    palette.minsize(580, 350)
    palette.protocol("WM_DELETE_WINDOW", palette.withdraw)
    app.workspace_tools_window = palette

    toolbar = ttk.Frame(sidebar)
    toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    toolbar.columnconfigure(0, weight=1)
    ttk.Button(
        toolbar, text="☰  工作工具 / 画线 / OCR",
        command=lambda: toggle_workspace_tools(app),
        style="PC.Compact.TButton",
    ).grid(row=0, column=0, sticky="ew")
    app.workspace_tools_toggle = toolbar

    outer = ttk.Frame(palette, padding=(10, 8))
    outer.pack(fill="both", expand=True)
    canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0)
    scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    content = ttk.Frame(canvas)
    item = canvas.create_window((0, 0), window=content, anchor="nw")
    content.bind(
        "<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(item, width=e.width))
    # Only scroll the palette while the pointer is over it; never hijack the
    # main page index's existing mousewheel bindings.
    canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-int(e.delta / 120), "units"))
    canvas.bind("<Button-4>", lambda _e: canvas.yview_scroll(-3, "units"))
    canvas.bind("<Button-5>", lambda _e: canvas.yview_scroll(3, "units"))
    app._build_quick_settings(content)


def toggle_workspace_tools(app: Any) -> None:
    window = getattr(app, "workspace_tools_window", None)
    if window is None:
        return
    try:
        if window.state() != "withdrawn":
            window.withdraw()
        else:
            window.deiconify()
            window.lift()
            window.focus_set()
    except tk.TclError:
        return
