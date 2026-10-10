"""Index-first workspace with a real resizable right-side tools dock.

The existing quick-settings widgets are built once. Hiding the dock uses
Panedwindow.forget (not destroy), preserving edits, Tk variables and callbacks.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any


TASK_GROUPS = (
    ("预处理", "图片预处理(前置)"),
    ("版面", "一、版面参数"),
    ("显示", "二、显示设置"),
    ("OCR", "三、共享 OCR 通道 / OCR画线"),
    ("画线/校对", "四、画线 / OCR / 插图 / 校对"),
    ("制作", "五、后期词典制作"),
)


def install_workspace_tools(app: Any, sidebar: ttk.Frame) -> None:
    """Keep index navigation in sidebar and mount editable tools in a dock."""
    panes = app.main_paned
    dock = ttk.Frame(panes, padding=(7, 5), style="PC.Sidebar.TFrame")
    app.workspace_tools_window = dock  # stable compatibility reference
    app.workspace_tools_dock = dock
    app.workspace_tools_visible = False
    app.workspace_tools_width = 470
    # Main viewer is already pane 1. Add the dock only on demand.
    toolbar = ttk.Frame(sidebar)
    toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    toolbar.columnconfigure(0, weight=1)
    ttk.Button(
        toolbar, text="☰  工具", command=lambda: toggle_workspace_tools(app),
        style="PC.Compact.TButton",
    ).grid(row=0, column=0, sticky="ew")
    app.workspace_tools_toggle = toolbar
    menu_button = ttk.Menubutton(toolbar, text="▾", width=3, style="PC.Compact.TButton")
    menu_button.grid(row=0, column=1, padx=(4, 0))
    task_menu = tk.Menu(menu_button, tearoff=False)
    for label, title in TASK_GROUPS:
        task_menu.add_command(
            label=label,
            command=lambda target=title: show_workspace_task(app, target),
        )
    task_menu.add_separator()
    task_menu.add_command(label="显示全部工具", command=lambda: (
        show_workspace_tools(app), show_all_sections(app)
    ))
    menu_button.configure(menu=task_menu)
    app.workspace_tools_menu = task_menu

    navigation = ttk.Frame(dock)
    navigation.pack(fill="x", pady=(0, 6))
    ttk.Label(navigation, text="任务：").pack(side="left")
    jump_var = tk.StringVar(value="选择工具分组")
    jump = ttk.Combobox(
        navigation, textvariable=jump_var, state="readonly", width=17
    )
    jump.pack(side="left", fill="x", expand=True)
    ttk.Button(
        navigation, text="全部", command=lambda: show_all_sections(app),
        style="PC.Compact.TButton",
    ).pack(side="left", padx=(4, 0))
    ttk.Button(
        navigation, text="×", width=3, command=lambda: hide_workspace_tools(app),
        style="PC.Compact.TButton",
    ).pack(side="right", padx=(4, 0))

    scroller = ttk.Frame(dock)
    scroller.pack(fill="both", expand=True)
    canvas = tk.Canvas(scroller, highlightthickness=0, borderwidth=0)
    scrollbar = ttk.Scrollbar(scroller, orient="vertical", command=canvas.yview)
    horizontal = ttk.Scrollbar(scroller, orient="horizontal", command=canvas.xview)
    canvas.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
    scrollbar.pack(side="right", fill="y")
    horizontal.pack(side="bottom", fill="x")
    canvas.pack(side="left", fill="both", expand=True)
    content = ttk.Frame(canvas)
    item = canvas.create_window((0, 0), window=content, anchor="nw")
    content.bind(
        "<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(
        item, width=max(e.width, content.winfo_reqwidth())
    ))
    canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-int(e.delta / 120), "units"))
    canvas.bind("<Button-4>", lambda _e: canvas.yview_scroll(-3, "units"))
    canvas.bind("<Button-5>", lambda _e: canvas.yview_scroll(3, "units"))
    app._build_quick_settings(content)

    sections = {
        str(section._collapse_title): section
        for section in content.winfo_children()
        if getattr(section, "_collapse_title", None)
    }
    jump.configure(values=tuple(sections))
    app.workspace_tools_section_selector = jump
    app.workspace_tools_sections = sections
    app.workspace_tools_canvas = canvas
    app.workspace_tools_content = content
    app.workspace_tools_jump_var = jump_var

    def on_select(_event: tk.Event | None = None) -> None:
        choose_workspace_section(app, jump_var.get())

    jump.bind("<<ComboboxSelected>>", on_select)
    # Keep keyboard bindings on main window so they work while viewing images.
    app.bind("<Control-Shift-t>", lambda _e: toggle_workspace_tools(app), add="+")
    app.bind("<Control-Shift-T>", lambda _e: toggle_workspace_tools(app), add="+")
    app.bind("<Control-k>", lambda _e: focus_workspace_section(app), add="+")
    dock.bind("<Escape>", lambda _e: hide_workspace_tools(app), add="+")
    app.bind("<Control-K>", lambda _e: focus_workspace_section(app), add="+")


def _remember_dock_width(app: Any) -> None:
    if not getattr(app, "workspace_tools_visible", False):
        return
    try:
        width = int(app.workspace_tools_dock.winfo_width())
        if width > 100:
            app.workspace_tools_width = width
    except (tk.TclError, AttributeError, ValueError):
        pass


def hide_workspace_tools(app: Any) -> str:
    if getattr(app, "workspace_tools_visible", False):
        _remember_dock_width(app)
        app.main_paned.forget(app.workspace_tools_dock)
        app.workspace_tools_visible = False
    return "break"


def show_workspace_tools(app: Any) -> None:
    if getattr(app, "workspace_tools_visible", False):
        return
    dock = app.workspace_tools_dock
    panes = app.main_paned
    panes.add(dock, weight=0)
    app.workspace_tools_visible = True

    def restore_width() -> None:
        if not getattr(app, "workspace_tools_visible", False):
            return
        try:
            total = panes.winfo_width()
            if total > 450:
                width = min(max(310, int(app.workspace_tools_width)), max(310, total - 340))
                panes.sashpos(1, total - width)
        except tk.TclError:
            pass

    app.after_idle(restore_width)


def toggle_workspace_tools(app: Any) -> str:
    if getattr(app, "workspace_tools_visible", False):
        return hide_workspace_tools(app)
    show_workspace_tools(app)
    return "break"


def focus_workspace_section(app: Any) -> str:
    show_workspace_tools(app)
    selector = app.workspace_tools_section_selector
    selector.focus_set()
    selector.event_generate("<Down>")
    return "break"


def show_all_sections(app: Any) -> None:
    for section in app.workspace_tools_sections.values():
        app._set_section_expanded(section, True)


def choose_workspace_section(app: Any, title: str) -> None:
    sections = app.workspace_tools_sections
    section = sections.get(title)
    if section is None:
        return
    show_workspace_tools(app)
    for candidate in sections.values():
        app._set_section_expanded(candidate, candidate is section)
    app.workspace_tools_section_selector.set(title)
    app.workspace_tools_canvas.yview_moveto(0)


def show_workspace_task(app: Any, title: str) -> None:
    choose_workspace_section(app, title)
