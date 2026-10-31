"""Settings dialog responsive option groups and scrollable page layout.

SettingsDialog retains historical method signatures and binding behavior.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    import tkinter.ttk as ttk


def add_check_group(
    self,
    parent: ttk.Frame,
    title: str,
    checks: tuple[tuple[str, str], ...] | list[tuple[str, str]],
    *,
    intro: str = "",
    deps: dict[str, Any],
) -> ttk.LabelFrame:
    ttk = deps["ttk"]
    tk = deps["tk"]
    group = ttk.LabelFrame(parent, text=title, padding=(12, 9))
    group.pack(fill="x", pady=(0, 10))
    group.columnconfigure(0, weight=1)
    row = 0
    if intro:
        intro_label = ttk.Label(
            group, text=intro, foreground="#5f6670", justify="left",
        )
        intro_label.grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8)
        )
        self._bind_responsive_labels(
            group, intro_label, horizontal_padding=24, min_wrap=150
        )
        row += 1

    auto_child_names = (
        "ordinary_auto_columns",
        "ordinary_auto_start_y",
        "ordinary_auto_manual_x",
        "ordinary_auto_column_width",
        "ordinary_auto_gutter",
        "ordinary_auto_character_height",
        "ordinary_auto_row_padding",
    )
    auto_child_set = set(auto_child_names)
    auto_children = [
        (label, name) for label, name in checks if name in auto_child_set
    ]

    for label, name in checks:
        if name in auto_child_set:
            continue
        if name not in self.vars:
            self.vars[name] = tk.BooleanVar(
                value=bool(getattr(self.parent.settings, name))
            )
        check = ttk.Checkbutton(group, text=label, variable=self.vars[name])
        check.grid(row=row, column=0, sticky="w", pady=4)
        if name == "layout_mask_illustrations_use_existing":
            parent_mask = self.vars.get("layout_mask_illustrations")
            if parent_mask is not None:
                def _sync_illustration_reuse_state(*_ignored, master=parent_mask, child=check):
                    child.configure(state="normal" if master.get() else "disabled")
                parent_mask.trace_add("write", _sync_illustration_reuse_state)
                _sync_illustration_reuse_state()
        info = ttk.Label(group, text="ⓘ", foreground="#6b7280", cursor="hand2")
        info.grid(row=row, column=1, sticky="w", padx=(8, 0))
        callback = lambda l=label, n=name: self._show_check_help(l, n)
        self._bind_help_widget(check, callback)
        self._bind_help_widget(info, callback)
        info.bind(
            "<Button-1>",
            lambda _e, l=label, n=name: self._show_check_help(l, n),
            add="+",
        )
        row += 1

        if name == "ordinary_auto_layout" and auto_children:
            child_grid = ttk.Frame(group)
            child_grid.grid(
                row=row, column=0, columnspan=2,
                sticky="w", padx=(22, 0), pady=(0, 4),
            )
            for index, (child_label, child_name) in enumerate(auto_children):
                if child_name not in self.vars:
                    self.vars[child_name] = tk.BooleanVar(
                        value=bool(getattr(self.parent.settings, child_name))
                    )
                child_row = 0 if index < 3 else 1
                child_col = index if index < 3 else index - 3
                child = ttk.Checkbutton(
                    child_grid,
                    text=child_label,
                    variable=self.vars[child_name],
                )
                child.grid(
                    row=child_row, column=child_col,
                    sticky="w", padx=(0, 16), pady=4,
                )
                child_callback = (
                    lambda l=child_label, n=child_name:
                    self._show_check_help(l, n)
                )
                self._bind_help_widget(child, child_callback)
            row += 1
    return group


def scrollable_settings_page(self, tab: ttk.Frame, *, deps: dict[str, Any]) -> ttk.Frame:
    ttk = deps["ttk"]
    tk = deps["tk"]
    host = ttk.Frame(tab)
    host.pack(fill="both", expand=True)

    panes = ttk.Panedwindow(host, orient="horizontal")
    panes.pack(fill="both", expand=True)

    left = ttk.Frame(panes)
    left.rowconfigure(0, weight=1)
    left.columnconfigure(0, weight=1)
    canvas = tk.Canvas(left, highlightthickness=0, borderwidth=0)
    scrollbar = ttk.Scrollbar(left, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")

    content = ttk.Frame(canvas, padding=(14, 12, 10, 18))
    window = canvas.create_window((0, 0), window=content, anchor="nw")
    content.bind(
        "<Configure>",
        lambda _e, cv=canvas: cv.configure(scrollregion=cv.bbox("all")),
    )
    canvas.bind(
        "<Configure>",
        lambda e, cv=canvas, item=window: cv.itemconfigure(item, width=e.width),
    )
    self._settings_canvases[str(tab)] = canvas

    right = ttk.Frame(panes, padding=(6, 8, 8, 8))
    panes.add(left, weight=3)
    panes.add(right, weight=2)

    split_initialized = {"done": False}

    def initialize_split(_event=None) -> None:
        if split_initialized["done"]:
            return
        try:
            width = int(panes.winfo_width())
            if width <= 200:
                return
            panes.sashpos(0, int(width * 0.60))
            split_initialized["done"] = True
        except tk.TclError:
            return

    panes.bind("<Map>", initialize_split, add="+")
    panes.bind("<Configure>", initialize_split, add="+")
    self.after_idle(initialize_split)

    help_box = ttk.LabelFrame(right, text="设置说明", padding=(14, 12))
    help_box.pack(fill="both", expand=True)
    help_title = ttk.Label(
        help_box,
        textvariable=self._settings_help_title_var,
        font=("TkDefaultFont", 10, "bold"),
        justify="left",
    )
    help_title.pack(anchor="w", fill="x", padx=(0, 6))
    # Each tab owns a vertically scrollable help pane. The old Label
    # wrapped long explanations but clipped their bottom beyond the window.
    help_view = ttk.Frame(help_box)
    help_view.pack(fill="both", expand=True, pady=(7, 0))
    help_canvas = tk.Canvas(help_view, borderwidth=0, highlightthickness=0)
    help_scroll = ttk.Scrollbar(help_view, orient="vertical", command=help_canvas.yview)
    help_canvas.configure(yscrollcommand=help_scroll.set)
    help_canvas.pack(side="left", fill="both", expand=True)
    help_scroll.pack(side="right", fill="y")
    help_content = ttk.Frame(help_canvas)
    help_window = help_canvas.create_window((0, 0), window=help_content, anchor="nw")
    help_content.bind(
        "<Configure>",
        lambda _e, cv=help_canvas: cv.configure(scrollregion=cv.bbox("all")),
        add="+",
    )
    help_canvas.bind(
        "<Configure>",
        lambda e, cv=help_canvas, item=help_window: cv.itemconfigure(
            item, width=max(1, e.width)
        ),
        add="+",
    )
    self._settings_help_scroll_canvases.append(help_canvas)
    # Bind the live variable in every tab rather than taking a snapshot.
    help_body = ttk.Label(
        help_content,
        textvariable=self._settings_help_body_var,
        foreground="#555b63",
        justify="left",
        anchor="nw",
        wraplength=300,
    )
    help_body.pack(anchor="w", fill="x", padx=(0, 8))
    help_image = ttk.Label(help_content, anchor="center")
    help_separator = ttk.Separator(help_content, orient="horizontal")
    help_separator.pack(fill="x", pady=(14, 10))
    self._settings_help_image_widgets.append(
        (help_image, help_separator, help_content)
    )
    help_hint = ttk.Label(
        help_content,
        text="把鼠标停在设置项上、点击 ⓘ，或用 Tab/鼠标进入输入框时，"
             "右侧会显示完整说明与版面图解；左侧只保留参数、单位和必要状态。",
        foreground="#7a8088",
        justify="left",
    )
    help_hint.pack(anchor="w", fill="x", padx=(0, 6))
    self._bind_responsive_labels(
        help_content,
        help_body,
        help_hint,
        horizontal_padding=18,
        min_wrap=120,
    )

    def scroll_help(event) -> str:
        direction = (
            (-1 if event.num == 4 else 1)
            if getattr(event, "num", None) in (4, 5)
            else (-1 if getattr(event, "delta", 0) > 0 else 1)
        )
        help_canvas.yview_scroll(3 * direction, "units")
        return "break"

    for wheel_widget in (help_canvas, help_content, help_body, help_hint, help_image):
        for event_name in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            wheel_widget.bind(event_name, scroll_help, add="+")
    help_box.bind(
        "<Configure>",
        lambda _e: self._schedule_settings_help_image_render(),
        add="+",
    )
    return content


# Actual SettingsDialog collapsible controls and introductory layout.

def _add_collapsible_settings(
    self,
    parent: ttk.Frame,
    title: str,
    names: tuple[str, ...] | list[str],
    checks: tuple[tuple[str, str], ...] | list[tuple[str, str]] = (),
 *, deps: dict[str, Any]) -> None:
    tk = deps["tk"]
    ttk = deps["ttk"]
    shell = ttk.Frame(parent)
    shell.pack(fill="x", pady=(0, 10))
    expanded = tk.BooleanVar(value=False)
    title_var = tk.StringVar(value=f"▸ {title}")
    body = ttk.Frame(shell)

    def toggle() -> None:
        if expanded.get():
            expanded.set(False)
            body.pack_forget()
            title_var.set(f"▸ {title}")
        else:
            expanded.set(True)
            title_var.set(f"▾ {title}")
            body.pack(fill="x", pady=(6, 0))

    ttk.Button(shell, textvariable=title_var, command=toggle).pack(fill="x")
    if names:
        self._add_setting_group(body, "参数", names)
    if checks:
        self._add_check_group(body, "行为", checks)

def _settings_intro(self, parent: ttk.Frame, title: str, text: str, *, deps: dict[str, Any]) -> None:
    ttk = deps["ttk"]
    title_label = ttk.Label(
        parent, text=title, font=("TkDefaultFont", 11, "bold"), justify="left",
    )
    title_label.pack(anchor="w", fill="x")
    body_label = ttk.Label(
        parent, text=text, foreground="#5f6670", justify="left",
    )
    body_label.pack(anchor="w", fill="x", pady=(3, 10))
    self._bind_responsive_labels(
        parent,
        title_label,
        body_label,
        horizontal_padding=12,
        min_wrap=160,
    )
