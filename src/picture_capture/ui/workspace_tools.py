"""Minimal icon rail and an overlay tool palette that never resizes the page.

Quick-setting Tk variables are initialized once, independently of all visual
menus. A compact task popover can be pinned for image-and-parameter work.
"""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from tkinter import font as tkfont, ttk
from typing import Any

from ..ui_compat import screen_work_area

from .compact_display_menu import build_compact_display_menu
from .compact_headword_profile_menu import build_headword_profile_menu
from .compact_task_menus import (
    build_preprocess_menu, build_layout_menu, build_ocr_menu,
    build_drawing_menu, build_postproduction_menu,
)
from .simple_page_controls import (
    install_simple_page_controls, install_simple_page_tree_actions,
)
from .workspace_mode_shortcuts import (
    create_workspace_mode_shortcut_button, install_workspace_mode_shortcut_traces,
    refresh_workspace_mode_shortcut_buttons,
    toggle_workspace_illustration_editor, toggle_workspace_section_editor,
    toggle_workspace_auxiliary_editor, toggle_workspace_layout,
    toggle_workspace_display_preview,
)


# Every floating task menu occupies a compact single-column panel.
TOOL_MENU_WIDTH = 280
DEFAULT_RAIL_WIDTH = 120
DEFAULT_PAGE_LIST_WIDTH = 260
RAIL_DIVIDER_WIDTH = 6

TASK_GROUPS = (
    ("预处理", "◫", "图片预处理(前置)"),
    ("版面参数", "▤", "一、版面参数"),
    ("显示参数", "◉", "二、显示设置"),
    ("OCR参数", "⌕", "三、共享 OCR 通道 / OCR画线"),
    ("OCR画线设置", "▣", "三之一、OCR画线设置"),
    ("画线…", "✎", "四、画线 / OCR / 插图 / 校对"),
    ("后期制作", "✂", "五、后期词典制作"),
)


# Approved pastel backgrounds and legible text for 普 / O / 校.
# Colours in each tuple: (background, foreground, hover/pressed background).
# Classic Tk.Button avoids native ttk themes ignoring coloured backgrounds.
MACARON_ACTION_COLORS = {
    "普": {
        "light": ("#BFDCF2", "#254B69", "#A9CFEA"),
        "dark": ("#355A75", "#EAF5FF", "#426984"),
    },
    "O": {
        "light": ("#E3CEF6", "#583976", "#D4B8EE"),
        "dark": ("#604A7A", "#F6EBFF", "#755A92"),
    },
    "校": {
        "light": ("#C4EAD8", "#245C47", "#AEDFC8"),
        "dark": ("#376A58", "#E9FFF3", "#477B65"),
    },
}


def _macaron_action_colors(label: str, mode: str) -> tuple[str, str, str]:
    return MACARON_ACTION_COLORS[label][
        "dark" if str(mode).lower() == "dark" else "light"
    ]


def _apply_macaron_button_appearance(button: tk.Button, mode: str) -> None:
    background, foreground, hovered = _macaron_action_colors(
        button._pc_macaron_label, mode,
    )
    button.configure(
        bg=hovered if button._pc_macaron_hovered else background,
        fg=foreground, activebackground=hovered, activeforeground=foreground,
    )


def refresh_macaron_action_buttons(app: Any) -> None:
    """Refresh both action locations on light/dark/system appearance changes."""
    for button in getattr(app, "workspace_macaron_buttons", ()):
        try:
            if button.winfo_exists():
                _apply_macaron_button_appearance(button, app.appearance_mode)
        except (AttributeError, tk.TclError):
            # A previous toolbar may have been destroyed during mode changes.
            continue


def _create_macaron_action_button(
    app: Any, parent: tk.Misc, label: str, command: Any,
) -> tk.Button:
    """Build a centred pastel shortcut with reliable native-Tk colours."""
    background, foreground, hovered = _macaron_action_colors(
        label, app.appearance_mode,
    )
    button = tk.Button(
        parent, text=label, width=2, command=command,
        font="TkDefaultFont", anchor="center", justify="center",
        bg=background, fg=foreground,
        activebackground=hovered, activeforeground=foreground,
        relief="flat", bd=0, highlightthickness=0, padx=1, pady=1,
        cursor="hand2",
    )
    # The generic dark-colour conversion would overwrite our semantic palette.
    button._pc_skip_classic_appearance = True
    button._pc_macaron_label = label
    button._pc_macaron_hovered = False

    def set_hover(hovered: bool) -> None:
        button._pc_macaron_hovered = hovered
        try:
            _apply_macaron_button_appearance(button, app.appearance_mode)
        except tk.TclError:
            pass

    button.bind("<Enter>", lambda _event: set_hover(True), add="+")
    button.bind("<Leave>", lambda _event: set_hover(False), add="+")
    if not hasattr(app, "workspace_macaron_buttons"):
        app.workspace_macaron_buttons = []
    app.workspace_macaron_buttons.append(button)
    return button



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
    """Place a 120px icon rail beside the 260px normal-mode page index."""
    app.workspace_rail_width = DEFAULT_RAIL_WIDTH
    app.workspace_page_list_width = DEFAULT_PAGE_LIST_WIDTH
    rail = ttk.Frame(sidebar_host, style="PC.Sidebar.TFrame", width=DEFAULT_RAIL_WIDTH)
    rail.pack(side="left", fill="y", before=app.sidebar_canvas, padx=0)
    rail.pack_propagate(False)
    # The divider also acts as a draggable grip, so 120px is a default rather
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
        if getattr(app, "workspace_mode", "") == "紧凑":
            size_compact_page_columns(app)
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
    # All shared quick variables/traces are created without any hidden Tk
    # widgets. No old tool sections are constructed, packed or destroyed.
    from .quick_state import initialize_quick_state
    initialize_quick_state(app)
    sections: dict[str, ttk.Frame] = {}
    sections["图片预处理(前置)"] = build_preprocess_menu(app, content)
    sections["一、版面参数"] = build_layout_menu(app, content)
    sections["二、显示设置"] = build_compact_display_menu(app, content)
    sections["三、共享 OCR 通道 / OCR画线"] = build_ocr_menu(app, content)
    sections["三之一、OCR画线设置"] = build_headword_profile_menu(app, content)
    sections["四、画线 / OCR / 插图 / 校对"] = build_drawing_menu(app, content)
    sections["五、后期词典制作"] = build_postproduction_menu(app, content)
    app.preprocess_panel = sections["图片预处理(前置)"]
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
    rail_style.configure("PC.WindowMode.TButton", font="TkDefaultFont",
                         padding=(2, 0))
    rail_style.map("PC.WindowMode.TButton",
                   relief=[("selected", "sunken"), ("!selected", "raised")])
    rail_style.configure("PC.WindowProject.TButton", font="TkDefaultFont",
                         padding=(1, 0))
    rail_style.configure("PC.WindowQuick.TButton", font="TkDefaultFont",
                         padding=(1, 0))
    rail_style.configure("PC.WindowZoom.TEntry", font="TkDefaultFont",
                         padding=(0, 0))
    rail.columnconfigure(0, weight=1)
    app.page_index_labels = {"bookmark":"●","page":"页面","section":"域","lined":"线","fill_status":"填充状态","illustrations":"图"}
    app.page_index_columns = tuple(app.page_index_labels)
    app.workspace_rail_labels = []
    app.workspace_rail_rows = []

    def rail_action(parent: ttk.Frame, row: int, symbol: str, label: str,
                    command: Any, tip: str) -> ttk.Frame:
        """Separate fixed-width icon and text controls: Unicode glyph widths vary."""
        entry = ttk.Frame(parent, style="PC.Sidebar.TFrame", width=DEFAULT_RAIL_WIDTH, height=33)
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
        # Classic flat controls fill the same 33px row in both OS themes,
        # without the varying insets of rounded native ttk buttons.
        colors = app._main_ui_colors
        text_button = tk.Button(
            entry, text=label, width=9, command=command,
            font="TkDefaultFont", anchor="center", justify="center",
            bg=colors["button"], fg=colors["text"],
            activebackground=colors["button_hover"], activeforeground=colors["text"],
            relief="flat", bd=0, highlightthickness=0, padx=0, pady=0,
            cursor="hand2",
        )
        text_button.grid(row=0, column=1, sticky="nsew", padx=(1, 0), pady=0)
        app.workspace_rail_labels.append(text_button)
        if tip:
            app._attach_tooltip(icon, tip)
        return entry

    # Tk keeps the native minimize/maximize/close title-bar controls.
    # Place adjacent workspace presets in a narrow upper-right client strip.
    mode_bar = ttk.Frame(app, style="PC.Sidebar.TFrame", padding=(0, 1, 2, 1))
    mode_bar.pack(side="top", fill="x", before=app.main_paned)
    app.workspace_header_mode_bar = mode_bar
    # Keep the four project actions permanently anchored on the left.
    # Optional zoom/drawing shortcuts and window presets occupy the right.
    mode_group = ttk.Frame(mode_bar, style="PC.Sidebar.TFrame")
    mode_group.pack(side="right")
    app.workspace_header_mode_group = mode_group
    # These fixed header controls stay visible in narrow-window presets.
    # Put L/A/S immediately before ◑; all share the existing display variables.
    app.workspace_mode_shortcut_buttons = {}
    for caption, callback in (
        ("L", lambda: toggle_workspace_layout(app)),
        ("A", lambda: toggle_workspace_display_preview(app, "切图预览")),
        ("S", lambda: toggle_workspace_display_preview(app, "OCR词头区域预览")),
    ):
        button = create_workspace_mode_shortcut_button(
            app, mode_group, caption, callback,
        )
        button.pack(side="left", padx=(0, 1))
    # The theme switch is immediately to the left of 极简, not a window
    # preset; changing it uses the app's persisted appearance preference.
    theme_toggle = _compact_header_button(
        app, mode_group, "◑", lambda: toggle_workspace_appearance(app),
    )
    theme_toggle.pack(side="left", padx=(0, 2))
    app._attach_tooltip(theme_toggle, "切换浅色/深色模式")
    app.workspace_theme_toggle_button = theme_toggle
    app.workspace_title_mode_buttons = {}
    for caption in ("极简", "紧凑", "正常", "最大"):
        button = _compact_header_button(
            app, mode_group, caption,
            lambda mode=caption: set_sidebar_mode(app, mode),
        )
        button.pack(side="left", padx=(1, 0))
        app.workspace_title_mode_buttons[caption] = button
    _refresh_window_mode_buttons(app)

    # No artificial divider between 帮助 and the next toolbar action.
    app.workspace_header_quick_host = ttk.Frame(mode_bar, style="PC.Sidebar.TFrame")
    project_group = ttk.Frame(mode_bar, style="PC.Sidebar.TFrame")
    project_group.pack(side="left", padx=(2, 0))
    app.project_action_bar = project_group  # Compatibility owner.
    app.project_footer_buttons = []  # Also used by preprocess lock handling.
    app.workspace_header_project_buttons = []
    project_actions = (
        ("项目", app.open_recent_project, "打开最近项目与项目管理"),
        ("Profile", app.open_project_profile, "配置词典 Profile 和页面模板"),
        ("设置", app.open_settings, "打开设置中心"),
        ("帮助", app.show_help_dialog, "查看帮助与快捷操作"),
    )
    for label, command, tip in project_actions:
        button = _compact_header_button(app, project_group, label, command)
        button.pack(side="left", padx=(1, 0))
        app._attach_tooltip(button, f"{label}：{tip}")
        app.project_footer_buttons.append(button)
        app.workspace_header_project_buttons.append(button)
    # The header's new widgets use view_zoom_var, initialized later in app.py.
    # Existing bottom-left shortcuts are never moved, hidden or reparented.
    app.after_idle(lambda: install_header_quick_controls(app))
    mode_bar.bind(
        "<Configure>",
        lambda event: _refresh_header_toolbar(app, event.width),
        add="+",
    )
    _refresh_header_toolbar(app, app.winfo_width())
    app.after_idle(lambda: enforce_header_min_width(app))
    for index, (label, symbol, title) in enumerate(TASK_GROUPS):
        rail_action(
            rail, index, symbol, label,
            lambda target=title: show_workspace_task(app, target), label,
        )
    ttk.Separator(rail, orient="horizontal").grid(
        row=len(TASK_GROUPS), column=0, sticky="ew", pady=4,
    )
    # Only the selected window preset owns page-list visibility.
    # 极简 keeps up/down navigation without a manual page-list toggle.
    extreme_nav = ttk.Frame(rail, style="PC.Sidebar.TFrame")
    extreme_nav.grid(row=len(TASK_GROUPS) + 1, column=0, sticky="ew", pady=(2, 3))
    extreme_nav.grid_remove()
    extreme_nav.columnconfigure(0, weight=1)
    for nav_row, (caption, delta) in enumerate((("上", -1), ("下", 1))):
        button = ttk.Button(
            extreme_nav, text=caption, width=3, style="PC.Rail.TButton",
            command=lambda direction=delta: app.change_page(direction),
        )
        button.grid(row=nav_row, column=0, sticky="ew", pady=(0, 2))
        app._attach_tooltip(
            button,
            "切换到上页（Shift + 鼠标右键）" if delta < 0
            else "切换到下页（鼠标右键）",
        )
    app.workspace_extreme_page_navigation = extreme_nav

    # 紧凑 shows a miniature page list beneath the task icons.
    # 正常/最大 display the full-width list beside the rail; 极简 hides both.
    # Never reparent live Treeviews.
    simple_slot = ttk.Frame(rail, style="PC.Sidebar.TFrame")
    simple_slot.grid(
        row=len(TASK_GROUPS) + 2, column=0, sticky="nsew", padx=0, pady=0,
    )
    simple_slot.grid_remove()
    app.workspace_mini_page_slot = simple_slot
    mini_host = ttk.Frame(simple_slot, style="PC.Sidebar.TFrame")
    mini_host.pack(fill="both", expand=True)
    mini_host.rowconfigure(1, weight=1)
    mini_host.columnconfigure(0, weight=1)
    # The page panel is not a reduced two-column substitute. It carries all
    # page-range controls, navigation buttons and the complete list columns.
    def finish_compact_page_controls() -> None:
        install_simple_page_controls(app, mini_host)
        # The controls are created after the window has initialized its page
        # variables; apply the selected preset's font after they exist.
        _apply_compact_sidebar_font(
            app, getattr(app, "workspace_mode", "") == "紧凑",
        )

    app.after_idle(finish_compact_page_controls)
    mini = ttk.Treeview(mini_host, columns=app.page_index_columns,
                        displaycolumns=("page", "lined", "illustrations"),
                        show="headings", selectmode="browse", height=12,
                        style="PC.CompactPage.Treeview")
    for column in app.page_index_columns:
        mini.heading(column, text=app.page_index_labels[column], anchor="center")
        mini.column(column, width=24, minwidth=14,
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
    # Use the Treeview viewport, not the full rail including its scrollbar.
    mini.bind("<Configure>", lambda _event: size_compact_page_columns(app), add="+")
    optional_columns = ("bookmark", "lined", "illustrations", "section", "fill_status")
    mini_vars = {key: tk.BooleanVar(value=(key in {"lined", "illustrations"}))
                 for key in optional_columns}
    app.workspace_mini_column_vars = mini_vars
    def choose_mini_columns() -> None:
        # Use the same stable column order as the authoritative full list.
        order = ("bookmark", "page", "lined", "illustrations", "section", "fill_status")
        mini.configure(displaycolumns=tuple(
            key for key in order if key == "page" or mini_vars[key].get()
        ))
        size_compact_page_columns(app)
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
    rail.rowconfigure(len(TASK_GROUPS) + 2, weight=1)

    footer_row = len(TASK_GROUPS) + 3
    footer = ttk.Frame(rail, style="PC.Footer.TFrame")
    footer.grid(row=footer_row, column=0, sticky="sew", pady=(4, 2))
    footer.columnconfigure(0, weight=1)
    quick_actions = (
        ("普通画线", app.run_normal_draw_action),
        ("OCR画线", app.run_ocr_draw_action),
        ("词条校对", app.open_review),
    )
    app.workspace_quick_action_buttons = []
    app.workspace_macaron_buttons = []
    app.workspace_quick_zoom_controls = []
    quick_host = ttk.Frame(footer, style="PC.Footer.TFrame")
    quick_host.grid(row=0, column=0, sticky="ew", pady=(0, 2))
    app.workspace_quick_actions_host = quick_host
    for index, (label, command) in enumerate(quick_actions):
        quick_host.columnconfigure(index, weight=1, uniform="quickrail")
        button = _create_macaron_action_button(
            app, quick_host, ("普", "O", "校")[index], command,
        )
        button.grid(row=0, column=index, sticky="ew", padx=0, pady=0)
        app.workspace_quick_action_buttons.append(button)
    # In the footer the edit-mode shortcuts remain directly below 普/O/校,
    # even when insufficient space hides optional *header* quick actions.
    app.workspace_edit_shortcut_buttons = []
    for caption, callback in (
        ("图", lambda: toggle_workspace_illustration_editor(app)),
        ("区", lambda: toggle_workspace_section_editor(app)),
        ("辅", lambda: toggle_workspace_auxiliary_editor(app)),
    ):
        button = create_workspace_mode_shortcut_button(
            app, quick_host, caption, callback,
        )
        app.workspace_edit_shortcut_buttons.append(button)
    install_workspace_mode_shortcut_traces(app)
    # view_zoom_var is initialized later in the main window constructor.
    # Install these controls after idle; they share the existing zoom variable.
    app.after_idle(lambda: install_compact_zoom_controls(app))

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


def compact_page_column_widths(
    labels: dict[str, str], rows: list[tuple[str, ...]], columns: tuple[str, ...],
    shown: tuple[str, ...], rail_width: int, measure: Any,
) -> dict[str, int]:
    """Fill the live Treeview width; reserve enough space for each heading.

    The page-name column consumes the remainder, without the old 100px cap.
    Extra user-selected columns can trigger horizontal scrolling if necessary.
    """
    minima = {"bookmark": 21, "page": 44, "section": 25, "lined": 25,
              "fill_status": 55, "illustrations": 25}
    maxima = {"bookmark": 36, "section": 44, "lined": 42,
              "fill_status": 100, "illustrations": 42}
    widths: dict[str, int] = {}
    for index, key in enumerate(columns):
        header = max(minima.get(key, 25), int(measure(labels.get(key, key))) + 16)
        samples = (str(row[index]) for row in rows if index < len(row))
        body = max((int(measure(value)) for value in samples), default=0) + 10
        widths[key] = header if key == "page" else max(header, min(maxima.get(key, 80), body))
    if "page" in shown:
        remaining = int(rail_width) - sum(widths[key] for key in shown if key != "page")
        widths["page"] = max(widths["page"], remaining)
    elif shown:
        first = shown[0]
        widths[first] = max(widths[first], int(rail_width) -
                            sum(widths[col] for col in shown if col != first))
    return widths


def size_compact_page_columns(app: Any) -> None:
    """Fit columns to the real viewport after every compact-list resize."""
    mini = getattr(app, "workspace_mini_page_list", None)
    if mini is None:
        return
    try:
        columns = tuple(app.page_index_columns)
        display = tuple(mini.tk.splitlist(mini.cget("displaycolumns")))
        shown = columns if display == ("#all",) else display
        rows = [tuple(mini.item(iid, "values")) for iid in mini.get_children()]
        viewport = int(mini.winfo_width())
        if viewport <= 1:
            viewport = max(1, int(app.workspace_rail_width) - 18)
        widths = compact_page_column_widths(
            app.page_index_labels, rows, columns, shown,
            max(1, viewport - 2), app.compact_page_font.measure,
        )
        for key, width in widths.items():
            mini.column(key, width=width, minwidth=min(14, width),
                        stretch=False, anchor="center")
    except (AttributeError, tk.TclError, ValueError):
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
        size_compact_page_columns(app)
    except tk.TclError:
        pass


def required_header_width(app: Any) -> int:
    """Actual permanent header width: project labels, presets and native padding."""
    project = app.project_action_bar
    modes = app.workspace_header_mode_group
    # Only the two genuine frame gutters remain; no fake width reservation.
    return max(1, int(project.winfo_reqwidth()) + int(modes.winfo_reqwidth()) + 4)


def enforce_header_min_width(app: Any) -> None:
    """Keep all permanent project text and window controls visible."""
    try:
        minimum = required_header_width(app)
        _, minimum_height = app.minsize()
        app.minsize(minimum, minimum_height)
    except (AttributeError, tk.TclError):
        pass


def _refresh_header_toolbar(app: Any, width: int) -> None:
    """Fill actually available space, never applying an arbitrary 650px cutoff.

    With room for the whole toolbar, show zoom and 普/O/校. With less room,
    show 普/O/校 alone rather than hiding them and leaving a large blank gap.
    The four permanent left-hand text buttons and window presets never hide.
    """
    shortcuts = getattr(app, "workspace_header_shortcut_buttons", ())
    if not shortcuts:
        return  # The first <Configure> runs before the deferred quick controls.
    quick_host = app.workspace_header_quick_host
    zoom_group = app.workspace_header_zoom_group
    zoom_separator = app.workspace_header_zoom_separator

    # Count real requested widget widths and their pack padding (not guesses).
    actions_width = sum(int(button.winfo_reqwidth()) + 1 for button in shortcuts)
    zoom_width = int(zoom_group.winfo_reqwidth()) + int(zoom_separator.winfo_reqwidth()) + 10
    available = int(width) - required_header_width(app)
    density = (
        "full" if available >= actions_width + zoom_width
        else "actions" if available >= actions_width
        else "none"
    )
    if getattr(app, "_workspace_header_quick_density", None) == density:
        return
    app._workspace_header_quick_density = density
    app._workspace_header_quick_visible = density != "none"
    quick_host.pack_forget()
    zoom_group.pack_forget()
    zoom_separator.pack_forget()
    if density == "full":
        zoom_group.pack(side="left", before=shortcuts[0])
        zoom_separator.pack(
            side="left", fill="y", padx=5, pady=3, before=shortcuts[0],
        )
    if density != "none":
        quick_host.pack(side="right")


def install_header_quick_controls(app: Any) -> None:
    """Add a second toolbar; keep one source of truth for zoom and operations."""
    if getattr(app, "workspace_header_quick_buttons", None):
        return
    host = app.workspace_header_quick_host
    zoom_group = ttk.Frame(host, style="PC.Sidebar.TFrame")
    zoom_group.pack(side="left")
    app.workspace_header_zoom_group = zoom_group
    actions = (
        ("➖", lambda: app.zoom(0.87), "缩小显示"),
        ("%", None, "当前缩放百分比；回车应用"),
        ("➕", lambda: app.zoom(1.15), "放大显示"),
        ("⇔", app.fit_page_width, "占满宽度"),
        ("⇳", app.fit_page_height, "占满高度"),
        ("◧", app.fit_single_column_width, "单栏占满宽度"),
    )
    app.workspace_header_quick_buttons = []
    for label, callback, tooltip in actions:
        if callback is None:
            widget = ttk.Entry(
                zoom_group, textvariable=app.view_zoom_var, width=5,
                justify="center", style="PC.WindowZoom.TEntry",
            )
            widget.bind("<Return>", app.apply_view_zoom_text)
            widget.bind("<FocusOut>", app.apply_view_zoom_text)
            app.workspace_header_zoom_entry = widget
        else:
            widget = ttk.Button(
                zoom_group, text=label, width=2, command=callback,
                style="PC.WindowQuick.TButton",
            )
        widget.pack(side="left", padx=(1, 0))
        app._attach_tooltip(widget, tooltip)
        app.workspace_header_quick_buttons.append(widget)
    zoom_separator = ttk.Separator(host, orient="vertical")
    zoom_separator.pack(side="left", fill="y", padx=5, pady=3)
    app.workspace_header_zoom_separator = zoom_separator
    app.workspace_header_shortcut_buttons = []
    shortcuts = (
        ("普", app.run_normal_draw_action, "普通画线"),
        ("O", app.run_ocr_draw_action, "OCR画线"),
        ("校", app.open_review, "词条校对"),
    )
    for label, callback, tooltip in shortcuts:
        button = _create_macaron_action_button(app, host, label, callback)
        button.pack(side="left", padx=(1, 0))
        app._attach_tooltip(button, tooltip)
        app.workspace_header_quick_buttons.append(button)
        app.workspace_header_shortcut_buttons.append(button)
    # Buttons arrive after the first header <Configure>; measure and retry.
    app.after_idle(lambda: _refresh_header_toolbar(
        app, app.workspace_header_mode_bar.winfo_width(),
    ))


def _compact_header_button(
    app: Any, parent: tk.Misc, label: str, command: Any,
) -> tk.Button:
    """Theme-independent tight header control (no Vista button margins)."""
    colors = app._main_ui_colors
    button = tk.Button(
        parent, text=label, width=0, command=command,
        font="TkDefaultFont", anchor="center", justify="center",
        bg=colors["button"], fg=colors["text"],
        activebackground=colors["button_hover"],
        activeforeground=colors["text"],
        bd=0, relief="flat", highlightthickness=0, padx=3, pady=1,
        cursor="hand2",
    )
    # These semantic colours are refreshed with the theme, rather than
    # being transformed a second time by the generic classic-Tk pass.
    button._pc_skip_classic_appearance = True
    return button


def refresh_compact_header_buttons(app: Any) -> None:
    """Update both theme colours and selected mode after a theme switch."""
    colors = getattr(app, "_main_ui_colors", None)
    if not colors:
        return
    controls = list(getattr(app, "workspace_header_project_buttons", ()))
    toggle = getattr(app, "workspace_theme_toggle_button", None)
    if toggle is not None:
        controls.append(toggle)
    for button in controls:
        try:
            if button.winfo_exists():
                button.configure(
                    bg=colors["button"], fg=colors["text"],
                    activebackground=colors["button_hover"],
                    activeforeground=colors["text"],
                )
        except (AttributeError, tk.TclError):
            continue
    _refresh_window_mode_buttons(app)
    refresh_workspace_mode_shortcut_buttons(app)


def toggle_workspace_appearance(app: Any) -> str:
    """Toggle the resolved light/dark theme through the canonical app setter.

    System-following preferences are replaced by the explicitly chosen theme,
    avoiding a separate toolbar state that can drift from the settings UI.
    """
    mode = "light" if getattr(app, "appearance_mode", "light") == "dark" else "dark"
    app.set_appearance_mode(mode)
    return mode


def _refresh_window_mode_buttons(app: Any) -> None:
    """Apply compact, centred selected-state colours without themed margins."""
    active = getattr(app, "workspace_mode", "正常")
    colors = getattr(app, "_main_ui_colors", {})
    for mode, button in getattr(app, "workspace_title_mode_buttons", {}).items():
        try:
            button.configure(
                bg=colors.get("tree_selected") if mode == active
                else colors.get("button"),
                fg=colors.get("text"),
                activebackground=colors.get("button_hover"),
                activeforeground=colors.get("text"),
            )
        except (AttributeError, tk.TclError):
            continue


def _compact_font(app: Any) -> tkfont.Font:
    """80% of the user's actual Tk default font, without global scaling."""
    existing = getattr(app, "workspace_compact_font", None)
    if existing is not None:
        return existing
    source = tkfont.nametofont("TkDefaultFont")
    original = int(source.cget("size"))
    size = max(7, round(original * 0.8)) if original > 0 else min(-7, round(original * 0.8))
    compact = source.copy()
    compact.configure(size=size)
    app.workspace_compact_font = compact
    return compact


def _style_compact_sidebar(app: Any) -> None:
    """Create 80% styles used ONLY by the page-list subtree."""
    small = _compact_font(app)
    style = ttk.Style(app)
    for suffix in ("TButton", "TLabel", "TRadiobutton", "TCheckbutton",
                   "TEntry", "TCombobox"):
        style.configure(f"PC.Workspace80.{suffix}", font=small, padding=0)
    # Theme support for indicatorsize varies; compact text and paddings
    # are applied on all platforms, with a smaller circle where supported.
    style.configure("PC.Workspace80.TRadiobutton",
                    font=small, padding=0, indicatorsize=10)
    # Only the zoom-percentage field uses a smaller font (in every mode).
    # Other zoom buttons and launcher labels retain the normal font.
    style.configure("PC.WorkspaceZoom.TEntry", font=small, padding=0)


def _apply_compact_sidebar_font(app: Any, compact: bool) -> None:
    """Keep page-range controls at 80% and miniature page list at 90%.

    Left launcher labels, project buttons, zoom controls and 普/O/校 retain
    their normal font at every window preset.
    """
    _style_compact_sidebar(app)
    slot = app.workspace_mini_page_slot
    styles = {
        ttk.Label: ("PC.Workspace80.TLabel", "TLabel"),
        ttk.Radiobutton: ("PC.Workspace80.TRadiobutton", "TRadiobutton"),
        ttk.Checkbutton: ("PC.Workspace80.TCheckbutton", "TCheckbutton"),
        ttk.Entry: ("PC.Workspace80.TEntry", "TEntry"),
        ttk.Combobox: ("PC.Workspace80.TCombobox", "TCombobox"),
        ttk.Button: ("PC.Workspace80.TButton", "PC.SimplePage.TButton"),
    }

    def visit(widget: tk.Misc) -> None:
        if isinstance(widget, ttk.Treeview):
            # The compact page-list style uses the separately sized 90% font.
            widget.configure(style="PC.CompactPage.Treeview")
        elif isinstance(widget, (tk.Radiobutton, tk.Entry, tk.Button)):
            widget.configure(font=_compact_font(app) if compact else "TkDefaultFont")
        else:
            for kind, (small, standard) in styles.items():
                if isinstance(widget, kind):
                    widget.configure(style=small if compact else standard)
                    break
        for child in widget.winfo_children():
            visit(child)

    visit(slot)


def install_compact_zoom_controls(app: Any) -> None:
    """Six real zoom controls driven by the existing image-view callbacks."""
    if getattr(app, "workspace_quick_zoom_controls", None):
        return
    host = app.workspace_quick_actions_host
    _style_compact_sidebar(app)
    actions = (
        ("➖", lambda: app.zoom(0.87), "缩小显示"),
        ("%", None, "当前缩放百分比；回车应用"),
        ("➕", lambda: app.zoom(1.15), "放大显示"),
        ("⇔", app.fit_page_width, "占满宽度"),
        ("⇳", app.fit_page_height, "占满高度"),
        ("◧", app.fit_single_column_width, "单栏占满宽度"),
    )
    for label, callback, tooltip in actions:
        if callback is None:
            widget = ttk.Entry(
                host, textvariable=app.view_zoom_var, width=4,
                justify="center", style="PC.WorkspaceZoom.TEntry",
            )
            widget.bind("<Return>", app.apply_view_zoom_text)
            widget.bind("<FocusOut>", app.apply_view_zoom_text)
        else:
            widget = ttk.Button(
                host, text=label, width=2, command=callback,
                style="PC.QuickRail.TButton",
            )
        app._attach_tooltip(widget, tooltip)
        # New controls are not managed yet; the active preset will grid them.
        app.workspace_quick_zoom_controls.append(widget)
    _apply_preset_rail_controls(app, getattr(app, "workspace_mode", "正常"))


def _apply_preset_rail_controls(app: Any, mode: str) -> None:
    """Embed zoom operations in all modes; stack only in 极简."""
    extreme = mode == "极简"
    if extreme:
        app.workspace_extreme_page_navigation.grid()
    else:
        app.workspace_extreme_page_navigation.grid_remove()
    app.workspace_tools_rail.configure(width=36 if extreme else app.workspace_rail_width)
    for entry in app.workspace_rail_rows:
        entry.configure(width=36 if extreme else app.workspace_rail_width)
    for label in app.workspace_rail_labels:
        if extreme:
            label.grid_remove()
        else:
            label.grid()

    # Compact range controls use 80%, while the page list itself uses 90%.
    _apply_compact_sidebar_font(app, mode == "紧凑")
    host = app.workspace_quick_actions_host
    for column in range(3):
        host.columnconfigure(
            column, weight=1 if not extreme or column == 0 else 0,
            minsize=0, uniform="" if extreme else "quickrail",
        )

    # Never expose the old pop-up toolbar or the ≣ toggle in these presets.
    canvas_zoom = getattr(app, "page_size_row", None)
    if canvas_zoom is not None and canvas_zoom.winfo_manager() == "place":
        canvas_zoom.place_forget()

    for index, control in enumerate(app.workspace_quick_zoom_controls):
        control.grid(
            row=index if extreme else index // 3,
            column=0 if extreme else index % 3,
            sticky="ew", padx=0, pady=0,
        )
    for index, (button, title) in enumerate(zip(
        app.workspace_quick_action_buttons, ("普", "O", "校"),
    )):
        button.configure(text=title, width=2)
        button.grid(
            row=6 + index if extreme else 2,
            column=0 if extreme else index,
            sticky="ew", padx=0, pady=0,
        )
    for index, button in enumerate(getattr(app, "workspace_edit_shortcut_buttons", ())):
        button.grid(
            row=9 + index if extreme else 3,
            column=0 if extreme else index,
            sticky="ew", padx=0, pady=0,
        )

def _set_simple_page_visible(app: Any, visible: bool) -> None:
    """Apply only the active mode's miniature page-list visibility."""
    slot = app.workspace_mini_page_slot
    if visible and slot.winfo_manager() != "grid":
        slot.grid()
    elif not visible and slot.winfo_manager() == "grid":
        slot.grid_remove()


def preferred_sidebar_width(
    app: Any, *, extreme: bool = False, compact: bool = False,
) -> int:
    """Extreme 36px; compact 120px with list below; normal adds 260px list."""
    rail_width = 36 if extreme else int(app.workspace_rail_width)
    if extreme or compact:
        return rail_width + RAIL_DIVIDER_WIDTH
    return rail_width + RAIL_DIVIDER_WIDTH + int(app.workspace_page_list_width)


def _apply_preset_page_index(app: Any, mode: str) -> None:
    """Three distinct page-list states: full, compact, or entirely hidden."""
    full = mode in {"正常", "最大"}
    compact = mode == "紧凑"
    if full:
        _set_simple_page_visible(app, False)
        if app.sidebar_canvas.winfo_manager() != "pack":
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


def _window_decoration_height(app: Any) -> int:
    """Find native window chrome so taskbar-exclusive work height is respected.

    Tk geometry requests a client size, but the OS work area measures the
    decorated outer window. Use Windows' real frame/client rectangles rather
    than assuming a constant titlebar size at different DPI scaling.
    """
    if sys.platform == "win32":
        try:
            frame = str(app.tk.call("wm", "frame", app._w))
            hwnd = ctypes.c_void_p(int(frame, 0))

            class RECT(ctypes.Structure):
                _fields_ = (
                    ("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long),
                )

            outer, client = RECT(), RECT()
            user32 = ctypes.windll.user32
            if (user32.GetWindowRect(hwnd, ctypes.byref(outer)) and
                    user32.GetClientRect(hwnd, ctypes.byref(client))):
                outer_height = int(outer.bottom - outer.top)
                client_height = int(client.bottom - client.top)
                if 0 < client_height <= outer_height:
                    return outer_height - client_height
        except (AttributeError, OSError, TypeError, ValueError, tk.TclError):
            pass
    try:
        # Tk fallback: client origin differs from outer position by the titlebar.
        top = max(0, int(app.winfo_rooty()) - int(app.winfo_y()))
        return top + (6 if top else 0)
    except (AttributeError, tk.TclError):
        return 0


def _preset_work_geometry(app: Any) -> tuple[int, int, int, int]:
    """Desktop work area (taskbar excluded), corrected for window decorations."""
    x, y, width, height = screen_work_area(app)
    return int(x), int(y), max(1, int(width)), max(
        1, int(height) - _window_decoration_height(app),
    )


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
    previews = app.__dict__.get("_page_thumbnails")
    if previews is not None:
        previews.on_mode_change()
    _refresh_window_mode_buttons(app)
    _apply_preset_page_index(app, mode)
    _apply_preset_rail_controls(app, mode)

    if mode in {"极简", "紧凑"}:
        def fit_compact() -> None:
            try:
                app.state("normal")
                app.update_idletasks()
                work_x, work_y, work_w, height = _preset_work_geometry(app)
                compact_width = preferred_sidebar_width(
                    app, extreme=(mode == "极简"), compact=(mode == "紧凑"),
                )
                # Set the new usable height *before* fitting the page image,
                # otherwise fit_page_height sees the preceding window size.
                initial_width = min(work_w, max(required_header_width(app), app.winfo_width()))
                app.geometry(f"{initial_width}x{height}+{work_x}+{work_y}")
                app.update_idletasks()
                app.main_paned.sashpos(0, compact_width)
                app.update_idletasks()
                if app.image is not None:
                    app.fit_page_height()
                    required = int(compact_width + app.image.width * app.view_scale + 32)
                else:
                    required = app.winfo_width()
                width = min(work_w, max(required_header_width(app), required))
                app.geometry(f"{width}x{height}+{work_x}+{work_y}")
                app.after_idle(lambda: app.main_paned.sashpos(0, compact_width))
            except tk.TclError:
                pass
        app.after_idle(fit_compact)
    elif mode == "正常":
        def fit_normal() -> None:
            try:
                app.state("normal")
                app.update_idletasks()
                work_x, work_y, work_w, height = _preset_work_geometry(app)
                required_sidebar = preferred_sidebar_width(app)
                sash = min(required_sidebar, max(1, app.main_paned.winfo_width() - 160))
                app.main_paned.sashpos(0, sash)
                width = app.winfo_width()
                if app.image is not None:
                    required = int(sash + app.image.width * app.view_scale + 32)
                    required = max(required_header_width(app), required)
                    width = max(width, required)
                width = min(work_w, max(required_header_width(app), width))
                app.geometry(f"{width}x{height}+{work_x}+{work_y}")
            except tk.TclError:
                pass
        app.after_idle(fit_normal)
    elif mode == "最大":
        try:
            app.state("normal")
            app.geometry("+0+0")
            app.state("zoomed")
        except tk.TclError:
            work_x, work_y, work_w, height = _preset_work_geometry(app)
            app.geometry(f"{work_w}x{height}+{work_x}+{work_y}")
        app.after(120, app.fit_page_width)
    return "break"
