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
    follow_zoom = tk.BooleanVar(value=bool(app.settings.crop_preview_follow_zoom))
    app.quick_bool_vars["crop_preview_follow_zoom"] = follow_zoom
    ttk.Checkbutton(row, text="跟随缩放", variable=follow_zoom).pack(side="left", padx=(8, 0))


def effective_crop_preview_font_size(
    image_width: int, view_scale: float, settings: Any,
) -> int:
    """Match main text editor's 1400-pixel displayed-page reference scale."""
    base_size = max(5, int(settings.crop_preview_font_size))
    if settings.crop_preview_follow_zoom:
        font_size = round(base_size * max(1.0, image_width * view_scale) / 1400.0)
    else:
        font_size = base_size
    return max(5, min(72, font_size))


def crop_preview_font_spec(app: Any, scale: float, resolve_family: Any, entry_font_spec: Any) -> Any:
    """Resolve preview typography using the same size semantics as main editors."""
    family = resolve_family(
        app.canvas, app.settings.crop_preview_font_family, app.settings.ocr_language,
    )
    return entry_font_spec(
        family, effective_crop_preview_font_size(app.image.width, scale, app.settings),
        app.settings.crop_preview_font_bold, app.settings.crop_preview_font_italic,
    )
