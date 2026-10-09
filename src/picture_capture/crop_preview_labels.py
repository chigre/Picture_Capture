"""Legible, non-interactive labels for the main crop-plan preview."""
from __future__ import annotations

from typing import Any


def format_crop_preview_entry_label(word: str, filename: str) -> str:
    """Show the headword and its output image name on the same preview line."""
    word = str(word or "").replace(chr(13), " ").replace(chr(10), " ").strip()
    filename = str(filename or "").replace(chr(13), " ").replace(chr(10), " ").strip()
    return f"{word}  |  {filename}" if word else filename


def draw_crop_preview_label(
    canvas: Any, x: float, y: float, *, text: str,
    outline: str, font: Any, anchor: str = "n", justify: str = "center",
) -> tuple[Any, Any | None]:
    """Keep foreground text readable on dense scans using a bordered paper badge."""
    label = canvas.create_text(
        x, y, text=text, fill="#19232d", anchor=anchor,
        justify=justify, font=font, tags=("crop-plan",),
    )
    bbox = canvas.bbox(label)
    if bbox is None:
        return label, None
    x0, y0, x1, y1 = bbox
    backing = canvas.create_rectangle(
        x0 - 4, y0 - 3, x1 + 4, y1 + 3,
        fill="#f8fafc", outline=outline, width=1,
        tags=("crop-plan",),
    )
    canvas.tag_lower(backing, label)
    return label, backing
