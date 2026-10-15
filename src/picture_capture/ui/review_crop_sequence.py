"""Index badges beside ReviewWindow inline crops.

A crop and its sequence badge are children of the same disposable row widget.
The badge is presentation only; ReviewWindow's existing Entry identity, sorted
order and deletion/re-render path remain the sole authority for numbering.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font, ttk
from typing import Any

from ..overlay_layout_helpers import effective_main_overlay_font_size
from ..review_text_helpers import _entry_font_spec
from ..ui_compat import resolve_content_font_family


def _main_sequence_font(review: Any) -> tuple:
    """Match the main-canvas neutral index badge, not the review editor font."""
    app = review.parent
    settings = app.settings
    family = resolve_content_font_family(
        review, settings.main_entry_font_family, settings.ocr_language,
    )
    image_width = int(app.image.width) if app.image is not None else 1400
    main_font_size = effective_main_overlay_font_size(
        image_width, app.view_scale, settings,
    )
    return _entry_font_spec(
        family, max(8, round(main_font_size * 0.65)), False, False,
    )


def review_sequence_gutter(review: Any) -> int:
    """Exact pixel room for the left-side badge at automatic crop zoom."""
    if getattr(review, "_filter_rows_active", False):
        return 0
    app = review.parent
    total = len(getattr(app, "entries", ()) or ())
    if not total:
        return 0
    text = app._entry_sequence_text(total - 1, total)
    badge_font = font.Font(root=review, font=_main_sequence_font(review))
    # 2px padding per side mirrors the main badge; 3px separates image/number.
    return max(0, int(badge_font.measure(text)) + 4 + 3)


def create_review_crop_with_index(
    review: Any, rows: ttk.Frame, *, photo: Any, index: int, total: int,
) -> tuple[ttk.Label, tk.Label, ttk.Frame]:
    """Render one review crop with its main-style number aligned at its foot."""
    host = ttk.Frame(rows, style="PCR.Surface.TFrame")
    host.grid(row=index * 2, column=0, sticky="ew", padx=6, pady=(8, 0))
    host.columnconfigure(1, weight=1)

    sequence = tk.Label(
        host,
        text=review.parent._entry_sequence_text(index, total),
        bg="#e6e6e6",
        fg="#000000",
        bd=0, padx=2, pady=0,
        font=_main_sequence_font(review),
    )
    sequence._pc_skip_classic_appearance = True
    sequence.grid(row=0, column=0, sticky="s", padx=(0, 3))

    picture = ttk.Label(host, image=photo, style="PCR.Crop.TLabel")
    picture.grid(row=0, column=1, sticky="w")

    for widget in (host, sequence):
        widget.bind("<MouseWheel>", review.scroll_rows)
        widget.bind("<Button-4>", lambda _event: review.scroll_rows_linux(-1))
        widget.bind("<Button-5>", lambda _event: review.scroll_rows_linux(1))
    return picture, sequence, host
