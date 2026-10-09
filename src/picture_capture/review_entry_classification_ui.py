from __future__ import annotations

"""Static proofreading UI helpers for entry regular/oversized classification."""

from typing import Any
import tkinter as tk
from tkinter import ttk

from .entry_classification import (
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
    if (
        parent is None
        or getattr(parent, "current_page", None) is None
        or getattr(parent, "image", None) is None
    ):
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


def sync_review_entry_classification(window: Any) -> None:
    """Synchronize the manual selector with the active Entry classification."""
    entry = _entry_for_active(window)
    var = getattr(window, "entry_scale_classification_var", None)
    source_var = getattr(window, "entry_source_classification_var", None)
    if var is None or source_var is None:
        return
    if entry is None:
        var.set("自动")
        source_var.set("来源：—")
        return

    meta = get_entry_classification(entry)
    var.set(_SCALE_TO_LABEL[meta.entry_scale] if meta.manual_override else "自动")
    source = _SOURCE_LABELS.get(
        meta.auto_entry_source,
        meta.auto_entry_source or "未知",
    )
    effective = "大字头" if meta.entry_scale == "oversized" else "普通词条"
    suffix = "（人工）" if meta.manual_override else ""
    source_var.set(f"来源：{source}｜当前：{effective}{suffix}")


def change_review_entry_classification(window: Any, _event: Any | None = None) -> None:
    """Persist one manual classification change and refresh both review surfaces."""
    entry = _entry_for_active(window)
    if entry is None:
        return
    label = str(window.entry_scale_classification_var.get() or "自动")
    scale = _LABEL_TO_SCALE.get(label, "auto")
    set_entry_scale_manual(entry, None if scale == "auto" else scale)
    _persist(window)
    sync_review_entry_classification(window)
    try:
        window._request_render_rows(focus_index=window.active_index)
    except Exception:
        pass
    try:
        window.parent.redraw()
    except Exception:
        pass


def set_review_entry_classification_shortcut(window: Any, label: str) -> str:
    """Apply one keyboard-selected classification label."""
    window.entry_scale_classification_var.set(label)
    change_review_entry_classification(window)
    return "break"


def initialize_review_entry_classification(window: Any) -> None:
    """Add the manual Entry classification control to one ReviewWindow."""
    if getattr(window, "entry_classification_frame", None) is not None:
        return

    window.entry_scale_classification_var = tk.StringVar(value="自动")
    window.entry_source_classification_var = tk.StringVar(value="来源：—")
    frame = ttk.Frame(window, padding=(6, 3))
    frame.place(relx=1.0, x=-14, y=36, anchor="ne")
    ttk.Label(frame, text="词条类型：").pack(side="left")
    combo = ttk.Combobox(
        frame,
        textvariable=window.entry_scale_classification_var,
        values=("自动", "普通词条", "大字头"),
        state="readonly",
        width=9,
    )
    combo.pack(side="left", padx=(0, 8))
    combo.bind(
        "<<ComboboxSelected>>",
        lambda event: change_review_entry_classification(window, event),
    )
    ttk.Label(
        frame,
        textvariable=window.entry_source_classification_var,
    ).pack(side="left")
    window.entry_scale_classification_combo = combo
    window.entry_classification_frame = frame

    # Fast manual corrections while proofreading.
    window.bind(
        "<Control-Alt-Key-0>",
        lambda _event: set_review_entry_classification_shortcut(window, "自动"),
        add="+",
    )
    window.bind(
        "<Control-Alt-Key-1>",
        lambda _event: set_review_entry_classification_shortcut(window, "普通词条"),
        add="+",
    )
    window.bind(
        "<Control-Alt-Key-2>",
        lambda _event: set_review_entry_classification_shortcut(window, "大字头"),
        add="+",
    )
    sync_review_entry_classification(window)


def install_review_entry_classification(app_module: Any) -> None:
    """Compatibility no-op; Review classification wiring is static."""
    _ = app_module


__all__ = [
    "change_review_entry_classification",
    "initialize_review_entry_classification",
    "install_review_entry_classification",
    "set_review_entry_classification_shortcut",
    "sync_review_entry_classification",
]
