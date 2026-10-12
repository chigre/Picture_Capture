"""Copyable, modeless detailed Layout parameters panel.

Verbose diagnostics belong in this window, not on the scanned dictionary.
The content comes from the same full _format_summary that the legacy giant
image overlay previously drew, preserving existing audit information.
"""
from __future__ import annotations

from typing import Any


def layout_detail_text(app: Any) -> str:
    """Return the full existing diagnostic, with no GUI-specific truncation."""
    from .layout_visualization_summary import _format_summary
    from .layout_visualization_ui import _snapshot_for_app

    return _format_summary(app, _snapshot_for_app(app))


def _copy_detail_text(widget: Any) -> None:
    """Copy all content, whether or not the read-only Text has a selection."""
    content = widget.get("1.0", "end-1c")
    if not content:
        return
    widget.clipboard_clear()
    widget.clipboard_append(content)


def _select_all(event: Any) -> str:
    event.widget.tag_add("sel", "1.0", "end-1c")
    event.widget.mark_set("insert", "1.0")
    event.widget.see("1.0")
    return "break"


def refresh_layout_details_if_open(app: Any) -> None:
    """Refresh when the page/settings change, without opening new windows."""
    window = getattr(app, "_layout_details_window", None)
    widget = getattr(app, "_layout_details_text", None)
    if window is None or widget is None:
        return
    try:
        if not window.winfo_exists():
            return
        message = layout_detail_text(app)
    except Exception as exc:
        message = f"Layout 详细诊断暂不可用：{type(exc).__name__}: {exc}"

    try:
        if widget.get("1.0", "end-1c") == message:
            return
        # Preserve the user's scroll position when data refresh is needed.
        top = widget.yview()[0]
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", message)
        widget.configure(state="disabled")
        widget.yview_moveto(top)
        window.title(
            f"Layout 详细诊断 · 第{int(getattr(app,'current_index',0))+1}页"
        )
    except Exception:
        pass


def show_layout_details_window(app: Any) -> None:
    """Open or focus a small, scrollable, fully selectable Layout report."""
    import tkinter as tk
    from tkinter import ttk

    previous = getattr(app, "_layout_details_window", None)
    if previous is not None:
        try:
            if previous.winfo_exists():
                refresh_layout_details_if_open(app)
                previous.lift()
                previous.focus_set()
                return
        except Exception:
            pass

    root = getattr(app, "root", None)
    window = tk.Toplevel(root)
    app._layout_details_window = window
    window.title("Layout 详细诊断")
    window.geometry("660x490")
    window.minsize(430, 290)
    window.transient(root)
    window.columnconfigure(0, weight=1)
    window.rowconfigure(1, weight=1)

    title = ttk.Label(
        window, text="Layout 参数与推理依据（只读，可选择、复制）",
        font=("TkDefaultFont", 10, "bold"),
    )
    title.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))

    body = ttk.Frame(window)
    body.grid(row=1, column=0, sticky="nsew", padx=12)
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=1)

    report = tk.Text(
        body, wrap="word", font=("TkFixedFont", 10),
        padx=10, pady=9, relief="flat", highlightthickness=1,
        highlightbackground="#cbd5e1",
        state="disabled", undo=False,
    )
    report.grid(row=0, column=0, sticky="nsew")
    bar = ttk.Scrollbar(body, orient="vertical", command=report.yview)
    bar.grid(row=0, column=1, sticky="ns")
    report.configure(yscrollcommand=bar.set)
    report.bind("<Control-a>", _select_all)
    report.bind("<Control-A>", _select_all)
    report.bind("<Command-a>", _select_all)

    actions = ttk.Frame(window)
    actions.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 12))
    ttk.Button(
        actions, text="复制全部",
        command=lambda: _copy_detail_text(report),
    ).pack(side="left")
    ttk.Button(
        actions, text="刷新",
        command=lambda: refresh_layout_details_if_open(app),
    ).pack(side="left", padx=(8, 0))
    ttk.Button(
        actions, text="关闭", command=window.destroy,
    ).pack(side="right")
    app._layout_details_text = report

    def close() -> None:
        window.destroy()
        app._layout_details_window = None
        app._layout_details_text = None

    window.protocol("WM_DELETE_WINDOW", close)
    refresh_layout_details_if_open(app)


def add_layout_details_button(app: Any, section: Any) -> None:
    """Legacy full-width settings also expose the same copyable report."""
    from tkinter import ttk
    from .layout_visualization_ui_v3 import _next_grid_row

    if getattr(app, "_layout_details_button", None) is not None:
        return
    button = ttk.Button(
        section, text="Layout详细诊断（复制）",
        command=lambda: show_layout_details_window(app),
    )
    button.grid(
        row=_next_grid_row(section), column=0,
        columnspan=4, sticky="w", pady=(3, 0),
    )
    app._layout_details_button = button


__all__ = [
    "layout_detail_text", "_copy_detail_text", "_select_all",
    "refresh_layout_details_if_open", "show_layout_details_window",
    "add_layout_details_button",
]
