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



def _draw_rail_icon(canvas: tk.Canvas, kind: str) -> None:
    """Use Tk vector geometry instead of inconsistent platform Unicode glyphs."""
    ink = "#455265"
    def line(*pts: int, width: int = 2) -> None:
        canvas.create_line(*pts, fill=ink, width=width, capstyle="round", joinstyle="round")
    def rect(x1: int, y1: int, x2: int, y2: int) -> None:
        canvas.create_rectangle(x1, y1, x2, y2, outline=ink, width=2)
    def circle(x1: int, y1: int, x2: int, y2: int) -> None:
        canvas.create_oval(x1, y1, x2, y2, outline=ink, width=2)
    if kind == "☰":  # Collapse sidebar: a panel, not a menu glyph
        rect(5, 5, 21, 21)
        line(11, 6, 11, 20)
    elif kind == "▦":
        rect(5, 4, 21, 22)
        for y in (9, 14, 19):
            line(9, y, 18, y, width=1)
    elif kind == "◫":
        rect(5, 5, 21, 21)
        line(7, 15, 19, 9)
    elif kind == "▤":
        rect(5, 5, 21, 21)
        for y in (10, 15):
            line(8, y, 18, y)
    elif kind == "◉":
        circle(4, 7, 22, 19)
        circle(11, 10, 15, 16)
    elif kind == "⌕":
        circle(5, 4, 17, 16)
        line(16, 16, 22, 22)
    elif kind == "✎":
        line(6, 19, 19, 6, width=3)
        line(5, 22, 11, 20)
    elif kind == "✂":
        circle(5, 5, 11, 11)
        circle(5, 15, 11, 21)
        line(10, 9, 22, 21)
        line(10, 17, 22, 5)
    elif kind == "≡":
        for y in (7, 13, 19):
            line(5, y, 21, y)
    elif kind == "▣":
        rect(4, 7, 22, 21)
        line(6, 7, 10, 4, 17, 4, 21, 7)
    elif kind == "◈":
        line(13, 3, 22, 13, 13, 23, 4, 13, 13, 3)
    elif kind == "⚙":
        circle(5, 5, 21, 21)
        circle(10, 10, 16, 16)
        for angle in (0, 90, 180, 270):
            import math
            rad = math.radians(angle)
            line(int(13 + 9*math.cos(rad)), int(13 + 9*math.sin(rad)),
                 int(13 + 12*math.cos(rad)), int(13 + 12*math.sin(rad)))
    else:
        circle(4, 4, 22, 22)
        canvas.create_text(13, 13, text="?", fill=ink, font=("TkDefaultFont", 12, "bold"))



def install_workspace_tools(app: Any, sidebar: ttk.Frame, sidebar_host: ttk.Frame) -> None:
    """Place the icon rail beside the initially visible page index."""
    rail = ttk.Frame(sidebar_host, style="PC.Sidebar.TFrame")
    rail.pack(side="left", fill="y", before=app.sidebar_canvas, padx=(3, 5))
    app.workspace_tools_toggle = rail
    app.workspace_tools_rail = rail
    app.workspace_sidebar_host = sidebar_host
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

    rail_style = ttk.Style(app)
    rail_style.configure("PC.Rail.TButton", padding=(4, 3), relief="flat", borderwidth=0, font="TkDefaultFont")
    rail_style.map("PC.Rail.TButton", relief=[("active", "flat")])
    rail.columnconfigure(0, weight=1)
    app.page_index_labels = {"bookmark":"●","page":"页面","section":"域","lined":"线","fill_status":"填充状态","illustrations":"图"}
    app.page_index_columns = tuple(app.page_index_labels)
    app.workspace_rail_labels = []

    def rail_action(parent: ttk.Frame, row: int, symbol: str, label: str,
                    command: Any, tip: str) -> ttk.Frame:
        """Separate fixed-width icon and text controls: Unicode glyph widths vary."""
        entry = ttk.Frame(parent, style="PC.Sidebar.TFrame")
        entry.grid(row=row, column=0, sticky="ew", pady=(0, 2))
        entry.columnconfigure(0, minsize=38)
        entry.columnconfigure(1, weight=1)
        icon = tk.Canvas(entry, width=30, height=27, borderwidth=0,
                         highlightthickness=0, cursor="hand2")
        icon.grid(row=0, column=0, sticky="ew")
        _draw_rail_icon(icon, symbol)
        icon.bind("<Button-1>", lambda _event: command())
        text_button = ttk.Button(entry, text=label, width=5, command=command,
                                 style="PC.Rail.TButton")
        text_button.grid(row=0, column=1, sticky="ew")
        app.workspace_rail_labels.append(text_button)
        app._attach_tooltip(icon, tip)
        app._attach_tooltip(text_button, tip)
        return entry

    sidebar_button = rail_action(
        rail, 0, "☰", "侧栏", lambda: show_sidebar_modes(app),
        "悬停选择最简、正常、最大模式",
    )
    mode_menu = ttk.Frame(rail, padding=3, style="PC.Sidebar.TFrame")
    mode_menu.grid(row=0, column=1, sticky="nw")
    mode_menu.grid_remove()
    app.workspace_sidebar_mode_menu = mode_menu
    for choice in ("最简", "正常", "最大"):
        ttk.Button(mode_menu, text=choice, width=5, style="PC.Rail.TButton",
                   command=lambda mode=choice: set_sidebar_mode(app, mode)).pack(fill="x")
    def schedule_mode_hide(_event: tk.Event | None = None) -> None:
        def check() -> None:
            widget = app.winfo_containing(app.winfo_pointerx(), app.winfo_pointery())
            if not _within(widget, sidebar_button) and not _within(widget, mode_menu):
                mode_menu.grid_remove()
        app.after_idle(check)
    for widget in (sidebar_button, *sidebar_button.winfo_children(),
                   mode_menu, *mode_menu.winfo_children()):
        widget.bind("<Enter>", lambda _e: show_sidebar_modes(app), add="+")
        widget.bind("<Leave>", schedule_mode_hide, add="+")
    app.workspace_sidebar_toggle = sidebar_button
    for index, (label, symbol, title) in enumerate(TASK_GROUPS, start=1):
        rail_action(
            rail, index, symbol, label,
            lambda target=title: show_workspace_task(app, target), label,
        )
    ttk.Separator(rail, orient="horizontal").grid(
        row=len(TASK_GROUPS) + 1, column=0, sticky="ew", pady=4,
    )
    app.workspace_page_index_button = rail_action(
        rail, len(TASK_GROUPS) + 2, "▦", "页面", lambda: toggle_page_index(app),
        "切换完整页面列表和简洁页面列表",
    )
    mini_host = ttk.Frame(rail, style="PC.Sidebar.TFrame")
    mini_host.grid(row=len(TASK_GROUPS) + 3, column=0, sticky="nsew")
    mini_host.grid_remove()
    mini_host.rowconfigure(0, weight=1)
    mini_host.columnconfigure(0, weight=1)
    mini = ttk.Treeview(mini_host, columns=app.page_index_columns,
                        displaycolumns=("page",), show="headings",
                        selectmode="browse", height=12, style="PC.CompactPage.Treeview")
    for column in app.page_index_columns:
        mini.heading(column, text=app.page_index_labels[column], anchor="center")
        mini.column(column, width=100 if column == "page" else 42,
                    anchor="center", stretch=False)
    mini.grid(row=0, column=0, sticky="nsew")
    mini_scroll = ttk.Scrollbar(mini_host, orient="vertical", command=mini.yview)
    mini_scroll.grid(row=0, column=1, sticky="ns")
    mini_hscroll = ttk.Scrollbar(mini_host, orient="horizontal", command=mini.xview)
    mini_hscroll.grid(row=1, column=0, sticky="ew")
    mini.configure(yscrollcommand=mini_scroll.set, xscrollcommand=mini_hscroll.set)
    optional_columns = ("bookmark", "lined", "illustrations", "section", "fill_status")
    mini_vars = {key: tk.BooleanVar(value=False) for key in optional_columns}
    app.workspace_mini_column_vars = mini_vars
    def choose_mini_columns() -> None:
        mini.configure(displaycolumns=("page",) + tuple(
            key for key in optional_columns if mini_vars[key].get()))
    def mini_heading_menu(event: tk.Event) -> str | None:
        if mini.identify_region(event.x, event.y) != "heading":
            return None
        menu = tk.Menu(mini, tearoff=False)
        menu.add_checkbutton(label="页面", state="disabled")
        for key in optional_columns:
            menu.add_checkbutton(label=app.page_index_labels[key], variable=mini_vars[key],
                                 command=choose_mini_columns)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"
    mini.bind("<Button-3>", mini_heading_menu)
    app.workspace_mini_page_host = mini_host
    app.workspace_mini_page_list = mini

    def choose_mini_page(_event: tk.Event) -> None:
        selected = mini.selection()
        if not selected or not app.page_list.exists(selected[0]):
            return
        if app.page_list.selection() == selected:
            return
        app.page_list.selection_set(selected[0])
        app.page_list.see(selected[0])
        app.page_list.event_generate("<<TreeviewSelect>>")

    mini.bind("<<TreeviewSelect>>", choose_mini_page)

    def sync_mini_selection(_event: tk.Event) -> None:
        selected = app.page_list.selection()
        if selected and mini.exists(selected[0]) and mini.selection() != selected:
            mini.selection_set(selected[0])
            mini.see(selected[0])

    # The full page table is created after install_workspace_tools returns.
    app.after_idle(lambda: app.page_list.bind(
        "<<TreeviewSelect>>", sync_mini_selection, add="+"))
    rail.rowconfigure(len(TASK_GROUPS) + 3, weight=1)

    footer_row = len(TASK_GROUPS) + 5
    footer = ttk.Frame(rail, style="PC.Footer.TFrame")
    footer.grid(row=footer_row, column=0, sticky="sew", pady=(4, 2))
    footer.columnconfigure(0, weight=1)
    app.project_action_bar = footer
    app.project_footer_buttons = []
    ttk.Separator(footer, orient="horizontal").grid(row=0, column=0, sticky="ew", pady=(0, 5))
    project_actions = (
        ("项目", "▣", app.open_recent_project, "打开最近项目与项目管理"),
        ("档案", "◈", app.open_project_profile, "配置词典 Profile 和页面模板"),
        ("设置", "⚙", app.open_settings, "打开设置中心"),
        ("帮助", "?", app.show_help_dialog, "查看帮助与快捷操作"),
    )
    for index, (label, symbol, command, tip) in enumerate(project_actions, start=1):
        button = rail_action(footer, index, symbol, label, command, f"{label}：{tip}")
        app.project_footer_buttons.append(button)

    app.workspace_sidebar_visible = True
    app.bind("<Control-Shift-b>", lambda _e: toggle_sidebar(app), add="+")
    app.bind("<Control-Shift-B>", lambda _e: toggle_sidebar(app), add="+")
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
        panes = app.main_paned
        width = panes.winfo_width()
        if width > 1 and app.sidebar_canvas.winfo_manager() == "pack":
            minimum = rail.winfo_reqwidth() + 8
            panes.sashpos(0, min(300, max(minimum, width - 320)))
    except (AttributeError, tk.TclError):
        pass


def refresh_compact_page_index(app: Any) -> None:
    """Mirror page names and order without creating another page state."""
    mini = getattr(app, "workspace_mini_page_list", None)
    source = getattr(app, "page_list", None)
    if mini is None or source is None:
        return
    try:
        selected = source.selection()
        mini.delete(*mini.get_children())
        for iid in source.get_children():
            values = source.item(iid, "values")
            if len(values) >= 2:
                mini.insert("", "end", iid=iid, values=values)
        if selected and mini.exists(selected[0]):
            mini.selection_set(selected[0])
            mini.see(selected[0])
    except tk.TclError:
        pass


def toggle_page_index(app: Any) -> str:
    """Toggle full page index vs compact page-only list beneath Page button."""
    panel = getattr(app, "page_panel", None)
    if panel is None:
        return "break"
    canvas = app.sidebar_canvas
    scrollbar = app.sidebar_scrollbar
    panes = app.main_paned
    rail = app.workspace_tools_rail
    mini_host = app.workspace_mini_page_host

    if canvas.winfo_manager() == "pack":
        try:
            app._workspace_index_width = panes.sashpos(0)
        except tk.TclError:
            pass
        refresh_compact_page_index(app)
        panel.grid_remove()
        canvas.pack_forget()
        scrollbar.pack_forget()
        mini_host.grid()
        def compact() -> None:
            try:
                app.update_idletasks()
                panes.sashpos(0, rail.winfo_reqwidth() + 10)
            except tk.TclError:
                pass
        app.after_idle(compact)
    else:
        mini_host.grid_remove()
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        panel.grid()
        def expand() -> None:
            try:
                app.update_idletasks()
                minimum = rail.winfo_reqwidth() + 8
                panes.sashpos(0, min(300, max(minimum, panes.winfo_width() - 320)))
            except tk.TclError:
                pass
        app.after_idle(expand)
    return "break"


def toggle_sidebar(app: Any) -> str:
    """Toggle compact icons-only navigation; never remove its Panedwindow pane."""
    if app.workspace_sidebar_visible:
        app._workspace_index_was_visible = app.sidebar_canvas.winfo_manager() == "pack"
        hide_workspace_tools(app)
        app.workspace_mini_page_host.grid_remove()
        if app.sidebar_canvas.winfo_manager() == "pack":
            try:
                app._workspace_index_width = app.main_paned.sashpos(0)
            except tk.TclError:
                pass
            app.sidebar_canvas.pack_forget()
            app.sidebar_scrollbar.pack_forget()
        for button in app.workspace_rail_labels:
            button.grid_remove()
        app.workspace_sidebar_visible = False

        def compact() -> None:
            try:
                app.main_paned.sashpos(0, app.workspace_tools_rail.winfo_reqwidth() + 8)
            except tk.TclError:
                pass
        app.after_idle(compact)
    else:
        for button in app.workspace_rail_labels:
            button.grid()
        if (getattr(app, "_workspace_index_was_visible", True)
                and app.sidebar_canvas.winfo_manager() != "pack"):
            app.sidebar_scrollbar.pack(side="right", fill="y")
            app.sidebar_canvas.pack(side="left", fill="both", expand=True)
            app.page_panel.grid()
        app.workspace_sidebar_visible = True
        if not getattr(app, "_workspace_index_was_visible", True):
            refresh_compact_page_index(app)
            app.workspace_mini_page_host.grid()
        def expand() -> None:
            try:
                width = app.main_paned.winfo_width()
                minimum = app.workspace_tools_rail.winfo_reqwidth() + 8
                if getattr(app, "_workspace_index_was_visible", True):
                    desired = min(300, max(minimum, width - 320))
                else:
                    desired = minimum
                app.main_paned.sashpos(0, int(desired))
            except tk.TclError:
                pass
        app.after_idle(expand)
    return "break"

def show_sidebar_modes(app: Any) -> None:
    app.workspace_sidebar_mode_menu.grid()


def set_sidebar_mode(app: Any, mode: str) -> str:
    """Apply the requested window and page index layout."""
    app.workspace_sidebar_mode_menu.grid_remove()
    if mode == "最简":
        if app.sidebar_canvas.winfo_manager() == "pack":
            toggle_page_index(app)
        app.update_idletasks()
        if app.image is not None:
            app.fit_page_height()
            app.update_idletasks()
            required = int(app.main_paned.sashpos(0) + app.image.width * app.view_scale + 32)
            try:
                app.state("normal")
                app.geometry(f"{min(app.winfo_screenwidth(), max(240, required))}x{app.winfo_height()}")
            except tk.TclError:
                pass
    elif mode == "正常":
        if app.sidebar_canvas.winfo_manager() != "pack":
            toggle_page_index(app)
        app.update_idletasks()
        if app.image is not None:
            required = int(app.main_paned.sashpos(0) + app.image.width * app.view_scale + 32)
            if app.winfo_width() < required:
                try:
                    app.state("normal")
                    app.geometry(f"{min(app.winfo_screenwidth(), required)}x{app.winfo_height()}")
                except tk.TclError:
                    pass
    elif mode == "最大":
        if app.sidebar_canvas.winfo_manager() != "pack":
            toggle_page_index(app)
        try:
            app.state("zoomed")
        except tk.TclError:
            app.geometry(f"{app.winfo_screenwidth()}x{app.winfo_screenheight()}+0+0")
        app.after_idle(app.fit_page_width)
    return "break"
