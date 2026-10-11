"""Minimal icon rail and an overlay tool palette that never resizes the page.

Quick-setting widgets are built exactly once, preserving existing commands and
variables. A temporary popover can be pinned for image-and-parameter work.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from .compact_display_menu import build_compact_display_menu


# Every floating task menu occupies a compact single-column panel.
TOOL_MENU_WIDTH = 300

TASK_GROUPS = (
    ("预处理", "◫", "图片预处理(前置)"),
    ("版面参数", "▤", "一、版面参数"),
    ("显示参数", "◉", "二、显示设置"),
    ("OCR参数", "⌕", "三、共享 OCR 通道 / OCR画线"),
    ("画线…", "✎", "四、画线 / OCR / 插图 / 校对"),
    ("后期制作", "✂", "五、后期词典制作"),
)



def _stack_tool_menu_controls(root: ttk.Frame) -> None:
    """Reflow the existing quick-settings widgets into one vertical column.

    This changes geometry managers *without recreating controls*, so Tk
    variables, command callbacks, focus bindings and external widget
    references all remain intact.  The original quick-settings layout was
    designed for a broad sidebar and contains many multi-column grid rows
    and packed horizontal toolbars; both must be stacked for a 300px menu.
    """
    containers = (tk.Frame, tk.LabelFrame, ttk.Frame, ttk.LabelFrame)

    def stack(container: tk.Misc) -> None:
        if not isinstance(container, containers):
            return
        children = tuple(container.winfo_children())
        gridded = [child for child in children if child.winfo_manager() == "grid"]
        if gridded:
            ordered = sorted(
                gridded,
                key=lambda child: (
                    int(child.grid_info()["row"]),
                    int(child.grid_info()["column"]),
                ),
            )
            columns = max(
                int(child.grid_info()["column"]) +
                int(child.grid_info().get("columnspan", 1))
                for child in ordered
            )
            # Reset weights from the legacy wide/multi-column grid.
            for col in range(columns):
                container.columnconfigure(col, weight=0, minsize=0, uniform="")
            container.columnconfigure(0, weight=1)
            for child in ordered:
                child.grid_forget()
            for row, child in enumerate(ordered):
                child.grid(
                    row=row, column=0, sticky="ew",
                    padx=0, pady=(0, 3),
                )
        else:
            packed = [child for child in children if child.winfo_manager() == "pack"]
            if len(packed) > 1 and any(
                child.pack_info().get("side") in ("left", "right")
                for child in packed
            ):
                for child in packed:
                    child.pack_forget()
                for child in packed:
                    # Keep small colour swatches and unit labels intrinsic,
                    # while buttons, selectors and other inputs use the width.
                    intrinsic = isinstance(child, (tk.Label, ttk.Label)) or (
                        isinstance(child, tk.Button) and
                        str(child.cget("text")) == ""
                    )
                    child.pack(
                        side="top", anchor="w",
                        fill="none" if intrinsic else "x",
                        padx=0, pady=(0, 2),
                    )
        for child in children:
            if isinstance(child, (tk.Label, ttk.Label)):
                # A long description should wrap rather than set a wide
                # requested size in the narrow task palette.
                child.configure(wraplength=204)
            stack(child)

    for section in root.winfo_children():
        if getattr(section, "_collapse_title", None):
            stack(section)


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
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    content = ttk.Frame(canvas)
    item = canvas.create_window((0, 0), window=content, anchor="nw")
    content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    # Keep the embedded frame at the viewport width: never let the original
    # wide-layout requested size force horizontal scrolling or clipping.
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(
        item, width=max(1, e.width)
    ))
    # Mouse-wheel events go to the hovered child in Tk; binding the canvas
    # alone cannot scroll when the pointer is over an entry or a button.
    def scroll_menu(event: tk.Event, steps: int) -> str | None:
        if not app.workspace_tools_visible or not _within(event.widget, popup):
            return None
        canvas.yview_scroll(steps, "units")
        return "break"

    def scroll_menu_wheel(event: tk.Event) -> str | None:
        delta = int(getattr(event, "delta", 0) or 0)
        if not delta:
            return None
        steps = -max(1, abs(delta) // 120) if delta > 0 else max(1, abs(delta) // 120)
        return scroll_menu(event, steps * 3)

    app.bind_all("<MouseWheel>", scroll_menu_wheel, add="+")
    app.bind_all("<Button-4>", lambda event: scroll_menu(event, -3), add="+")
    app.bind_all("<Button-5>", lambda event: scroll_menu(event, 3), add="+")
    app._build_quick_settings(content)
    _stack_tool_menu_controls(content)
    sections = {
        str(section._collapse_title): section
        for section in content.winfo_children()
        if getattr(section, "_collapse_title", None)
    }
    # The old display section still owns its already-bound quick variables,
    # but it is never shown. A purpose-built, 300px display panel presents
    # exactly the requested order without duplicating variable state.
    sections["二、显示设置"] = build_compact_display_menu(app, content)
    app.workspace_tools_sections = sections
    app.workspace_tools_content = content
    # No accordion: start with only one real task panel attached.
    for child in content.winfo_children():
        child.pack_forget()
    first = sections[TASK_GROUPS[0][2]]
    app._set_section_expanded(first, True, persist=False)
    first.pack(fill="x")
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
        text_button = ttk.Button(entry, text=label, width=9, command=command,
                                 style="PC.Rail.TButton")
        text_button.grid(row=0, column=1, sticky="ew")
        app.workspace_rail_labels.append(text_button)
        if tip:
            app._attach_tooltip(icon, tip)
            app._attach_tooltip(text_button, tip)
        return entry

    sidebar_button = rail_action(
        rail, 0, "☰", "窗口模式", lambda: toggle_sidebar_modes(app),
        "",
    )
    mode_menu = ttk.Frame(app, padding=3, relief="solid", borderwidth=1,
                          style="PC.Sidebar.TFrame")
    app.workspace_sidebar_mode_menu = mode_menu
    for choice in ("极简", "简单", "正常", "最大"):
        ttk.Button(mode_menu, text=choice, width=7, style="PC.Rail.TButton",
                   command=lambda mode=choice: set_sidebar_mode(app, mode)).pack(fill="x")
    # Do not dismiss this menu on <Leave>. Hover transitions between the
    # icon and the floating palette may cross a real gap on Windows.
    # Opening is deliberate (click), and closing requires a selection,
    # Escape, a second click, or a click outside.
    mode_menu.bind("<Escape>", lambda _e: mode_menu.place_forget(), add="+")
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
        "切换页面列表；极简模式下使用下方“上／下”按钮翻页",
    )
    # Ultra-compact page controls live directly under the Page icon and do
    # not depend on the full/mini page index being visible.
    extreme_nav = ttk.Frame(rail, style="PC.Sidebar.TFrame")
    extreme_nav.grid(row=len(TASK_GROUPS) + 3, column=0, sticky="ew", pady=(2, 3))
    extreme_nav.grid_remove()
    extreme_nav.columnconfigure(0, weight=1)
    for nav_row, (caption, delta) in enumerate((("上", -1), ("下", 1))):
        ttk.Button(
            extreme_nav, text=caption, width=3, style="PC.Rail.TButton",
            command=lambda direction=delta: app.change_page(direction),
        ).grid(row=nav_row, column=0, sticky="ew", pady=(0, 2))
    app.workspace_extreme_page_navigation = extreme_nav

    mini_host = ttk.Frame(rail, style="PC.Sidebar.TFrame")
    mini_host.grid(row=len(TASK_GROUPS) + 4, column=0, sticky="nsew")
    mini_host.grid_remove()
    mini_host.rowconfigure(0, weight=1)
    mini_host.columnconfigure(0, weight=1)
    mini = ttk.Treeview(mini_host, columns=app.page_index_columns,
                        displaycolumns=("page", "illustrations"), show="headings",
                        selectmode="browse", height=12, style="PC.CompactPage.Treeview")
    for column in app.page_index_columns:
        mini.heading(column, text=app.page_index_labels[column], anchor="center")
        mini.column(column, width=80 if column == "page" else 26, minwidth=20,
                    anchor="center", stretch=False)
    mini.grid(row=0, column=0, sticky="nsew")
    mini_scroll = ttk.Scrollbar(mini_host, orient="vertical", command=mini.yview)
    mini_scroll.grid(row=0, column=1, sticky="ns")
    mini_hscroll = ttk.Scrollbar(mini_host, orient="horizontal", command=mini.xview)
    mini_hscroll.grid(row=1, column=0, sticky="ew")
    mini.configure(yscrollcommand=mini_scroll.set, xscrollcommand=mini_hscroll.set)
    optional_columns = ("bookmark", "lined", "illustrations", "section", "fill_status")
    mini_vars = {key: tk.BooleanVar(value=(key == "illustrations")) for key in optional_columns}
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
    rail.rowconfigure(len(TASK_GROUPS) + 4, weight=1)

    footer_row = len(TASK_GROUPS) + 5
    footer = ttk.Frame(rail, style="PC.Footer.TFrame")
    footer.grid(row=footer_row, column=0, sticky="sew", pady=(4, 2))
    footer.columnconfigure(0, weight=1)
    app.project_action_bar = footer
    app.project_footer_buttons = []
    quick_actions = (("普通画线", app.run_normal_draw_action),
                     ("OCR画线", app.run_ocr_draw_action),
                     ("词条校对", app.open_review))
    app.workspace_quick_action_buttons = []
    for index, (label, command) in enumerate(quick_actions):
        button = ttk.Button(footer, text=label, command=command, style="PC.Rail.TButton")
        button.grid(row=index, column=0, sticky="ew", pady=(0, 2))
        app.workspace_quick_action_buttons.append(button)
    ttk.Separator(footer, orient="horizontal").grid(
        row=len(quick_actions), column=0, sticky="ew", pady=(2, 5))
    project_actions = (
        ("项目中心", "▣", app.open_recent_project, "打开最近项目与项目管理"),
        ("项目档案", "◈", app.open_project_profile, "配置词典 Profile 和页面模板"),
        ("设置中心", "⚙", app.open_settings, "打开设置中心"),
        ("帮助中心", "?", app.show_help_dialog, "查看帮助与快捷操作"),
    )
    for index, (label, symbol, command, tip) in enumerate(project_actions, start=len(quick_actions) + 1):
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
    def dismiss_mode_on_outside_click(event: tk.Event) -> None:
        if mode_menu.winfo_manager() != "place":
            return
        if not _within(event.widget, mode_menu) and not _within(event.widget, sidebar_button):
            mode_menu.place_forget()
    app.bind_all("<Button-1>", dismiss_mode_on_outside_click, add="+")
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
        # Each tool opens a 300px vertical menu. Reposition instead of
        # resizing the image canvas when the menu would cross the right edge.
        root_width = max(1, int(app.winfo_width()))
        width = min(TOOL_MENU_WIDTH, max(1, root_width - 12))
        left = max(4, min(left, root_width - width - 6))
        height = max(1, app.winfo_height() - top - 28)
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
    """Compatibility entry point: never reveal multiple tool groups at once."""
    choose_workspace_section(app, TASK_GROUPS[0][2])


def choose_workspace_section(app: Any, title: str) -> None:
    section = app.workspace_tools_sections.get(title)
    if section is None:
        return
    # pack_forget removes the other panels completely; unlike collapsing,
    # this leaves no titles, borders or empty placeholders in the popup.
    for child in app.workspace_tools_content.winfo_children():
        if child.winfo_manager() == "pack":
            child.pack_forget()
    if getattr(section, "_collapse_title", None):
        app._set_section_expanded(section, True, persist=False)
        # The popup header already identifies this tool. Do not show an
        # additional accordion title or collapse arrow inside its panel.
        title_var = getattr(section, "_collapse_title_var", None)
        if title_var is not None:
            title_var.set("")
        title_label = getattr(section, "_collapse_label", None)
        if title_label is not None:
            title_label.unbind("<Button-1>")
    section.pack(side="top", fill="x")
    app.workspace_tools_heading.set(
        next((label for label, _icon, section_title in TASK_GROUPS
              if section_title == title), title)
    )
    app.workspace_tools_canvas.yview_moveto(0)


def show_workspace_task(app: Any, title: str | None) -> None:
    target = title or app.workspace_tools_active or TASK_GROUPS[0][2]
    if app.workspace_tools_visible and target == app.workspace_tools_active:
        hide_workspace_tools(app)
        return
    app.workspace_tools_active = target
    choose_workspace_section(app, target)
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
            minimum = rail.winfo_reqwidth() + choices.winfo_reqwidth() + 24
            panes.sashpos(0, min(max(minimum, 1), width - 160))
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
    if getattr(app, "workspace_mode", None) == "极简":
        # The Page icon never silently expands a list in icon-only mode.
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
                minimum = rail.winfo_reqwidth() + app.page_range_controls_row.winfo_reqwidth() + 24
                panes.sashpos(0, min(max(minimum, 1), panes.winfo_width() - 160))
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
            if getattr(app, "workspace_mode", None) != "极简":
                refresh_compact_page_index(app)
                app.workspace_mini_page_host.grid()
        # Ctrl+Shift+B must not resurrect labels or a page list in 极简.
        if getattr(app, "workspace_mode", None) == "极简":
            _apply_preset_page_index(app, "极简")
        _apply_preset_rail_controls(app, getattr(app, "workspace_mode", "正常"))
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
    """Open an intentionally persistent mode selector beside its trigger."""
    menu = app.workspace_sidebar_mode_menu
    rail_button = app.workspace_sidebar_toggle
    try:
        menu.update_idletasks()
        x = rail_button.winfo_rootx() - app.winfo_rootx() + rail_button.winfo_width() + 2
        y = rail_button.winfo_rooty() - app.winfo_rooty()
        x = min(x, max(0, app.winfo_width() - menu.winfo_reqwidth() - 4))
        y = min(y, max(0, app.winfo_height() - menu.winfo_reqheight() - 4))
        menu.place(x=max(0, x), y=max(0, y))
        menu.lift()
    except tk.TclError:
        pass


def toggle_sidebar_modes(app: Any) -> None:
    menu = app.workspace_sidebar_mode_menu
    if menu.winfo_manager() == "place":
        menu.place_forget()
    else:
        show_sidebar_modes(app)


def _apply_preset_rail_controls(app: Any, mode: str) -> None:
    """Switch compact rail visibility without destroying icons or commands."""
    extreme = mode == "极简"
    if extreme:
        app.workspace_extreme_page_navigation.grid()
    else:
        app.workspace_extreme_page_navigation.grid_remove()
    for label in app.workspace_rail_labels:
        if extreme or not app.workspace_sidebar_visible:
            label.grid_remove()
        else:
            label.grid()
    for button, ordinary, compact in zip(
        app.workspace_quick_action_buttons,
        ("普通画线", "OCR画线", "词条校对"),
        ("普", "O", "校"),
    ):
        button.configure(text=compact if extreme else ordinary, width=3 if extreme else 0)


def _apply_preset_page_index(app: Any, mode: str) -> None:
    """Three distinct page-list states: full, compact, or entirely hidden."""
    full = mode in {"正常", "最大"}
    compact = mode == "简单"
    if full:
        app.workspace_mini_page_host.grid_remove()
        if app.sidebar_canvas.winfo_manager() != "pack":
            app.sidebar_scrollbar.pack(side="right", fill="y")
            app.sidebar_canvas.pack(side="left", fill="both", expand=True)
        app.page_panel.grid()
        return

    if app.sidebar_canvas.winfo_manager() == "pack":
        try:
            app._workspace_index_width = app.main_paned.sashpos(0)
        except tk.TclError:
            pass
        app.sidebar_canvas.pack_forget()
        app.sidebar_scrollbar.pack_forget()
    app.page_panel.grid_remove()
    if compact:
        refresh_compact_page_index(app)
        app.workspace_mini_page_host.grid()
    else:
        app.workspace_mini_page_host.grid_remove()


def set_sidebar_mode(app: Any, mode: str) -> str:
    """Apply independent window presets without mixing page-index states.

    极简 inherits 简单's height-fitted window but retains only rail icons,
    compact run-action labels and its own previous/next navigation buttons.
    """
    if mode == "最简":  # Session compatibility, not a selectable UI label.
        mode = "简单"
    if mode not in {"极简", "简单", "正常", "最大"}:
        return "break"
    app.workspace_mode = mode
    app.workspace_sidebar_mode_menu.place_forget()
    if not app.workspace_sidebar_visible:
        toggle_sidebar(app)
    _apply_preset_page_index(app, mode)
    _apply_preset_rail_controls(app, mode)

    if mode in {"极简", "简单"}:
        def fit_compact() -> None:
            try:
                app.update_idletasks()
                compact_width = app.workspace_tools_rail.winfo_reqwidth() + 10
                app.main_paned.sashpos(0, compact_width)
                app.update_idletasks()
                height, top = app.winfo_height(), app.winfo_y()
                if app.image is not None:
                    app.fit_page_height()
                    required = int(compact_width + app.image.width * app.view_scale + 32)
                else:
                    required = app.winfo_width()
                app.state("normal")
                app.geometry(f"{min(app.winfo_screenwidth(), max(240, required))}x{height}+0+{top}")
                app.after_idle(lambda: app.main_paned.sashpos(0, compact_width))
            except tk.TclError:
                pass
        app.after_idle(fit_compact)
    elif mode == "正常":
        def fit_normal() -> None:
            try:
                app.update_idletasks()
                rail = app.workspace_tools_rail
                required_sidebar = rail.winfo_reqwidth() + app.page_range_controls_row.winfo_reqwidth() + 24
                sash = min(required_sidebar, max(1, app.main_paned.winfo_width() - 160))
                app.main_paned.sashpos(0, sash)
                if app.image is not None:
                    required = int(sash + app.image.width * app.view_scale + 32)
                    if app.winfo_width() < required:
                        height, top = app.winfo_height(), app.winfo_y()
                        app.state("normal")
                        app.geometry(f"{min(app.winfo_screenwidth(), required)}x{height}+0+{top}")
            except tk.TclError:
                pass
        app.after_idle(fit_normal)
    elif mode == "最大":
        try:
            app.state("zoomed")
        except tk.TclError:
            app.geometry(f"{app.winfo_screenwidth()}x{app.winfo_screenheight()}+0+0")
        app.after(120, app.fit_page_width)
    return "break"
