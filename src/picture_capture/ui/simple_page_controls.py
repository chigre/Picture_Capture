"""Full page-range/navigation controls for the 简单 sidebar page list.

The original page_panel remains authoritative for page selection and data.
This compact view reuses the exact same Tk variables and navigation commands.
"""
from __future__ import annotations

from tkinter import ttk
from typing import Any


def install_simple_page_controls(app: Any, host: ttk.Frame) -> ttk.Frame:
    """Expose all full-page controls above the simple-mode mirrored treeview."""
    controls = ttk.Frame(host, style="PC.Sidebar.TFrame", padding=(0, 3, 0, 3))
    controls.grid(row=0, column=0, columnspan=2, sticky="ew")
    controls.columnconfigure(0, weight=1)
    controls.columnconfigure(1, weight=1)

    # Wrap three range selections into two compact lines instead of
    # letting one long horizontal range bar widen the entire icon rail.
    for row, column, caption, value in (
        (0, 0, "当前页", "current"),
        (0, 1, "当前至末页", "to_end"),
        (1, 0, "当前至指定页", "to_specified"),
        (1, 1, "指定", "specified"),
    ):
        ttk.Radiobutton(
            controls, text=caption, variable=app.page_range_var,
            value=value,
        ).grid(row=row, column=column, sticky="w", pady=1)

    spec = ttk.Frame(controls, style="PC.Sidebar.TFrame")
    spec.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(3, 3))
    spec.columnconfigure(0, weight=1)
    field = ttk.Entry(spec, textvariable=app.page_range_spec_var, width=9)
    field.grid(row=0, column=0, sticky="ew", padx=(0, 2))
    field.bind("<Return>", lambda _event: app.jump_to_page_spec())
    ttk.Button(
        spec, text="跳转", command=app.jump_to_page_spec,
        style="PC.PageNav.TButton",
    ).grid(row=0, column=1, sticky="ew")

    actions = ttk.Frame(controls, style="PC.Sidebar.TFrame")
    actions.grid(row=3, column=0, columnspan=2, sticky="ew")
    for index, (caption, callback, help_text) in enumerate((
        ("前签", lambda: app.jump_to_bookmark(-1), "上一书签"),
        ("后签", lambda: app.jump_to_bookmark(1), "下一书签"),
        ("上页", lambda: app.change_page(-1), "上一页"),
        ("下页", lambda: app.change_page(1), "下一页"),
    )):
        actions.columnconfigure(index, weight=1, uniform="simple-page-actions")
        button = ttk.Button(
            actions, text=caption, command=callback,
            style="PC.PageNav.TButton",
        )
        button.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 1, 0))
        app._attach_tooltip(button, help_text)
    return controls


__all__ = ["install_simple_page_controls"]
