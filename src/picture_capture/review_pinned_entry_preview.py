"""Pinned source-resolution context crop for the active proofreading entry.

The crop is twice the height of the existing proofreading crop and remains
outside the scrolling crop/text editor. Classification is not a UI setting.
"""
from __future__ import annotations

import importlib
from typing import Any
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk


def doubled_crop_box(box: tuple[int, int, int, int], image_height: int) -> tuple[int, int, int, int]:
    """Double crop height about its centre; shift inward at image boundaries."""
    x0, y0, x1, y1 = map(int, box)
    limit = max(1, int(image_height))
    height = max(1, y1 - y0)
    target = min(limit, height * 2)
    start = max(0, min(limit - target, (y0 + y1 - target) // 2))
    return x0, start, x1, start + target


def initialize_pinned_entry_preview(window: Any) -> None:
    """Insert preview above (not inside) the independently scrolling rows."""
    if getattr(window, "active_entry_preview_label", None) is not None:
        return
    editor_area = window.review_editor_area
    host = ttk.Frame(editor_area, style="PCR.Surface.TFrame")
    label = ttk.Label(host, style="PCR.Crop.TLabel", anchor="center")
    label.pack(fill="x", padx=6)
    host.pack(fill="x", before=window.canvas, pady=(0, 4))
    window.active_entry_preview_host = host
    window.active_entry_preview_label = label
    window.active_entry_preview_photo = None
    window.active_entry_preview_key = None

    def resized(_event: tk.Event) -> None:
        # Deferred so the available width has finished changing.
        pending = getattr(window, "_active_preview_resize_job", None)
        if pending is not None:
            try:
                window.after_cancel(pending)
            except tk.TclError:
                pass
        window._active_preview_resize_job = window.after(
            120, lambda: refresh_pinned_entry_preview(window, force=True)
        )

    editor_area.bind("<Configure>", resized, add="+")
    refresh_pinned_entry_preview(window)


def refresh_pinned_entry_preview(window: Any, *, force: bool = False) -> None:
    """Refresh only the active image; never create a text input or change data."""
    label = getattr(window, "active_entry_preview_label", None)
    if label is None:
        return
    parent = getattr(window, "parent", None)
    page = getattr(parent, "current_page", None)
    source = getattr(parent, "image", None)
    if page is None or source is None:
        label.configure(image="")
        window.active_entry_preview_photo = None
        window.active_entry_preview_key = None
        return
    try:
        entries = list(window._bound_row_entries())
        index = int(window.active_index)
        if not (0 <= index < len(entries)):
            raise IndexError(index)
        entry = entries[index]
        next_entry = entries[index + 1] if index + 1 < len(entries) else None
        available = max(1, int(window.review_editor_area.winfo_width()) - 16)
        key = (str(page), index, int(entry.x), int(entry.y), available,
               id(source), int(getattr(parent, "current_index", 0)))
        if not force and key == getattr(window, "active_entry_preview_key", None):
            return

        # Use the same actual crop geometry as ordinary review rows.
        app = importlib.import_module(type(window).__module__)
        review_settings, geometry = app._review_crop_context(
            source, parent.settings, max(1, int(parent.canvas.winfo_width())),
            int(parent.current_index),
        )
        box = app._review_line_box(entry, geometry, source, review_settings, next_entry)
        doubled = doubled_crop_box(box, source.height)
        crop = source.crop(doubled).convert("RGB")
        # Preserve image aspect ratio, and do not magnify smaller crops.
        if crop.width > available:
            height = max(1, round(crop.height * available / crop.width))
            crop = crop.resize((available, height), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(app.themed_display_image(crop, parent.appearance_mode))
        label.configure(image=photo)
        window.active_entry_preview_photo = photo
        window.active_entry_preview_key = key
    except (AttributeError, IndexError, TypeError, ValueError, tk.TclError, OSError):
        label.configure(image="")
        window.active_entry_preview_photo = None
        window.active_entry_preview_key = None
