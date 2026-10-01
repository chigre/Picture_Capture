from __future__ import annotations

"""Proofreading UI for the shared entry regular/oversized classification."""

from dataclasses import replace
from typing import Any
import tkinter as tk
from tkinter import ttk

from .entry_classification import (
    classified_entry_crop_height,
    get_entry_classification,
    set_entry_scale_manual,
)


_SCALE_TO_LABEL = {
    "auto": "自动",
    "regular": "普通词条",
    "oversized": "大字头",
}
_LABEL_TO_SCALE = {value: key for key, value in _SCALE_TO_LABEL.items()}
_SOURCE_LABELS = {
    "indent": "缩进",
    "symbol_sample": "符号样本",
    "large_head": "大字头",
    "ocr": "OCR",
    "manual": "人工",
    "unknown": "未知",
}


def _entry_for_active(window: Any):
    try:
        entries = list(window._bound_row_entries())
        index = int(window.active_index)
    except Exception:
        return None
    return entries[index] if 0 <= index < len(entries) else None


def _persist(window: Any) -> None:
    parent = getattr(window, "parent", None)
    if parent is None or getattr(parent, "current_page", None) is None or getattr(parent, "image", None) is None:
        return
    try:
        from .formats import pdic_path, write_pdic

        write_pdic(
            pdic_path(parent.current_page),
            parent.entries,
            parent.image.width,
            parent.pages_tuple(),
        )
    except Exception:
        # Classification editing must never make the review window unusable.
        return


def install_review_entry_classification(app_module: Any) -> None:
    """Install canonical crop semantics and a manual type selector in ReviewWindow."""
    if getattr(app_module, "_review_entry_classification_installed", False):
        return

    # Replace the old text heuristic ("one Han character == oversized") with the
    # same structural classification used by ordinary drawing and future OCR crops.
    def review_line_box(entry, geometry, image, settings, next_entry=None):
        regular_height = app_module._effective_review_regular_crop_height(settings)
        oversized_height = app_module._effective_review_single_cjk_line_height(settings)
        height = classified_entry_crop_height(
            entry,
            settings,
            regular_height=regular_height,
            oversized_height=oversized_height,
        )
        if geometry.transform.kind != "identity":
            classified_settings = replace(settings)
            classified_settings.character_height = int(height)
            return app_module.line_box(entry, geometry, image, classified_settings)

        left, _old_top, right, _bottom = app_module.line_box(entry, geometry, image, settings)
        row_padding = max(0, int(getattr(settings, "row_padding", 0) or 0))
        half_spacing = round(0.5 * row_padding)
        top = max(int(geometry.top), int(entry.y) - half_spacing)
        return left, top, right, min(int(image.height), top + max(1, int(height)))

    app_module._review_line_box = review_line_box

    ReviewWindow = app_module.ReviewWindow
    original_init = ReviewWindow.__init__
    original_request = ReviewWindow._request_render_rows
    original_set_active = ReviewWindow.set_active

    def sync_control(self) -> None:
        entry = _entry_for_active(self)
        var = getattr(self, "entry_scale_classification_var", None)
        source_var = getattr(self, "entry_source_classification_var", None)
        if var is None or source_var is None:
            return
        if entry is None:
            var.set("自动")
            source_var.set("来源：—")
            return
        meta = get_entry_classification(entry)
        var.set(_SCALE_TO_LABEL[meta.entry_scale] if meta.manual_override else "自动")
        source = _SOURCE_LABELS.get(meta.auto_entry_source, meta.auto_entry_source or "未知")
        effective = "大字头" if meta.entry_scale == "oversized" else "普通词条"
        suffix = "（人工）" if meta.manual_override else ""
        source_var.set(f"来源：{source}｜当前：{effective}{suffix}")

    def change_classification(self, _event=None) -> None:
        entry = _entry_for_active(self)
        if entry is None:
            return
        label = str(self.entry_scale_classification_var.get() or "自动")
        scale = _LABEL_TO_SCALE.get(label, "auto")
        set_entry_scale_manual(entry, None if scale == "auto" else scale)
        _persist(self)
        sync_control(self)
        try:
            self._request_render_rows(focus_index=self.active_index)
        except Exception:
            pass
        try:
            self.parent.redraw()
        except Exception:
            pass

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.entry_scale_classification_var = tk.StringVar(value="自动")
        self.entry_source_classification_var = tk.StringVar(value="来源：—")
        frame = ttk.Frame(self, padding=(6, 3))
        frame.place(relx=1.0, x=-14, y=36, anchor="ne")
        ttk.Label(frame, text="词条类型：").pack(side="left")
        combo = ttk.Combobox(
            frame,
            textvariable=self.entry_scale_classification_var,
            values=("自动", "普通词条", "大字头"),
            state="readonly",
            width=9,
        )
        combo.pack(side="left", padx=(0, 8))
        combo.bind("<<ComboboxSelected>>", self._change_entry_classification)
        ttk.Label(frame, textvariable=self.entry_source_classification_var).pack(side="left")
        self.entry_scale_classification_combo = combo
        self.entry_classification_frame = frame
        sync_control(self)

        # Fast manual corrections while proofreading.
        self.bind("<Control-Alt-Key-0>", lambda _e: _set_shortcut(self, "自动"), add="+")
        self.bind("<Control-Alt-Key-1>", lambda _e: _set_shortcut(self, "普通词条"), add="+")
        self.bind("<Control-Alt-Key-2>", lambda _e: _set_shortcut(self, "大字头"), add="+")

    def request(self, *args, **kwargs):
        sync_control(self)
        return original_request(self, *args, **kwargs)

    def set_active(self, index: int):
        result = original_set_active(self, index)
        sync_control(self)
        return result

    def _set_shortcut(self, label: str):
        self.entry_scale_classification_var.set(label)
        change_classification(self)
        return "break"

    # Improve wording of the existing global height control.  The setting value
    # remains compatible; only the UI stops implying that every single CJK word
    # is necessarily a display head.
    original_build = getattr(ReviewWindow, "_build", None)
    if callable(original_build):
        def build(self, *args, **kwargs):
            result = original_build(self, *args, **kwargs)
            try:
                stack = [self]
                while stack:
                    parent = stack.pop()
                    for child in parent.winfo_children():
                        stack.append(child)
                        try:
                            if child.cget("text") == "单字行高：":
                                child.configure(text="大字头切图高：")
                        except Exception:
                            pass
            except Exception:
                pass
            return result
        ReviewWindow._build = build

    ReviewWindow.__init__ = init
    ReviewWindow._request_render_rows = request
    ReviewWindow.set_active = set_active
    ReviewWindow._sync_entry_classification_control = sync_control
    ReviewWindow._change_entry_classification = change_classification
    ReviewWindow._set_entry_classification_shortcut = _set_shortcut
    app_module._review_entry_classification_installed = True


__all__ = ["install_review_entry_classification"]
