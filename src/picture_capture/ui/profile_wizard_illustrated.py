"""Small illustrated-layout selector for the existing Project Profile wizard.

The wizard continues to own its working AppSettings snapshot. This widget
merely changes that snapshot; save/confirmation follows the existing wizard
transaction and never overwrites PDIC or page-level illustrated annotations.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .illustrated_profile_menu import KIND_LABELS
from ..illustrated_profile import KINDS


def add_wizard_layout_selector(wizard, tab: ttk.Frame, *, row: int) -> None:
    frame = ttk.LabelFrame(tab, text="词典版式", padding=8)
    frame.grid(row=row, column=0, sticky="ew", pady=(10, 5))
    kind = getattr(wizard.working, "dictionary_layout_kind", "traditional")
    current = tk.StringVar(value=KIND_LABELS.get(kind, KIND_LABELS["traditional"]))
    widget = ttk.Combobox(frame, textvariable=current, state="readonly",
                          values=tuple(KIND_LABELS.values()))
    widget.pack(fill="x")
    ttk.Label(
        frame,
        text="图解页使用自由文字框与多语言 OCR，不依赖栏数或传统画线。"
             "多语言与逐页版式参数在【一、版面参数】中管理；混合模式默认普通页。",
        wraplength=getattr(wizard, "_wizard_left_width", 350) - 55,
        justify="left",
    ).pack(fill="x", pady=(5, 0))

    def change(_event=None):
        selected = next((k for k, v in KIND_LABELS.items() if v == current.get()), None)
        if selected not in KINDS:
            return
        wizard.working.dictionary_layout_kind = selected
        wizard._profile_revision += 1
        wizard._refresh_summary()

    widget.bind("<<ComboboxSelected>>", change)
    wizard.dictionary_layout_kind_var = current
