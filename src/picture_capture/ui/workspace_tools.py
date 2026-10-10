"""Minimal icon rail and an overlay tool palette that never resizes the page.

Quick-setting widgets are built exactly once, preserving existing commands and
variables. A temporary popover can be pinned for image-and-parameter work.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any


TASK_GROUPS = (
    ("预处理", "◫", "图片预处理(前置)"),
    ("版面", "▤", "一、版面参数"),
    ("显示", "◉", "二、显示设置"),
    ("识别", "⌕", "三、共享 OCR 通道 / OCR画线"),
    ("画线", "✎", "四、画线 / OCR / 插图 / 校对"),
    ("制作", "✂", "五、后期词典制作"),
)


def install_workspace_tools(app: Any, sidebar: ttk.Frame, sidebar_host: ttk.Frame) -> None:
    """Place the icon rail beside the initially visible page index."""
    rail = ttk.Frame(sidebar_host, style="PC.Sidebar.TFrame")
    rail.pack(side="left", fill="y", before=app.sidebar_canvas, padx=(3, 5))
    app.workspace_tools_toggle = rail
    app.workspace_tools_rail = rail
    app.workspace_tools_visible = False
    app.workspace_tools_pinned = False
    app.workspace_tools_active = None

    # Overlay is a child of the main window, not a third Panedwindow pane
    # and not a floating OS window. Thus the image canvas never shrinks.
    popup = ttk.Frame(app, padding=7, relief="solid", borderwidth=1,
                      style="PC.Sidebar.TFrame")
    app.workspace_tools_window = popup
    app.workspace_tools_popup = popup
    header = ttk.Frame(popup)
    header.pack(fill="x", pady=(0, 6))
    heading = tk.StringVar(value="工作工具")
    ttk.Label(header, textvariable=heading).pack(side="left", fill="x", expand=True)
    pin_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        header, text="固定", variable=pin_var,
        command=lambda: set_workspace_pin(app, bool(pin_var.get())),
    ).pack(side="left", padx=5)
    ttk.Button(header, text="×", width=3, command=lambda: hide_workspace_tools(app),
               style="PC.Compact.TButton").pack(side="right")

    scroller = ttk.Frame(popup)
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
    content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(
        item, width=max(e.width, content.winfo_reqwidth())
    ))
    canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(
        -int(e.delta / 120) if e.delta else 0, "units"
    ))
    canvas.bind("<Button-4>", lambda _e: canvas.yview_scroll(-3, "units"))
    canvas.bind("<Button-5>", lambda _e: canvas.yview_scroll(3, "units"))
    app._build_quick_settings(content)
    sections = {
        str(section._collapse_title): section
        for section in content.winfo_children()
        if getattr(section, "_collapse_title", None)
    }
    app.workspace_tools_sections = sections
    app.workspace_tools_canvas = canvas
    app.workspace_tools_heading = heading
    app.workspace_tools_pin_var = pin_var

    index_button = ttk.Button(
        rail, text="▦ 页面", width=8, style="PC.Compact.TButton",
        command=lambda: toggle_page_index(app),
    )
    index_button.grid(row=0, column=0, padx=2, pady=(0, 6), sticky="ew")
    app.workspace_page_index_button = index_button
    app._attach_tooltip(index_button, "页面列表（默认显示，点击收起或展开）")
    for index, (label, symbol, title) in enumerate(TASK_GROUPS, start=1):
        button = ttk.Button(
            rail, text=f"{symbol} {label}", width=8, style="PC.Compact.TButton",
            command=lambda target=title: show_workspace_task(app, target),
        )
        button.grid(row=index, column=0, padx=2, pady=(0, 6), sticky="ew")
        app._attach_tooltip(button, label)
    ttk.Separator(rail, orient="horizontal").grid(
        row=len(TASK_GROUPS) + 1, column=0, sticky="ew", pady=4,
    )
    ttk.Button(
        rail, text="☰ 全部", width=8, style="PC.Compact.TButton",
        command=lambda: show_workspace_task(app, None),
    ).grid(row=len(TASK_GROUPS) + 2, column=0, pady=4)

    # Four persistent project actions live at the bottom of the icon rail.
    # They are independent of the page-index visibility.
    footer_row = len(TASK_GROUPS) + 4
    rail.rowconfigure(footer_row - 1, weight=1)
    footer = ttk.Frame(rail, style="PC.Footer.TFrame")
    footer.grid(row=footer_row, column=0, sticky="sew", pady=(4, 2))
    app.project_action_bar = footer
    app.project_footer_buttons = []
    ttk.Separator(footer, orient="horizontal").pack(fill="x", pady=(0, 5))
    project_actions = (
        ("项目", "▣", app.open_recent_project, "打开最近项目与项目管理"),
        ("档案", "◈", app.open_project_profile, "配置词典 Profile 和页面模板"),
        ("设置", "⚙", app.open_settings, "打开设置中心"),
        ("帮助", "?", app.show_help_dialog, "查看帮助与快捷操作"),
    )
    for label, symbol, command, tip in project_actions:
        button = ttk.Button(
            footer, text=f"{symbol} {label}", width=8, command=command,
            style="PC.Compact.TButton",
        )
        button.pack(fill="x", pady=(0, 5))
        app.project_footer_buttons.append(button)
        app._attach_tooltip(button, f"{label}：{tip}")

    app.bind("<Control-Shift-t>", lambda _e: toggle_workspace_tools(app), add="+")
    app.bind("<Control-Shift-T>", lambda _e: toggle_workspace_tools(app), add="+")
    popup.bind("<Escape>", lambda _e: hide_workspace_tools(app), add="+")

    def dismiss_outside(event: tk.Event) -> None:
        if not app.workspace_tools_visible or app.workspace_tools_pinned:
            return
        widget = event.widget
        if _within(widget, popup) or _within(widget, rail):
            return
        hide_workspace_tools(app)

    app.bind_all("<Button-1>", dismiss_outside, add="+")
    app.bind("<Configure>", lambda _e: position_workspace_popup(app), add="+")
    # Size the initial index to fit all three range choices, not the
    # historical sum of the page-table column widths.
    app.after_idle(lambda: size_page_index_to_controls(app))


def _within(widget: Any, ancestor: tk.Misc) -> bool:
    while widget is not None:
        if widget is ancestor:
            return True
        widget = getattr(widget, "master", None)
    return False


def position_workspace_popup(app: Any) -> None:
    """Position inside the root without changing main pane geometry."""
    if not getattr(app, "workspace_tools_visible", False):
        return
    rail = app.workspace_tools_rail
    popup = app.workspace_tools_popup
    try:
        root_x = app.winfo_rootx()
        root_y = app.winfo_rooty()
        left = rail.winfo_rootx() + rail.winfo_width() - root_x + 6
        top = max(4, rail.winfo_rooty() - root_y)
        remaining = max(160, app.winfo_width() - left - 12)
        width = min(720, remaining)
        height = max(160, app.winfo_height() - top - 28)
        popup.place(x=left, y=top, width=width, height=height)
        popup.lift()
    except tk.TclError:
        pass


def set_workspace_pin(app: Any, pinned: bool) -> None:
    app.workspace_tools_pinned = pinned
    app.workspace_tools_pin_var.set(pinned)


def hide_workspace_tools(app: Any) -> str:
    app.workspace_tools_popup.place_forget()
    app.workspace_tools_visible = False
    return "break"


def show_workspace_tools(app: Any) -> None:
    if not app.workspace_tools_visible:
        app.workspace_tools_visible = True
        position_workspace_popup(app)


def toggle_workspace_tools(app: Any) -> str:
    if app.workspace_tools_visible:
        return hide_workspace_tools(app)
    show_workspace_tools(app)
    return "break"


def show_all_sections(app: Any) -> None:
    for section in app.workspace_tools_sections.values():
        app._set_section_expanded(section, True)


def choose_workspace_section(app: Any, title: str) -> None:
    section = app.workspace_tools_sections.get(title)
    if section is None:
        return
    for candidate in app.workspace_tools_sections.values():
        app._set_section_expanded(candidate, candidate is section)
    app.workspace_tools_heading.set(title)
    app.workspace_tools_canvas.yview_moveto(0)


def show_workspace_task(app: Any, title: str | None) -> None:
    if app.workspace_tools_visible and title == app.workspace_tools_active:
        hide_workspace_tools(app)
        return
    app.workspace_tools_active = title
    if title is None:
        app.workspace_tools_heading.set("全部工作工具")
        show_all_sections(app)
    else:
        choose_workspace_section(app, title)
    show_workspace_tools(app)


def size_page_index_to_controls(app: Any) -> None:
    """Set the initial index width based on the range-selector's requested size."""
    try:
        rail = app.workspace_tools_rail
        choices = app.page_range_controls_row
        app.update_idletasks()
        needed = rail.winfo_reqwidth() + choices.winfo_reqwidth() + 38
        panes = app.main_paned
        width = panes.winfo_width()
        if width > 600:
            panes.sashpos(0, min(needed, width - 350))
    except (AttributeError, tk.TclError):
        pass


def toggle_page_index(app: Any) -> str:
    """Truly collapse the index area and return its width to the viewer."""
    panel = getattr(app, "page_panel", None)
    if panel is None:
        return "break"
    canvas = app.sidebar_canvas
    scrollbar = app.sidebar_scrollbar
    panes = app.main_paned
    rail = app.workspace_tools_rail
    host = rail.master

    if canvas.winfo_manager() == "pack":
        try:
            app._workspace_index_width = panes.sashpos(0)
        except tk.TclError:
            pass
        panel.grid_remove()
        canvas.pack_forget()
        scrollbar.pack_forget()

        def collapse() -> None:
            try:
                panes.sashpos(0, rail.winfo_reqwidth() + 10)
            except tk.TclError:
                pass

        app.after_idle(collapse)
    else:
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        panel.grid()
        def expand() -> None:
            try:
                app.update_idletasks()
                desired = getattr(app, "_workspace_index_width", 0)
                if not desired:
                    desired = rail.winfo_reqwidth() + panel.winfo_reqwidth() + 24
                panes.sashpos(0, min(int(desired), max(200, panes.winfo_width() - 320)))
            except tk.TclError:
                pass
        app.after_idle(expand)
    return "break"
