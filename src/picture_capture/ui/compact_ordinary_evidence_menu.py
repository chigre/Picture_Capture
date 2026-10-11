"""Ordinary-mode CJK and visual symbol evidence, shared with Project Profile."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from ..profile_setup import _visual_marker_capture_defaults
from ..visual_marker_templates import (
    parse_visual_marker_samples, serialize_visual_marker_samples,
)
from ..visual_marker_ui import VisualMarkerCaptureDialog, VisualMarkerSamplesDialog
from .compact_profile_persistence import (
    persist_profile_changes, profile_changes_allowed,
)


def replace_marker_samples(app: Any, samples: list[dict]) -> None:
    """Use the exact JSON sample collection stored by Project Profile."""
    if not profile_changes_allowed(app):
        return
    app.settings.profile_symbol_template_version = 1
    app.settings.profile_symbol_templates_json = serialize_visual_marker_samples(samples)
    persist_profile_changes(app)


def build_ordinary_visual_evidence(app: Any, parent: tk.Misc) -> ttk.Frame:
    panel = ttk.Frame(parent)
    panel.pack(fill="x")
    ttk.Label(
        panel, text="普通模式画线：视觉词头证据",
        font=("TkDefaultFont", 10, "bold"),
    ).pack(anchor="w", pady=(3, 5))

    enabled = tk.BooleanVar()
    threshold = tk.StringVar()
    count = tk.StringVar()

    def samples() -> list[dict]:
        return parse_visual_marker_samples(
            app.settings.profile_symbol_templates_json
        )

    def refresh() -> None:
        enabled.set(bool(app.settings.profile_cjk_allow_single_headword))
        threshold.set(f"{float(app.settings.profile_symbol_template_threshold):.2f}")
        current = samples()
        count.set(f"已保存视觉符号样本：{len(current)}")

    def update_enabled() -> None:
        if not profile_changes_allowed(app):
            refresh()
            return
        app.settings.profile_parser_controls_version = 1
        app.settings.profile_cjk_allow_single_headword = bool(enabled.get())
        persist_profile_changes(app)

    ttk.Checkbutton(
        panel, text="启用大字头detector（CJK）",
        variable=enabled, command=update_enabled,
    ).pack(anchor="w", pady=(1, 4))
    ttk.Label(panel, text="特定符号视觉样本：").pack(anchor="w")
    ttk.Label(panel, textvariable=count).pack(anchor="w", pady=(1, 2))

    def changed(samples_list: list[dict]) -> None:
        replace_marker_samples(app, [dict(item) for item in samples_list])
        refresh()

    def captured(item: dict) -> None:
        original = samples()
        sample_id = str(item.get("id") or "")
        if sample_id:
            original = [
                sample for sample in original
                if str(sample.get("id") or "") != sample_id
            ]
        changed([*original, dict(item)])

    def capture() -> None:
        project = getattr(app, "project", None)
        if project is None or not project.images:
            messagebox.showinfo("无法采样", "请先打开有图片的词典项目。", parent=app)
            return
        initial_role, literal = _visual_marker_capture_defaults(
            marker_prefix_enabled=bool(app.settings.profile_allow_marker_prefix),
            bracket_enabled=bool(app.settings.profile_cjk_allow_bracketed_headword),
            entry_text=app.settings.profile_entry_marker_symbols,
            bracket_text=app.settings.profile_bracket_open_symbols,
        )
        VisualMarkerCaptureDialog(
            app, project.images,
            initial_index=max(0, int(getattr(app, "current_index", 0))),
            initial_role=initial_role, initial_literal=literal,
            on_saved=captured,
        )

    def show_samples() -> None:
        current = samples()
        if not current:
            messagebox.showinfo(
                "视觉标记样本", "尚未保存样本。请先从页面采样。", parent=app,
            )
            return
        VisualMarkerSamplesDialog(app, current, on_changed=changed)

    buttons = ttk.Frame(panel)
    buttons.pack(fill="x", pady=(1, 3))
    ttk.Button(buttons, text="从页面采样...", command=capture).pack(side="left")
    ttk.Button(buttons, text="查看/删除样本", command=show_samples).pack(
        side="left", padx=(5, 0),
    )

    def save_threshold(_event: tk.Event | None = None) -> None:
        raw = threshold.get().strip()
        try:
            value = float(raw)
            if not 0.35 <= value <= 0.95:
                raise ValueError(raw)
        except ValueError:
            app.status_var.set("匹配阈值必须是 0.35–0.95 之间的数字")
            refresh()
            return
        if not profile_changes_allowed(app):
            refresh()
            return
        app.settings.profile_symbol_template_version = 1
        app.settings.profile_symbol_template_threshold = value
        persist_profile_changes(app)
        refresh()

    bottom = ttk.Frame(panel)
    bottom.pack(fill="x", pady=(2, 3))
    ttk.Label(bottom, text="匹配阈值").pack(side="left", padx=(0, 4))
    field = ttk.Entry(bottom, textvariable=threshold, width=7, justify="center")
    field.pack(side="left")
    field.bind("<Return>", save_threshold)
    field.bind("<FocusOut>", save_threshold)
    panel.refresh_from_settings = refresh  # type: ignore[attr-defined]
    refresh()
    return panel
