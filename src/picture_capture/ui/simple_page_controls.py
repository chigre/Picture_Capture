"""Full page-range/navigation controls for the 简单 sidebar page list.

The original page_panel remains authoritative for page selection and data.
This compact view reuses the exact same Tk variables and navigation commands.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any


def refresh_compact_range_appearance(app: Any) -> None:
    """Keep the same compact control chrome in light and dark appearances."""
    colors = getattr(app, "_main_ui_colors", {})
    if not colors:
        return
    for role, widget in getattr(app, "workspace_compact_range_widgets", ()):
        try:
            if not widget.winfo_exists():
                continue
            if role == "radio":
                widget.configure(
                    bg=colors["sidebar"], fg=colors["text"],
                    activebackground=colors["sidebar"],
                    activeforeground=colors["text"],
                    selectcolor=colors["sidebar"],
                )
            elif role == "entry":
                widget.configure(
                    bg=colors["button"], fg=colors["text"],
                    insertbackground=colors["text"],
                )
            else:
                widget.configure(
                    bg=colors["button"], fg=colors["text"],
                    activebackground=colors["button_hover"],
                    activeforeground=colors["text"],
                )
        except (AttributeError, tk.TclError):
            continue


def install_simple_page_controls(app: Any, host: ttk.Frame) -> ttk.Frame:
    """Place compact page controls consistently under both Windows themes.

    Native Vista ttk radiobuttons and pushbuttons add wide invisible margins
    even with padding=0. Classic Tk controls have explicit geometry instead,
    while retaining the original Tk variables, commands and keyboard bindings.
    """
    colors = app._main_ui_colors
    controls = ttk.Frame(host, style="PC.Sidebar.TFrame", padding=(0, 1, 0, 1))
    controls.grid(row=0, column=0, columnspan=2, sticky="ew")
    app.workspace_compact_range_widgets = []

    def remember(role: str, widget: tk.Misc) -> tk.Misc:
        widget._pc_skip_classic_appearance = True
        app.workspace_compact_range_widgets.append((role, widget))
        return widget

    def radio(parent: tk.Misc, caption: str, value: str) -> tk.Radiobutton:
        result = tk.Radiobutton(
            parent, text=caption, variable=app.page_range_var, value=value,
            font="TkDefaultFont", anchor="w", indicatoron=True,
            bg=colors["sidebar"], fg=colors["text"],
            selectcolor=colors["sidebar"], activebackground=colors["sidebar"],
            activeforeground=colors["text"], bd=0, relief="flat",
            highlightthickness=0, padx=0, pady=0,
            cursor="hand2",
        )
        remember("radio", result)
        return result

    def action(parent: tk.Misc, caption: str, callback: Any) -> tk.Button:
        result = tk.Button(
            parent, text=caption, width=2, command=callback,
            font="TkDefaultFont", anchor="center", justify="center",
            bg=colors["button"], fg=colors["text"],
            activebackground=colors["button_hover"],
            activeforeground=colors["text"],
            bd=0, relief="flat", highlightthickness=0,
            padx=0, pady=0, cursor="hand2",
        )
        remember("button", result)
        return result

    # 80% font (applied by the sidebar) with equal native-indicator geometry.
    for column, caption, value in (
        (0, "当前", "current"),
        (1, "至末页", "to_end"),
        (2, "至指定", "to_specified"),
    ):
        radio(controls, caption, value).grid(
            row=0, column=column, sticky="w", padx=0, pady=0,
        )

    spec = ttk.Frame(controls, style="PC.Sidebar.TFrame")
    spec.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 1))
    spec.columnconfigure(1, weight=1)
    # The unlabeled selector and the text field share the same page variable.
    radio(spec, "", "specified").grid(
        row=0, column=0, sticky="w", padx=0, pady=0,
    )
    field = tk.Entry(
        spec, textvariable=app.page_range_spec_var, width=7,
        font="TkDefaultFont", bg=colors["button"], fg=colors["text"],
        insertbackground=colors["text"], bd=1, relief="solid",
        highlightthickness=0, justify="left",
    )
    remember("entry", field)
    field.grid(row=0, column=1, sticky="ew", padx=0, pady=0)
    field.bind("<Return>", lambda _event: app.jump_to_page_spec())
    jump = action(spec, "跳", app.jump_to_page_spec)
    jump.grid(row=0, column=2, sticky="ew", padx=0, pady=0)
    app._attach_tooltip(
        jump, "跳转到指定页面的第一个有效页面；ENTER为快捷键",
    )

    actions = ttk.Frame(controls, style="PC.Sidebar.TFrame")
    actions.grid(row=2, column=0, columnspan=3, sticky="ew")
    for index, (caption, callback, help_text) in enumerate((
        ("⨇", lambda: app.jump_to_bookmark(-1), "上一书签"),
        ("⨈", lambda: app.jump_to_bookmark(1), "下一书签"),
        ("上", lambda: app.change_page(-1), "切换到上页（Shift + 鼠标右键）"),
        ("下", lambda: app.change_page(1), "切换到下页（鼠标右键）"),
    )):
        actions.columnconfigure(index, weight=1, uniform="simple-page-actions")
        button = action(actions, caption, callback)
        button.grid(row=0, column=index, sticky="ew", padx=0, pady=0)
        app._attach_tooltip(button, help_text)
    return controls


def install_simple_page_tree_actions(app: Any, tree: ttk.Treeview) -> None:
    """Mirror original bookmark and section editing in the simple page view."""
    from tkinter import simpledialog

    from picture_capture.project_storage import settings_path

    def selected_column(event: Any) -> str | None:
        name = str(tree.identify_column(event.x) or "")
        try:
            index = int(name.lstrip("#")) - 1
        except ValueError:
            return None
        raw = tuple(tree.tk.splitlist(tree.cget("displaycolumns")))
        if raw == ("#all",):
            raw = tuple(tree.tk.splitlist(tree.cget("columns")))
        return raw[index] if 0 <= index < len(raw) else None

    def on_bookmark(event: Any) -> str | None:
        if tree.identify_region(event.x, event.y) != "cell":
            return None
        if selected_column(event) != "bookmark":
            return None
        if app._preprocess_mode_active():
            app.status_var.set("预处理模式中：不修改页面书签。")
            return "break"
        iid = tree.identify_row(event.y)
        if not iid or app.project is None:
            return "break"
        try:
            index = int(iid)
            stem = app.project.images[index].stem
        except (ValueError, IndexError):
            return "break"
        bookmarked = app._bookmark_stems()
        if stem in bookmarked:
            bookmarked.remove(stem)
        else:
            bookmarked.add(stem)
        app.settings.page_bookmarks = sorted(bookmarked)
        app.project.settings.page_bookmarks = list(app.settings.page_bookmarks)
        app.settings.to_json(settings_path(app.project.root))
        app._update_page_row(index)
        return "break"

    def on_section_double_click(event: Any) -> str | None:
        if tree.identify_region(event.x, event.y) != "cell":
            return None
        if selected_column(event) != "section":
            return None
        if app._preprocess_mode_active():
            app.status_var.set("预处理模式中：SECTION 编辑已锁定。")
            return "break"
        iid = tree.identify_row(event.y)
        if not iid or app.project is None:
            return "break"
        try:
            index = int(iid)
            original = int(str(tree.set(iid, "section") or "0"))
        except (ValueError, IndexError):
            return "break"
        updated = simpledialog.askinteger(
            "Section", "Section 数量（0 = 关闭；1–10 = 启用）：",
            parent=app, initialvalue=original, minvalue=0, maxvalue=10,
        )
        if updated is not None:
            app._set_page_section_count(index, updated)
            if tree.exists(iid):
                tree.set(iid, "section", str(updated))
        return "break"

    tree.bind("<Button-1>", on_bookmark, add="+")
    tree.bind("<Double-1>", on_section_double_click, add="+")


__all__ = ["install_simple_page_controls", "install_simple_page_tree_actions"]
