"""Settings-panel controls for independent crop-preview label typography."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable


def add_crop_preview_font_controls(
    app: Any,
    parent: Any,
    content_font_values: tuple[str, ...],
    normalize_family: Callable[[str], str],
) -> None:
    """Build the crop-preview-only font row without growing legacy app.py."""
    row = ttk.Frame(parent)
    row.grid(row=9, column=0, columnspan=4, sticky="ew", pady=(3, 0))
    ttk.Label(row, text="切图预览标签字体").pack(side="left")
    family = tk.StringVar(value=normalize_family(app.settings.crop_preview_font_family))
    app.quick_vars["crop_preview_font_family"] = family
    app.quick_field_casts["crop_preview_font_family"] = str
    ttk.Combobox(row, textvariable=family, values=content_font_values, width=18).pack(side="left")
    ttk.Label(row, text="字号").pack(side="left", padx=(8, 2))
    size = tk.StringVar(value=str(app.settings.crop_preview_font_size))
    app.quick_vars["crop_preview_font_size"] = size
    app.quick_field_casts["crop_preview_font_size"] = int
    ttk.Entry(row, textvariable=size, width=5, justify="left").pack(side="left")
    for label, name in (("粗体", "crop_preview_font_bold"), ("斜体", "crop_preview_font_italic")):
        var = tk.BooleanVar(value=bool(getattr(app.settings, name)))
        app.quick_bool_vars[name] = var
        ttk.Checkbutton(row, text=label, variable=var).pack(side="left", padx=(7, 0))


def crop_preview_font_spec(app: Any, scale: float, resolve_family: Any, entry_font_spec: Any) -> Any:
    """Render preview labels independently from main editing widget typography."""
    family = resolve_family(
        app.canvas, app.settings.crop_preview_font_family, app.settings.ocr_language,
    )
    return entry_font_spec(
        family, max(5, round(app.settings.crop_preview_font_size * scale)),
        app.settings.crop_preview_font_bold, app.settings.crop_preview_font_italic,
    )
