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
