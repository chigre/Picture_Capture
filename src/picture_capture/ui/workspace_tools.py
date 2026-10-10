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
    palette.bind("<Escape>", lambda _event: palette.withdraw())
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
    navigation = ttk.Frame(outer)
    navigation.pack(side="top", fill="x", pady=(0, 6))
    ttk.Label(navigation, text="定位功能：").pack(side="left")
    jump_var = tk.StringVar(value="选择工具分组")
    jump = ttk.Combobox(navigation, textvariable=jump_var, state="readonly", width=30)
    jump.pack(side="left", fill="x", expand=True)
    ttk.Button(
        navigation, text="全部展开",
        command=lambda: show_all_sections(app), style="PC.Compact.TButton",
    ).pack(side="left", padx=(6, 0))
    ttk.Button(
        navigation, text="收起", command=palette.withdraw,
        style="PC.Compact.TButton",
    ).pack(side="right", padx=(6, 0))
    scroller = ttk.Frame(outer)
    scroller.pack(fill="both", expand=True)
    canvas = tk.Canvas(scroller, highlightthickness=0, borderwidth=0)
    scrollbar = ttk.Scrollbar(scroller, orient="vertical", command=canvas.yview)
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

    sections = [
        section for section in content.winfo_children()
        if getattr(section, "_collapse_title", None)
    ]
    by_title = {
        str(section._collapse_title): section for section in sections
    }
    jump.configure(values=tuple(by_title))

    def jump_to_section(_event: tk.Event | None = None) -> None:
        section = by_title.get(jump_var.get())
        if section is None:
            return
        choose_workspace_section(app, jump_var.get())

    jump.bind("<<ComboboxSelected>>", jump_to_section)
    app.workspace_tools_section_selector = jump
    app.workspace_tools_sections = by_title
    app.workspace_tools_canvas = canvas
    app.workspace_tools_content = content
    app.workspace_tools_jump = jump_to_section
    app.workspace_tools_jump_var = jump_var

    # Focus the task selector without opening or closing the palette.
    palette.bind("<Control-k>", lambda _event: focus_workspace_section(app))
    palette.bind("<Control-K>", lambda _event: focus_workspace_section(app))
    app.bind("<Control-Shift-t>", lambda _event: toggle_workspace_tools(app), add="+")
    app.bind("<Control-Shift-T>", lambda _event: toggle_workspace_tools(app), add="+")

    
def focus_workspace_section(app: Any) -> str:
    """Keyboard access to task groups without moving the page index."""
    selector = getattr(app, "workspace_tools_section_selector", None)
    if selector is not None:
        selector.focus_set()
        selector.event_generate("<Down>")
    return "break"


def show_all_sections(app: Any) -> None:
    """Restore the full controls list after using compact task mode."""
    for section in getattr(app, "workspace_tools_sections", {}).values():
        app._set_section_expanded(section, True)


def choose_workspace_section(app: Any, title: str) -> None:
    """Keep only one task group expanded to reduce needless scrolling."""
    sections = getattr(app, "workspace_tools_sections", {})
    section = sections.get(title)
    if section is None:
        return
    for candidate in sections.values():
        app._set_section_expanded(candidate, candidate is section)
    selector = getattr(app, "workspace_tools_section_selector", None)
    if selector is not None:
        selector.set(title)
    canvas = getattr(app, "workspace_tools_canvas", None)
    if canvas is not None:
        canvas.yview_moveto(0)


def toggle_workspace_tools(app: Any) -> None:
    window = getattr(app, "workspace_tools_window", None)
    if window is None:
        return
    try:
        if window.state() != "withdrawn":
            window.withdraw()
        else:
            # First opening is positioned beside the main canvas when space permits.
            if not getattr(app, "_workspace_tools_positioned", False):
                app.update_idletasks()
                width = min(860, max(580, app.winfo_screenwidth() - 80))
                height = min(690, max(350, app.winfo_screenheight() - 100))
                right = app.winfo_rootx() + app.winfo_width()
                x = right if right + width <= app.winfo_screenwidth() else max(
                    0, app.winfo_screenwidth() - width - 30
                )
                y = max(0, min(app.winfo_rooty() + 35, app.winfo_screenheight() - height - 50))
                window.geometry(f"{width}x{height}+{x}+{y}")
                app._workspace_tools_positioned = True
            window.deiconify()
            window.lift()
            window.focus_set()
    except tk.TclError:
        return
