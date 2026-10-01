from __future__ import annotations

"""Readable text backgrounds for the Layout diagnostic overlay.

The base visualization intentionally owns all geometry and label placement.  This
module only decorates Canvas text created while that overlay is drawn, keeping
readability concerns separate from detector/layout logic.
"""

from typing import Any, Callable

from .layout_visualization_ui import draw_layout_visualization


_RED_TEXT = {"#d32f2f", "#b00020"}
_BLUE_TEXT = {"#1976d2"}
_PURPLE_TEXT = {"#7b1fa2"}


def _background_for_text(fill: object, text: object) -> tuple[str, str]:
    """Return (background, outline) matched to the overlay text category."""
    color = str(fill or "").lower()
    value = str(text or "")
    if color in _RED_TEXT:
        return "#ffebee", color
    if color in _BLUE_TEXT:
        return "#e3f2fd", color
    if color in _PURPLE_TEXT:
        return "#f3e5f5", color
    if "Layout " in value or "method:" in value or "confidence:" in value:
        return "#fffde7", "#757575"
    return "#ffffff", "#9e9e9e"


def draw_layout_visualization_readable(app: Any) -> None:
    """Draw Layout overlay with a solid, matching background behind every label."""
    canvas = getattr(app, "canvas", None)
    if canvas is None:
        return

    original_create_text: Callable[..., Any] = canvas.create_text

    def create_text_with_background(*args: Any, **kwargs: Any) -> Any:
        text_id = original_create_text(*args, **kwargs)
        try:
            bbox = canvas.bbox(text_id)
            if bbox is None:
                return text_id
            background, outline = _background_for_text(
                kwargs.get("fill"), kwargs.get("text")
            )
            tags = kwargs.get("tags", ())
            pad_x = 4
            pad_y = 2
            rect_id = canvas.create_rectangle(
                bbox[0] - pad_x,
                bbox[1] - pad_y,
                bbox[2] + pad_x,
                bbox[3] + pad_y,
                fill=background,
                outline=outline,
                width=1,
                tags=tags,
            )
            canvas.tag_lower(rect_id, text_id)
        except Exception:
            # Readability decoration must never break the diagnostic overlay.
            pass
        return text_id

    canvas.create_text = create_text_with_background
    try:
        draw_layout_visualization(app)
    finally:
        canvas.create_text = original_create_text
