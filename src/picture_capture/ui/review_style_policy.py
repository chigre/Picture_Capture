"""Proofreading-window opt-in ttk theme policy.

ReviewWindow retains its original API and live theme/global bindings.
"""
from __future__ import annotations
from typing import Any


def configure_review_styles(self, deps: dict[str, Any]) -> None:
    ttk = deps["ttk"]
    appearance_palette = deps["appearance_palette"]
    """Configure dense, opt-in styles for the proofreading workspace only."""
    style = ttk.Style(self)
    base = appearance_palette(self.parent.appearance_mode)
    if self.parent.appearance_mode == "dark":
        colors = {
            "surface": base["surface"],
            "toolbar": base["surface_alt"],
            "panel": base["panel"],
            "border": base["border"],
            "text": base["text"],
            "muted": base["muted"],
            "button": base["button"],
            "button_hover": base["button_hover"],
            "primary": base["success"],
            "primary_hover": base["success_hover"],
            "danger": base["danger"],
            "danger_hover": "#4a2b30",
            "selection": base["selection"],
            "neutral_entry": base["input_bg"],
        }
    else:
        native_background = str(style.lookup("TFrame", "background") or "#f6f7f9")
        colors = {
            "surface": native_background,
            "toolbar": "#f3f4f6",
            "panel": "#f7f8fa",
            "border": "#d8dde5",
            "text": "#30343b",
            "muted": "#68707b",
            "button": "#eceff3",
            "button_hover": "#e1e5ea",
            "primary": "#5e9f69",
            "primary_hover": "#4f8e5c",
            "danger": "#9b3a3a",
            "danger_hover": "#f4d9d9",
            "selection": "#dce8f7",
            "neutral_entry": "#f4f4f4",
        }
    self._review_ui_colors = colors

    style.configure("PCR.Surface.TFrame", background=colors["surface"])
    style.configure("PCR.Toolbar.TFrame", background=colors["toolbar"])
    style.configure("PCR.Panel.TFrame", background=colors["panel"])
    style.configure(
        "PCR.SectionTitle.TLabel",
        background=colors["surface"],
        foreground=colors["text"],
        font=self.review_section_title_font,
        padding=(0, 2, 0, 1),
    )
    style.configure(
        "PCR.Toolbar.TLabel",
        background=colors["toolbar"],
        foreground=colors["text"],
    )
    style.configure(
        "PCR.Body.TLabel",
        background=colors["surface"],
        foreground=colors["text"],
    )
    style.configure(
        "PCR.Black.TLabel",
        background=colors["surface"],
        foreground="#000000" if self.parent.appearance_mode != "dark" else colors["text"],
    )
    style.configure(
        "PCR.Body.TCheckbutton",
        background=colors["surface"],
        foreground=colors["text"],
    )
    style.configure(
        "PCR.Muted.TLabel",
        background=colors["surface"],
        foreground=colors["muted"],
    )
    style.configure(
        "PCR.Header.TLabel",
        background=colors["surface"],
        foreground=colors["text"],
        font=self.review_section_title_font,
    )
    style.configure("PCR.Compact.TButton", padding=(7, 3))
    style.configure("PCR.Tool.TButton", padding=(4, 2))
    style.configure("PCR.Compact.TEntry", padding=(4, 2))
    style.configure("PCR.Compact.TSpinbox", padding=(3, 2))
    style.configure("PCR.Compact.TCombobox", padding=(3, 2))
    style.configure("PCR.Crop.TLabel", background=colors["surface"])
