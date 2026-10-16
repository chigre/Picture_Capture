"""Compact Project Profile controls for illustrated and mixed dictionary pages."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ..illustrated_profile import (
    GROUPING, KINDS, PAGE_KINDS, effective_page_kind, set_page_kind,
    validate_illustrated_preferences,
)
from .compact_profile_persistence import persist_profile_changes, profile_changes_allowed

KIND_LABELS = {
    "traditional": "传统词典（栏位/画线）",
    "illustrated": "图解词典（自由文字框）",
    "mixed": "混合词典（逐页指定）",
}
PAGE_LABELS = {
    "default": "项目默认（传统）",
    "traditional": "传统词典",
    "illustrated": "图解词典",
}
GROUP_LABELS = {
    "strict": "严格（减少错误合并）",
    "auto": "自动（平衡）",
    "loose": "宽松（归并更积极）",
}


def build_illustrated_profile_controls(app: Any, parent: ttk.Frame):
    """Build explicit validated Profile controls; return one sync callback."""
    root = ttk.Frame(parent)
    root.pack(fill="x", padx=2, pady=3)
    values: dict[str, tk.Variable] = {}

    def line(label: str) -> ttk.Frame:
        frame = ttk.Frame(root)
        frame.pack(fill="x", pady=3)
        ttk.Label(frame, text=label, width=16).pack(side="left")
        return frame

    def commit(field: str, transform=lambda value: value) -> None:
        if updating[0] or not profile_changes_allowed(app):
            return
        previous = getattr(app.settings, field)
        try:
            candidate = transform(values[field].get())
            setattr(app.settings, field, candidate)
            validate_illustrated_preferences(app.settings)
        except (TypeError, ValueError) as exc:
            setattr(app.settings, field, previous)
            app.status_var.set(f"图解 PROFILE 参数无效：{exc}")
            refresh()
            return
        persist_profile_changes(app)

    def text_field(field: str, label: str, *, caster=str) -> None:
        frame = line(label)
        variable = tk.StringVar()
        values[field] = variable
        widget = ttk.Entry(frame, textvariable=variable, width=25)
        widget.pack(side="left", fill="x", expand=True)
        widget.bind("<Return>", lambda _e: commit(field, caster))
        widget.bind("<FocusOut>", lambda _e: commit(field, caster))

    def choice(field: str, label: str, labels: dict[str, str]) -> None:
        frame = line(label)
        variable = tk.StringVar()
        values[field] = variable
        widget = ttk.Combobox(frame, textvariable=variable,
                              state="readonly", values=tuple(labels.values()))
        widget.pack(side="left", fill="x", expand=True)
        widget.bind("<<ComboboxSelected>>", lambda _e: commit(
            field, lambda v: next(k for k, label in labels.items() if label == v)
        ))

    def checkbox(field: str, label: str) -> None:
        variable = tk.BooleanVar()
        values[field] = variable
        ttk.Checkbutton(root, text=label, variable=variable,
                        command=lambda: commit(field, bool)).pack(anchor="w", pady=2)

    def percent_field(field: str, label: str) -> None:
        text_field(field, label, caster=float)

    updating = [False]
    choice("illustrated_grouping_mode", "文字组归并", GROUP_LABELS)
    text_field("illustrated_primary_language", "主索引语言")
    text_field("illustrated_ocr_languages", "OCR 语言集合")
    text_field("illustrated_group_max_lines", "每组最大行数", caster=int)
    checkbox("illustrated_require_review", "OCR 文字组必须审核后保存")
    checkbox("illustrated_export_split_aliases", "默认导出多语言拆分索引")
    percent_field("illustrated_ocr_top_percent", "顶部排除 %")
    percent_field("illustrated_ocr_bottom_percent", "底部排除 %")
    percent_field("illustrated_ocr_side_percent", "两侧排除 %")
    ttk.Separator(root).pack(fill="x", pady=(9, 6))
    ttk.Label(root, text="图解对象 · 网格、标尺与智能吸附").pack(anchor="w")
    checkbox("illustrated_grid_visible", "显示网格")
    text_field("illustrated_grid_x", "水平间距 px", caster=int)
    text_field("illustrated_grid_y", "垂直间距 px", caster=int)
    text_field("illustrated_grid_subdivisions", "网格细分数", caster=int)
    text_field("illustrated_grid_origin_x", "网格原点 X", caster=int)
    text_field("illustrated_grid_origin_y", "网格原点 Y", caster=int)
    text_field("illustrated_grid_color", "网格颜色 #")
    text_field("illustrated_guide_color", "辅助线颜色 #")
    text_field("illustrated_grid_opacity", "网格不透明度 %", caster=int)
    checkbox("illustrated_guides_visible", "显示水平/垂直辅助线")
    checkbox("illustrated_guides_locked", "锁定辅助线")
    checkbox("illustrated_snap_grid", "吸附到网格")
    checkbox("illustrated_snap_guides", "吸附到辅助线")
    checkbox("illustrated_snap_objects", "智能吸附到其他文字框")
    text_field("illustrated_snap_tolerance", "吸附距离 屏幕px", caster=int)
    text_field("illustrated_nudge_step", "方向键微移 px", caster=int)
    text_field("illustrated_history_depth", "撤销历史步数", caster=int)
    ttk.Label(root, text="在主图上 Shift 从上方标尺拖出垂直线，"
              "从左侧标尺拖出水平线；右键可增加/清空线，"
              "并操作对齐、分布、组合与锁定。",
              justify="left", wraplength=285).pack(fill="x", pady=4)
    ttk.Separator(root).pack(fill="x", pady=(8, 5))
    ttk.Label(root, text="OCR 语言以 + 或逗号分隔，如 eng+fra+deu+jpn+chi_sim。\n"
              "多语言须启用已安装语言包的本地 Tesseract；Paddle 单模型不会被当作多语言模型。",
              justify="left", wraplength=285).pack(fill="x", pady=4)

    def refresh():
        updating[0] = True
        try:
            for field, var in values.items():
                value = getattr(app.settings, field)
                if field == "illustrated_grouping_mode":
                    value = GROUP_LABELS.get(value, GROUP_LABELS["auto"])
                elif isinstance(value, float):
                    value = f"{value:g}"
                var.set(value)
        finally:
            updating[0] = False

    root.refresh_from_settings = refresh  # type: ignore[attr-defined]
    refresh()
    return root


def build_layout_kind_control(app: Any, parent: ttk.Frame,
                              refresh_others) -> callable:
    """Global mode plus mixed per-page override; unchanged ordinary defaults."""
    frame = ttk.Frame(parent)
    frame.pack(fill="x", pady=(4, 5))
    ttk.Label(frame, text="词典版式", width=15).pack(side="left")
    kind_var = tk.StringVar()
    combo = ttk.Combobox(frame, textvariable=kind_var, state="readonly",
                         values=tuple(KIND_LABELS.values()))
    combo.pack(side="left", fill="x", expand=True)

    page_frame = ttk.Frame(parent)
    page_frame.pack(fill="x", pady=3)
    ttk.Label(page_frame, text="当前页版式", width=15).pack(side="left")
    page_var = tk.StringVar()
    page_combo = ttk.Combobox(page_frame, textvariable=page_var,
                              state="readonly", values=tuple(PAGE_LABELS.values()))
    page_combo.pack(side="left", fill="x", expand=True)
    info_var = tk.StringVar()
    info_label = ttk.Label(parent, textvariable=info_var, wraplength=295)
    info_label.pack(fill="x")

    updating = [False]

    def refresh():
        updating[0] = True
        try:
            mode = getattr(app.settings, "dictionary_layout_kind", "traditional")
            kind_var.set(KIND_LABELS.get(mode, KIND_LABELS["traditional"]))
            mixed = mode == "mixed"
            if mixed:
                page_frame.pack(fill="x", pady=3, before=info_label)
            else:
                page_frame.pack_forget()
            page = getattr(app, "current_page", None)
            overrides = getattr(app.settings, "illustrated_page_overrides", {}) or {}
            override = overrides.get(page.name, "default") if page is not None else "default"
            page_var.set(PAGE_LABELS.get(override, PAGE_LABELS["default"]))
            info_var.set(f"当前页：{effective_page_kind(app.settings, page)}；"
                         "切换版式不会删除该页已保存的另一类标注。")
        finally:
            updating[0] = False
        refresh_others()

    def set_kind(_event=None):
        if updating[0] or not profile_changes_allowed(app):
            return
        label = kind_var.get()
        key = next((kind for kind, text in KIND_LABELS.items() if text == label), None)
        if key not in KINDS:
            return
        old = app.settings.dictionary_layout_kind
        app.settings.dictionary_layout_kind = key
        try:
            validate_illustrated_preferences(app.settings)
        except ValueError:
            app.settings.dictionary_layout_kind = old
            refresh()
            return
        persist_profile_changes(app)
        refresh()

    def set_page(_event=None):
        if updating[0] or not profile_changes_allowed(app):
            return
        page = getattr(app, "current_page", None)
        key = next((kind for kind, text in PAGE_LABELS.items() if text == page_var.get()), None)
        if page is None or key not in (*PAGE_KINDS, "default"):
            return
        set_page_kind(app.settings, page, key)
        persist_profile_changes(app)
        refresh()

    combo.bind("<<ComboboxSelected>>", set_kind)
    page_combo.bind("<<ComboboxSelected>>", set_page)
    return refresh
