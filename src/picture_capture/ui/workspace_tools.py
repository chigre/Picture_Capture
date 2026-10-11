"""Minimal icon rail and an overlay tool palette that never resizes the page.

Quick-setting widgets are built exactly once, preserving existing commands and
variables. A temporary popover can be pinned for image-and-parameter work.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont, ttk
from typing import Any

from .compact_display_menu import build_compact_display_menu
from .compact_task_menus import (
    build_preprocess_menu, build_layout_menu, build_ocr_menu,
    build_drawing_menu,
)
from .simple_page_controls import (
    install_simple_page_controls, install_simple_page_tree_actions,
)


# Every floating task menu occupies a compact single-column panel.
TOOL_MENU_WIDTH = 280
DEFAULT_RAIL_WIDTH = 140
DEFAULT_PAGE_LIST_WIDTH = 300
RAIL_DIVIDER_WIDTH = 6

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
    and packed horizontal toolbars; both must be stacked for a 280px menu.
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
    app.workspace_rail_width = DEFAULT_RAIL_WIDTH
    app.workspace_page_list_width = DEFAULT_PAGE_LIST_WIDTH
    rail = ttk.Frame(sidebar_host, style="PC.Sidebar.TFrame", width=DEFAULT_RAIL_WIDTH)
    rail.pack(side="left", fill="y", before=app.sidebar_canvas, padx=0)
    rail.pack_propagate(False)
    # The divider also acts as a draggable grip, so 140px is a default rather
    # than an unchangeable restriction on the icon/command column.
    divider = ttk.Frame(sidebar_host, width=RAIL_DIVIDER_WIDTH, cursor="sb_h_double_arrow",
                        style="PC.Sidebar.TFrame")
    divider.pack(side="left", fill="y", before=app.sidebar_canvas)
    stroke = ttk.Separator(divider, orient="vertical")
    stroke.place(relx=0.5, rely=0, relheight=1.0)
    app.workspace_rail_separator = divider
    # Record the original pointer and sash once. Using a cumulative sash delta
    # while ttk.Panedwindow relayouts during <B1-Motion> causes the observed
    # sudden jump when the grip is dragged to the left in 简单 mode.
    drag = {"origin": 0, "width": DEFAULT_RAIL_WIDTH, "sash": 0}

    def start_drag(event: tk.Event) -> None:
        drag["origin"] = int(event.x_root)
        drag["width"] = int(app.workspace_rail_width)
        try:
            drag["sash"] = int(app.main_paned.sashpos(0))
        except tk.TclError:
            drag["sash"] = 0

    def update_drag(event: tk.Event) -> None:
        delta = int(event.x_root) - drag["origin"]
        proposed = max(80, min(340, drag["width"] + delta))
        app.workspace_rail_width = proposed
        if getattr(app, "workspace_mode", "") != "极简":
            rail.configure(width=proposed)
            for entry in getattr(app, "workspace_rail_rows", ()):
                entry.configure(width=proposed)
            # One absolute sash position per pointer movement, identical in
            # 简单 and 正常. Never resize the main OS window during a drag.
            try:
                limit = max(1, app.main_paned.winfo_width() - 160)
                app.main_paned.sashpos(
                    0, max(1, min(limit, drag["sash"] + proposed - drag["width"])),
                )
            except (AttributeError, tk.TclError):
                pass
        position_workspace_popup(app)

    divider.bind("<ButtonPress-1>", start_drag)
    divider.bind("<B1-Motion>", update_drag)
    app.workspace_tools_toggle = rail
    app.workspace_tools_rail = rail
    app.workspace_sidebar_host = sidebar_host
    app.workspace_tools_visible = False
    app.workspace_tools_pinned = True
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
    pin_var = tk.BooleanVar(value=True)
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
    canvas.pack(side="left", fill="both", expand=True)
    content = ttk.Frame(canvas)
    item = canvas.create_window((0, 0), window=content, anchor="nw")

    def refresh_scrollbar(_event: tk.Event | None = None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))
        needs_scroll = content.winfo_reqheight() > max(1, canvas.winfo_height())
        if needs_scroll and scrollbar.winfo_manager() != "pack":
            scrollbar.pack(side="right", fill="y")
        elif not needs_scroll and scrollbar.winfo_manager() == "pack":
            scrollbar.pack_forget()
            canvas.yview_moveto(0)

    content.bind("<Configure>", refresh_scrollbar)
    # Keep the embedded frame at the viewport width: never let the original
    # wide-layout requested size force horizontal scrolling or clipping.
    def resized_canvas(event: tk.Event) -> None:
        canvas.itemconfigure(item, width=max(1, event.width))
        refresh_scrollbar()

    canvas.bind("<Configure>", resized_canvas)
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
    # but it is never shown. A purpose-built, 280px display panel presents
    # exactly the requested order without duplicating variable state.
    sections["图片预处理(前置)"] = build_preprocess_menu(app, content)
    sections["一、版面参数"] = build_layout_menu(app, content)
    sections["二、显示设置"] = build_compact_display_menu(app, content)
    sections["三、共享 OCR 通道 / OCR画线"] = build_ocr_menu(app, content)
    sections["四、画线 / OCR / 插图 / 校对"] = build_drawing_menu(app, content)
    app.workspace_tools_sections = sections
    app.workspace_tools_scrollbar_refresh = refresh_scrollbar
    app.workspace_tools_content = content
    # No accordion: start with only one real task panel attached.
    for child in content.winfo_children():
        child.pack_forget()
    first = sections[TASK_GROUPS[0][2]]
    first.pack(fill="x")
    app.workspace_tools_canvas = canvas
    app.workspace_tools_header = header
    app.workspace_tools_heading = heading
    app.workspace_tools_pin_var = pin_var

    # Give each control a direct wheel binding in addition to bind_all:
    # ttk comboboxes/spinboxes can consume MouseWheel at their class bindtag,
    # which otherwise prevents the event reaching the popup's scroll handler.
    def bind_popup_wheel(widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", scroll_menu_wheel, add="+")
        widget.bind("<Button-4>", lambda e: scroll_menu(e, -3), add="+")
        widget.bind("<Button-5>", lambda e: scroll_menu(e, 3), add="+")
        for child in widget.winfo_children():
            bind_popup_wheel(child)

    bind_popup_wheel(popup)

    rail_style = ttk.Style(app)
    # Explicit dimensions avoid the Windows light native theme adding several
    # pixels of extra row height compared with the dark variant.
    rail_style.configure("PC.Rail.TButton", padding=(0, 0), relief="flat",
                         borderwidth=0, font="TkDefaultFont")
    rail_style.configure("PC.QuickRail.TButton", padding=(0, 0), relief="flat",
                         borderwidth=0, font="TkDefaultFont")
    rail_style.map("PC.Rail.TButton", relief=[("active", "flat")])
    rail_style.map("PC.QuickRail.TButton", relief=[("active", "flat")])
    rail.columnconfigure(0, weight=1)
    app.page_index_labels = {"bookmark":"●","page":"页面","section":"域","lined":"线","fill_status":"填充状态","illustrations":"图"}
    app.page_index_columns = tuple(app.page_index_labels)
    app.workspace_rail_labels = []
    app.workspace_rail_rows = []

    def rail_action(parent: ttk.Frame, row: int, symbol: str, label: str,
                    command: Any, tip: str) -> ttk.Frame:
        """Separate fixed-width icon and text controls: Unicode glyph widths vary."""
        entry = ttk.Frame(parent, style="PC.Sidebar.TFrame", width=140, height=33)
        entry.grid(row=row, column=0, sticky="ew", pady=(0, 1))
        entry.grid_propagate(False)
        app.workspace_rail_rows.append(entry)
        entry.columnconfigure(0, minsize=36)
        entry.columnconfigure(1, weight=1)
        entry.rowconfigure(0, weight=1)
        icon = tk.Canvas(entry, width=30, height=27, borderwidth=0,
                         highlightthickness=0, cursor="hand2")
        icon.grid(row=0, column=0, sticky="ns")
        _draw_rail_icon(icon, symbol)
        icon.bind("<Button-1>", lambda _event: command())
        text_button = ttk.Button(entry, text=label, width=9, command=command,
                                 style="PC.Rail.TButton")
        text_button.grid(row=0, column=1, sticky="nsew", padx=(1, 0), pady=0)
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
    for choice in ("极简", "紧凑", "正常", "最大"):
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

    # 紧凑 mode has a genuine second column, sibling to the icon rail. The
    # old mini list was *inside* the 140px rail, which forced the splitter to
    # jump and squeezed page controls under the launcher buttons.
    simple_slot = ttk.Frame(
        sidebar_host, style="PC.Sidebar.TFrame",
        width=DEFAULT_PAGE_LIST_WIDTH,
    )
    simple_slot.pack_propagate(False)
    app.workspace_mini_page_slot = simple_slot
    mini_host = ttk.Frame(simple_slot, style="PC.Sidebar.TFrame")
    mini_host.pack(fill="both", expand=True)
    mini_host.rowconfigure(1, weight=1)
    mini_host.columnconfigure(0, weight=1)
    # The page panel is not a reduced two-column substitute. It carries all
    # page-range controls, navigation buttons and the complete list columns.
    app.after_idle(lambda: install_simple_page_controls(app, mini_host))
    mini = ttk.Treeview(mini_host, columns=app.page_index_columns,
                        displaycolumns=("bookmark", "page", "lined", "illustrations"),
                        show="headings", selectmode="browse", height=12,
                        style="PC.CompactPage.Treeview")
    for column in app.page_index_columns:
        mini.heading(column, text=app.page_index_labels[column], anchor="center")
        mini.column(column, width=80 if column == "page" else 26, minwidth=20,
                    anchor="center", stretch=False)
        mini.heading(
            column,
            command=lambda key=column: (
                app._sort_page_list(key),
                app.after_idle(lambda: refresh_compact_page_index(app)),
            ),
        )
    mini.grid(row=1, column=0, sticky="nsew")
    mini_scroll = ttk.Scrollbar(mini_host, orient="vertical", command=mini.yview)
    mini_scroll.grid(row=1, column=1, sticky="ns")
    mini_hscroll = ttk.Scrollbar(mini_host, orient="horizontal", command=mini.xview)
    mini_hscroll.grid(row=2, column=0, sticky="ew")
    mini.configure(yscrollcommand=mini_scroll.set, xscrollcommand=mini_hscroll.set)
    optional_columns = ("bookmark", "lined", "illustrations", "section", "fill_status")
    mini_vars = {key: tk.BooleanVar(value=(key in {"bookmark", "lined", "illustrations"}))
                 for key in optional_columns}
    app.workspace_mini_column_vars = mini_vars
    def choose_mini_columns() -> None:
        # Use the same stable column order as the authoritative full list.
        order = ("bookmark", "page", "lined", "illustrations", "section", "fill_status")
        mini.configure(displaycolumns=tuple(
            key for key in order if key == "page" or mini_vars[key].get()
        ))
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
    install_simple_page_tree_actions(app, mini)
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
    # Empty spacer keeps the quick-action/footer area anchored to the bottom.
    rail.rowconfigure(len(TASK_GROUPS) + 4, weight=1)

    footer_row = len(TASK_GROUPS) + 5
    footer = ttk.Frame(rail, style="PC.Footer.TFrame")
    footer.grid(row=footer_row, column=0, sticky="sew", pady=(4, 2))
    footer.columnconfigure(0, weight=1)
    app.project_action_bar = footer
    app.project_footer_buttons = []
    quick_actions = (
        ("普通画线", app.run_normal_draw_action),
        ("OCR画线", app.run_ocr_draw_action),
        ("词条校对", app.open_review),
        ("图片工具栏", lambda: toggle_image_toolbar(app)),
    )
    app.workspace_quick_action_buttons = []
    app.workspace_quick_zoom_controls = []
    quick_host = ttk.Frame(footer, style="PC.Footer.TFrame")
    quick_host.grid(row=0, column=0, sticky="ew", pady=(0, 2))
    app.workspace_quick_actions_host = quick_host
    for index, (label, command) in enumerate(quick_actions):
        quick_host.columnconfigure(index, weight=1, uniform="quickrail")
        button = ttk.Button(
            quick_host, text=("普", "O", "校", "≣")[index],
            command=command, width=2, style="PC.QuickRail.TButton",
        )
        button.grid(row=0, column=index, sticky="ew", padx=0, pady=0)
        app.workspace_quick_action_buttons.append(button)
        if index == 3:
            app._attach_tooltip(button, "图片工具栏：缩放、适合宽度、单栏宽度、适合高度")
    # view_zoom_var is initialized later in the main window constructor.
    # Install these controls after idle; they share the existing zoom variable.
    app.after_idle(lambda: install_compact_zoom_controls(app))
    ttk.Separator(footer, orient="horizontal").grid(
        row=1, column=0, sticky="ew", pady=(2, 4))
    project_actions = (
        ("项目中心", "▣", app.open_recent_project, "打开最近项目与项目管理"),
        ("项目档案", "◈", app.open_project_profile, "配置词典 Profile 和页面模板"),
        ("设置中心", "⚙", app.open_settings, "打开设置中心"),
        ("帮助中心", "?", app.show_help_dialog, "查看帮助与快捷操作"),
    )
    for index, (label, symbol, command, tip) in enumerate(project_actions, start=2):
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
    # Initialize a consistent 140px rail + 6px grip + 300px page list.
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
        # Each tool opens a 280px vertical menu. Reposition instead of
        # resizing the image canvas when the menu would cross the right edge.
        root_width = max(1, int(app.winfo_width()))
        width = min(TOOL_MENU_WIDTH, max(1, root_width - 12))
        left = max(4, min(left, root_width - width - 6))
        available_height = max(1, app.winfo_height() - top - 28)
        section = app.workspace_tools_sections.get(app.workspace_tools_active)
        requested = (
            section.winfo_reqheight() if section is not None
            else app.workspace_tools_content.winfo_reqheight()
        )
        header_height = app.workspace_tools_header.winfo_reqheight()
        height = min(available_height, max(115, requested + header_height + 28))
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
    # Project Profile may have been edited in its wizard since the last menu
    # opening; re-read canonical settings instead of showing stale copies.
    refresh = getattr(section, "refresh_from_settings", None)
    if callable(refresh):
        refresh()
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
    app.workspace_tools_content.update_idletasks()
    app.workspace_tools_scrollbar_refresh()


def show_workspace_task(app: Any, title: str | None) -> None:
    target = title or app.workspace_tools_active or TASK_GROUPS[0][2]
    if app.workspace_tools_visible and target == app.workspace_tools_active:
        hide_workspace_tools(app)
        return
    app.workspace_tools_active = target
    choose_workspace_section(app, target)
    show_workspace_tools(app)
    position_workspace_popup(app)


def size_page_index_to_controls(app: Any) -> None:
    """Use a consistent 140px icon rail plus 300px page list initially."""
    try:
        app.update_idletasks()
        panes = app.main_paned
        width = panes.winfo_width()
        if width > 1 and app.sidebar_canvas.winfo_manager() == "pack":
            panes.sashpos(0, min(preferred_sidebar_width(app), width - 160))
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
    """Toggle the independent page-list column, never the icon rail width."""
    if getattr(app, "page_panel", None) is None:
        return "break"
    if getattr(app, "workspace_mode", None) == "极简":
        return "break"
    if getattr(app, "workspace_mode", None) == "紧凑":
        slot = app.workspace_mini_page_slot
        visible = slot.winfo_manager() != "pack"
        if visible:
            refresh_compact_page_index(app)
        _set_simple_page_visible(app, visible)
        return "break"

    if app.sidebar_canvas.winfo_manager() == "pack":
        refresh_compact_page_index(app)
        app.page_panel.grid_remove()
        app.sidebar_canvas.pack_forget()
        app.sidebar_scrollbar.pack_forget()
        _set_simple_page_visible(app, True)
    else:
        _set_simple_page_visible(app, False)
        app.sidebar_scrollbar.pack(side="right", fill="y")
        app.sidebar_canvas.pack(side="left", fill="both", expand=True)
        app.page_panel.grid()
    # The two list implementations occupy the same 300px column.
    # Keep the current sash location unchanged.
    return "break"

def toggle_sidebar(app: Any) -> str:
    """Temporarily hide page list/text controls while preserving mode state."""
    if app.workspace_sidebar_visible:
        hide_workspace_tools(app)
        app.workspace_sidebar_visible = False
        _set_simple_page_visible(app, False)
        if app.sidebar_canvas.winfo_manager() == "pack":
            app.sidebar_canvas.pack_forget()
            app.sidebar_scrollbar.pack_forget()
        for label in app.workspace_rail_labels:
            label.grid_remove()
        def shrink() -> None:
            try:
                app.main_paned.sashpos(
                    0, int(app.workspace_rail_width) + RAIL_DIVIDER_WIDTH,
                )
            except tk.TclError:
                pass
        app.after_idle(shrink)
    else:
        app.workspace_sidebar_visible = True
        _apply_preset_rail_controls(app, getattr(app, "workspace_mode", "正常"))
        _apply_preset_page_index(app, getattr(app, "workspace_mode", "正常"))
        def expand() -> None:
            try:
                target = preferred_sidebar_width(
                    app, extreme=getattr(app, "workspace_mode", "") == "极简",
                )
                app.main_paned.sashpos(0, min(
                    target, max(1, app.main_paned.winfo_width() - 160),
                ))
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
    app.workspace_tools_rail.configure(width=36 if extreme else app.workspace_rail_width)
    for entry in app.workspace_rail_rows:
        entry.configure(width=36 if extreme else app.workspace_rail_width)
    for label in app.workspace_rail_labels:
        if extreme or not app.workspace_sidebar_visible:
            label.grid_remove()
        else:
            label.grid()
    # Drop unused grid columns in 极简; otherwise even empty weighted
    # columns retain the width of a three-column horizontal toolbar.
    quick_host = app.workspace_quick_actions_host
    for index in range(len(app.workspace_quick_action_buttons)):
        quick_host.columnconfigure(
            index, weight=1 if (not extreme or index == 0) else 0,
            minsize=0, uniform="" if extreme else "quickrail",
        )
    # Keep the abbreviations in ALL modes. Only the direction changes.
    for index, (button, title) in enumerate(zip(
        app.workspace_quick_action_buttons, ("普", "O", "校", "≣"),
    )):
        button.configure(text=title, width=2)
        button.grid_configure(
            row=index if extreme else 0,
            column=0 if extreme else index,
            sticky="ew", padx=0, pady=0,
        )


def _set_simple_page_visible(app: Any, visible: bool) -> None:
    """Show/hide the standalone 300px simple page column without reparenting."""
    slot = app.workspace_mini_page_slot
    if visible and slot.winfo_manager() != "pack":
        # The page list belongs on the far LEFT of the icon column.
        # The rail is always packed, so it is a safe -before anchor.
        slot.pack(side="left", fill="both", before=app.workspace_tools_rail)
    elif not visible and slot.winfo_manager() == "pack":
        slot.pack_forget()


def preferred_sidebar_width(app: Any, *, extreme: bool = False) -> int:
    """140px launcher + 6px grip + 300px page list in normal/compact mode."""
    return (
        36 + RAIL_DIVIDER_WIDTH if extreme else
        int(app.workspace_rail_width) + RAIL_DIVIDER_WIDTH
        + int(app.workspace_page_list_width)
    )


def toggle_image_toolbar(app: Any) -> None:
    """Open or close the existing image zoom toolbar from the rail button."""
    toolbar = getattr(app, "page_size_row", None)
    if toolbar is None:
        return
    if toolbar.winfo_manager() == "place":
        toolbar.place_forget()
    else:
        toolbar.place(relx=0, rely=1, x=8, y=-8, anchor="sw")
        toolbar.lift()


def _apply_preset_page_index(app: Any, mode: str) -> None:
    """Three distinct page-list states: full, compact, or entirely hidden."""
    full = mode in {"正常", "最大"}
    compact = mode == "紧凑"
    if full:
        _set_simple_page_visible(app, False)
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
    _set_simple_page_visible(app, compact)


def set_sidebar_mode(app: Any, mode: str) -> str:
    """Apply independent window presets without mixing page-index states.

    极简 inherits 紧凑's height-fitted window but retains only rail icons,
    compact run-action labels and its own previous/next navigation buttons.
    """
    if mode in {"最简", "简单"}:  # Both legacy saved names map to 紧凑.
        mode = "紧凑"
    if mode not in {"极简", "紧凑", "正常", "最大"}:
        return "break"
    app.workspace_mode = mode
    app.workspace_sidebar_mode_menu.place_forget()
    if not app.workspace_sidebar_visible:
        toggle_sidebar(app)
    _apply_preset_page_index(app, mode)
    _apply_preset_rail_controls(app, mode)

    if mode in {"极简", "紧凑"}:
        def fit_compact() -> None:
            try:
                app.update_idletasks()
                compact_width = preferred_sidebar_width(app, extreme=(mode == "极简"))
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
                required_sidebar = preferred_sidebar_width(app)
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
