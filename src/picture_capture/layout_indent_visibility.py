from __future__ import annotations

"""Visible physical-indent rendering and prepared-count diagnostics."""

from collections import Counter
from typing import Any


_FILL = "#fff59d"
_EDGE = "#f9a825"


def prepared_indent_counts(blocks: list[dict[str, Any]]) -> dict[int, int]:
    """Return 1-based per-column counts of drawable indent records."""
    counts: Counter[int] = Counter()
    for block in blocks:
        try:
            column = int(block.get("column", 0) or 0) + 1
            x0 = float(block["x0"])
            x1 = float(block["x1"])
            y0 = int(block["y0"])
            y1 = int(block["y1"])
        except (KeyError, TypeError, ValueError):
            continue
        if abs(x1 - x0) < 1.0 or y1 <= y0:
            continue
        counts[column] += 1
    return dict(sorted(counts.items()))


def _draw_indent_blocks_visible(app: Any, snapshot: Any) -> None:
    """Draw each measured blank span above the page with a first-ink edge."""
    from . import layout_visualization_summary as summary

    canvas = getattr(app, "canvas", None)
    if canvas is None:
        return
    indent_tag = summary._INDENT_TAG
    try:
        canvas.delete(indent_tag)
    except Exception:
        return

    var = getattr(app, "_layout_visualization_var", None)
    if var is None or not bool(var.get()):
        return

    geometry = snapshot.geometry
    scale = float(getattr(app, "view_scale", 1.0) or 1.0)
    blocks = list(getattr(app, "_layout_visualization_indent_blocks", []) or [])
    app._layout_visualization_indent_prepared_counts = prepared_indent_counts(blocks)
    if not blocks:
        return

    drawn: Counter[int] = Counter()
    for block in blocks:
        try:
            column = int(block.get("column", 0) or 0) + 1
            x0 = float(block["x0"])
            x1 = float(block["x1"])
            y0 = int(block["y0"])
            y1 = int(block["y1"])
        except (KeyError, TypeError, ValueError):
            continue
        if abs(x1 - x0) < 1.0 or y1 <= y0:
            continue

        try:
            p0 = geometry.canonical_to_source(round(x0), y0)
            p1 = geometry.canonical_to_source(round(x1), y1)
        except Exception:
            continue
        left = min(float(p0[0]), float(p1[0])) * scale
        right = max(float(p0[0]), float(p1[0])) * scale
        top = min(float(p0[1]), float(p1[1])) * scale
        bottom = max(float(p0[1]), float(p1[1])) * scale
        if right - left < 1.0 or bottom - top < 1.0:
            continue

        try:
            canvas.create_rectangle(
                left,
                top,
                right,
                bottom,
                fill=_FILL,
                outline=_EDGE,
                width=1,
                stipple="gray50",
                tags=(indent_tag,),
            )
            canvas.create_line(
                right,
                top,
                right,
                bottom,
                fill=_EDGE,
                width=2,
                tags=(indent_tag,),
            )
            drawn[column] += 1
        except Exception:
            continue

    app._layout_visualization_indent_drawn_counts = dict(sorted(drawn.items()))
    try:
        canvas.tag_raise(indent_tag)
    except Exception:
        pass


def add_prepared_indent_summary(base_text: str, app: Any) -> str:
    """Append the same outermost per-column prepared-indent diagnostic line."""
    blocks = list(getattr(app, "_layout_visualization_indent_blocks", []) or [])
    counts = prepared_indent_counts(blocks)
    if counts:
        detail = "   ".join(f"C{column}={count}" for column, count in counts.items())
    else:
        detail = "none"
    return base_text + f"\nindent blocks prepared: {detail}"


__all__ = [
    "_draw_indent_blocks_visible",
    "add_prepared_indent_summary",
    "prepared_indent_counts",
]
