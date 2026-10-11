"""Project Profile fields and automatic layout policy in the compact Layout menu.

The menu edits the same AppSettings fields as Project Profile. Geometry uses
the existing quick_vars/quick_pixel_vars percent-to-pixel synchronization.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from .compact_ordinary_evidence_menu import build_ordinary_visual_evidence

from picture_capture.profile_indent_ui import (
    INDENT_TYPE_CHOICES, apply_indent_type_label, indent_type_label,
)
from picture_capture.profile_semantics import (
    READING_LABELS, apply_reading_choice, reading_choice_from_settings,
)
from picture_capture.profile_setup import (
    HEADER_LABEL_TO_VALUE, FOOTER_LABEL_TO_VALUE, SIDE_LABEL_TO_VALUE,
)

# Dict keys are the true, persisted Project Profile fields, not display aliases.
PROFILE_TEXT_FIELDS = (
    ("词典全称", "dictionary_full_name"),
    ("词典简称(字母)", "dictionary_abbreviation"),
    ("ISBN", "dictionary_isbn"),
    ("正文页码", "dictionary_body_page_range"),
)

LAYOUT_ROWS = (
    ("正文栏数:", "columns", "ordinary_auto_columns"),
    ("正文起始Y:", "start_y", "ordinary_auto_start_y"),
    ("首栏X:", "manual_x", "ordinary_auto_manual_x"),
    ("单栏宽:", "column_width", "ordinary_auto_column_width"),
    ("栏间空:", "gutter", "ordinary_auto_gutter"),
    ("典型单行字高:", "character_height", "ordinary_auto_character_height"),
    ("典型行间空白:", "row_padding", "ordinary_auto_row_padding"),
    ("正文缩进:", "body_indent", None),
    ("微调判据:", "horizontal_tolerance", None),
)

PROFILE_TEMPLATE_FIELDS = (
    ("页眉:", "profile_header_mode", HEADER_LABEL_TO_VALUE),
    ("页尾:", "profile_footer_mode", FOOTER_LABEL_TO_VALUE),
    ("页边内容:", "profile_side_content_mode", SIDE_LABEL_TO_VALUE),
)
PROFILE_PERCENT_FIELDS = (
    ("排除高度%", "profile_header_percent", 35.0),
    ("排除高度%", "profile_footer_percent", 35.0),
    ("固定页边宽度%", "profile_side_percent", 30.0),
    ("A页排除宽度%", "profile_side_percent_a", 30.0),
    ("B页排除宽度%", "profile_side_percent_b", 30.0),
)


def _divider(panel: ttk.Frame) -> None:
    ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=(6, 5))


def build_layout_profile_menu(app: Any, parent: tk.Misc) -> ttk.Frame:
    panel = ttk.Frame(parent, padding=(4, 3, 4, 6))
    profile_vars: dict[str, tk.StringVar] = {}
    profile_buttons: dict[str, ttk.Widget] = {}
    auto_buttons: list[ttk.Checkbutton] = []
    ui_syncing = False

    def row() -> ttk.Frame:
        result = ttk.Frame(panel)
        result.pack(fill="x", pady=(2, 2))
        return result

    def caption(frame: ttk.Frame, value: str, width: int = 15) -> ttk.Label:
        widget = ttk.Label(frame, text=value, width=width, anchor="w")
        widget.pack(side="left", padx=0, pady=0)
        return widget

    def text_field(name: str, title: str) -> None:
        frame = row()
        caption(frame, title, 15)
        variable = tk.StringVar(value=str(getattr(app.settings, name, "")))
        profile_vars[name] = variable
        entry = ttk.Entry(frame, textvariable=variable)
        entry.pack(side="left", fill="x", expand=True, padx=0, pady=0)
        entry.bind("<Return>", lambda _e, key=name: save_field(key))
        entry.bind("<FocusOut>", lambda _e, key=name: save_field(key))

    def save_field(name: str) -> None:
        if ui_syncing:
            return
        raw = profile_vars[name].get().strip()
        if name in {field for _title, field, _limit in PROFILE_PERCENT_FIELDS}:
            try:
                val = float(raw)
            except (TypeError, ValueError):
                app.status_var.set(f"{name}：请输入有效百分比")
                return
            limit = dict((n, bound) for _, n, bound in PROFILE_PERCENT_FIELDS)[name]
            if not 0 <= val <= limit:
                app.status_var.set(f"{name}：需要在 0–{limit:g}% 范围")
                return
            setattr(app.settings, name, val)
        elif name == "layout_reading_label":
            selected = next(
                (key for key, label in READING_LABELS.items() if label == raw), None
            )
            if selected is None:
                return
            apply_reading_choice(app.settings, selected)
        elif name == "profile_indent_label":
            if raw not in INDENT_TYPE_CHOICES:
                return
            apply_indent_type_label(app.settings, raw)
        elif name in {"profile_header_mode", "profile_footer_mode", "profile_side_content_mode"}:
            labels = next(mapping for _, field, mapping in PROFILE_TEMPLATE_FIELDS if field == name)
            selected = labels.get(raw)
            if selected is None:
                return
            setattr(app.settings, name, selected)
            if name == "profile_side_content_mode":
                app.settings.profile_page_pair_mode = (
                    "alternate" if selected in {"outer", "inner"} else "same"
                )
        elif name == "profile_first_page_variant":
            if raw not in {"A", "B"}:
                return
            app.settings.profile_first_page_variant = raw
        else:
            setattr(app.settings, name, raw)

        if name not in {"dictionary_full_name", "dictionary_abbreviation",
                        "dictionary_isbn", "dictionary_body_page_range"}:
            app.settings.profile_setup_version = max(
                1, int(getattr(app.settings, "profile_setup_version", 0) or 0),
            )
        if app.project is not None:
            app.save_settings()
        if name in {
            "layout_reading_label", "profile_indent_label",
            "profile_header_mode", "profile_header_percent",
            "profile_footer_mode", "profile_footer_percent",
            "profile_side_content_mode", "profile_side_percent",
            "profile_side_percent_a", "profile_side_percent_b",
            "profile_first_page_variant",
        }:
            app.sync_quick_settings()
            app.redraw()
        refresh_enabled()

    def choice(name: str, title: str, values: tuple[str, ...]) -> None:
        frame = row()
        caption(frame, title, 15)
        variable = tk.StringVar()
        profile_vars[name] = variable
        combo = ttk.Combobox(
            frame, textvariable=variable, values=values, state="readonly",
        )
        combo.pack(side="left", fill="x", expand=True, padx=0, pady=0)
        combo.bind("<<ComboboxSelected>>", lambda _e, key=name: save_field(key))
        profile_buttons[name] = combo

    # Project metadata: all four fields are the original Profile setting keys.
    for title, key in PROFILE_TEXT_FIELDS:
        text_field(key, title)
    choice("layout_reading_label", "阅读方式", tuple(READING_LABELS.values()))
    choice("profile_indent_label", "缩进版式", INDENT_TYPE_CHOICES)

    _divider(panel)

    master = app.quick_bool_vars.get("ordinary_auto_layout")
    if master is None:
        master = tk.BooleanVar(value=bool(app.settings.ordinary_auto_layout))
        app.quick_bool_vars["ordinary_auto_layout"] = master

    def refresh_enabled() -> None:
        state = "normal" if bool(master.get()) else "disabled"
        for widget in auto_buttons:
            widget.configure(state=state)
        modes = {
            "profile_header_percent": (
                app.settings.profile_header_mode == "present"
            ),
            "profile_footer_percent": (
                app.settings.profile_footer_mode == "present"
            ),
            "profile_side_percent": (
                app.settings.profile_side_content_mode in {"left", "right"}
            ),
            "profile_side_percent_a": (
                app.settings.profile_side_content_mode in {"outer", "inner"}
            ),
            "profile_side_percent_b": (
                app.settings.profile_side_content_mode in {"outer", "inner"}
            ),
        }
        for name, enabled in modes.items():
            widget = profile_buttons.get(name)
            if widget is not None:
                widget.configure(state="normal" if enabled else "disabled")
        first = profile_buttons.get("profile_first_page_variant")
        if first is not None:
            first.configure(state="readonly" if app.settings.profile_page_pair_mode == "alternate"
                            else "disabled")

    auto_row = row()
    ttk.Checkbutton(
        auto_row, text="使用自动版面参数", variable=master,
        command=lambda: (app._quick_parameter_changed(), refresh_enabled()),
    ).pack(side="left", padx=0, pady=(0, 2))
    # Existing manual detector: it works on the selected page range and writes
    # the seven supported layout fields back to the shared settings/quick vars.
    # This action is independent of the per-page automatic drawing switches.
    detect_button = ttk.Button(
        auto_row, text="自动检测", command=app.detect_layout_current,
        style="PC.Compact.TButton",
    )
    detect_button.pack(side="left", padx=(5, 0), pady=(0, 2))
    app._attach_tooltip(
        detect_button,
        "按页面列表所选范围检测并填充：正文栏数、正文起始Y、首栏X、单栏宽、"
        "栏间空、典型单行字高、典型行间空白。多页取稳健中位数；"
        "正文缩进/微调判据仅在原先随字高自动计算时联动更新，"
        "不写入页底Y或修改Profile的页眉/页尾模板。",
    )

    for title, name, auto_name in LAYOUT_ROWS:
        frame = row()
        if auto_name is None:
            # Noninteractive visual placeholder: these two parameters do not
            # have an automatic-detection policy in the backend.
            ttk.Checkbutton(
                frame, state="disabled",
                variable=tk.BooleanVar(value=False),
            ).pack(side="left", padx=0, pady=0)
        else:
            variable = app.quick_bool_vars.get(auto_name)
            if variable is None:
                variable = tk.BooleanVar(value=bool(getattr(app.settings, auto_name)))
                app.quick_bool_vars[auto_name] = variable
            checkbox = ttk.Checkbutton(
                frame, variable=variable,
                command=app._quick_parameter_changed,
            )
            checkbox.pack(side="left", padx=0, pady=0)
            auto_buttons.append(checkbox)

        # Reserve space for the scrollbar on small windows: label, percent,
        # pixels and unit suffixes still fit one line in a 280px palette.
        caption(frame, title, 12)
        ttk.Entry(
            frame, textvariable=app.quick_vars[name],
            width=7 if name != "columns" else 5,
            justify="center",
        ).pack(side="left", padx=0, pady=0)
        if name != "columns":
            ttk.Label(frame, text="% ", width=2).pack(side="left", padx=0, pady=0)
            ttk.Entry(
                frame, textvariable=app.quick_pixel_vars[name],
                width=6, justify="center",
            ).pack(side="left", padx=0, pady=0)
            ttk.Label(frame, text="px", width=2).pack(side="left", padx=0, pady=0)

    _divider(panel)

    for title, name, labels in PROFILE_TEMPLATE_FIELDS:
        choice(name, title, tuple(labels))
        if name in {"profile_header_mode", "profile_footer_mode"}:
            percent_name = ("profile_header_percent" if name == "profile_header_mode"
                            else "profile_footer_percent")
            percent_row = row()
            caption(percent_row, "排除高度%", 15)
            percent_var = tk.StringVar()
            profile_vars[percent_name] = percent_var
            widget = ttk.Entry(percent_row, textvariable=percent_var, width=8)
            widget.pack(side="left", padx=0, pady=0)
            widget.bind("<Return>", lambda _e, n=percent_name: save_field(n))
            widget.bind("<FocusOut>", lambda _e, n=percent_name: save_field(n))
            profile_buttons[percent_name] = widget

    for title, name, _maxval in PROFILE_PERCENT_FIELDS[2:]:
        frame = row()
        caption(frame, title, 15)
        variable = tk.StringVar()
        profile_vars[name] = variable
        widget = ttk.Entry(frame, textvariable=variable, width=8)
        widget.pack(side="left", padx=0, pady=0)
        widget.bind("<Return>", lambda _e, n=name: save_field(n))
        widget.bind("<FocusOut>", lambda _e, n=name: save_field(n))
        profile_buttons[name] = widget
    choice("profile_first_page_variant", "A/B起始页", ("A", "B"))

    # Reuse the live quick-setting variable also shown in 显示参数. The main
    # application's float parser, 1–100% validation and auto-save stay shared.
    ratio_row = row()
    caption(ratio_row, "向右比例%", 15)
    ttk.Entry(
        ratio_row, textvariable=app.quick_vars["right_ratio"],
        width=8, justify="center",
    ).pack(side="left", padx=0, pady=0)

    _divider(panel)
    ordinary_visual_panel = build_ordinary_visual_evidence(app, panel)

    # Sync the compact menu after Project Profile edits or project changes.
    def refresh() -> None:
        nonlocal ui_syncing
        ui_syncing = True
        previous_quick_sync = bool(getattr(app, "_quick_syncing", False))
        app._quick_syncing = True
        try:
            for _title, name in PROFILE_TEXT_FIELDS:
                profile_vars[name].set(str(getattr(app.settings, name, "")))
            profile_vars["layout_reading_label"].set(
                READING_LABELS[reading_choice_from_settings(app.settings)]
            )
            profile_vars["profile_indent_label"].set(indent_type_label(app.settings))
            for _title, field, labels in PROFILE_TEMPLATE_FIELDS:
                current = str(getattr(app.settings, field))
                profile_vars[field].set(next(
                    (label for label, value in labels.items() if value == current),
                    next(iter(labels)),
                ))
            for _title, name, _bound in PROFILE_PERCENT_FIELDS:
                profile_vars[name].set(f"{float(getattr(app.settings, name)):.2f}".rstrip("0").rstrip("."))
            profile_vars["profile_first_page_variant"].set(
                str(getattr(app.settings, "profile_first_page_variant", "A")),
            )
            for _title, _name, auto_name in LAYOUT_ROWS:
                if auto_name is not None:
                    app.quick_bool_vars[auto_name].set(bool(getattr(app.settings, auto_name)))
            master.set(bool(app.settings.ordinary_auto_layout))
        finally:
            app._quick_syncing = previous_quick_sync
            ui_syncing = False
        refresh_enabled()
        ordinary_visual_panel.refresh_from_settings()

    panel.refresh_from_settings = refresh  # type: ignore[attr-defined]
    refresh()
    return panel


__all__ = [
    "PROFILE_TEXT_FIELDS", "LAYOUT_ROWS", "PROFILE_TEMPLATE_FIELDS",
    "PROFILE_PERCENT_FIELDS", "build_layout_profile_menu",
]
