from __future__ import annotations

"""Make per-line physical indents unmistakably visible in Layout diagnostics.

The shared Layout Core already records every line's local ``first_x`` value.  A
Layout diagnostic must therefore show the actual blank span from the physical
column-left boundary to that first ink position.  The previous renderer lowered
those pale-yellow blocks beneath the whole base Layout tag.  On real pages that
made prepared C1 indent evidence effectively disappear even while lane numbers
were present in the text summary.

This display-only adapter keeps the blocks above the scan/base geometry, adds a
clear first-ink edge, and leaves role strips and the summary above them.  It does
not change ``first_x``, lane clustering, roles, entry detection, PDIC, OCR, or
crop geometry.
"""

from collections import Counter
from typing import Any, Callable


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
            # The right edge is the measured first-ink X.  Keeping it solid makes
            # even a narrow blank span auditable when the pale fill is subtle.
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

    # Do not lower below the complete base Layout tag: that was the path that
    # could hide prepared C1 blocks on the scan.  These items are created after
    # the base overlay, so raising them makes the measured blank explicit.  Role
    # strips are drawn/raised afterwards and the summary tag is raised last.
    try:
        canvas.tag_raise(indent_tag)
    except Exception:
        pass


def install_layout_indent_visibility() -> None:
    """Install the visible-indent renderer and per-column diagnostics once."""
    from . import layout_visualization_summary as summary

    if bool(getattr(summary, "_layout_indent_visibility_installed", False)):
        return

    summary._draw_indent_blocks = _draw_indent_blocks_visible

    original_format: Callable[[Any, Any], str] = summary._format_summary

    def format_summary(app: Any, snapshot: Any) -> str:
        text = original_format(app, snapshot)
        blocks = list(getattr(app, "_layout_visualization_indent_blocks", []) or [])
        counts = prepared_indent_counts(blocks)
        if counts:
            detail = "   ".join(f"C{column}={count}" for column, count in counts.items())
        else:
            detail = "none"
        return text + f"\nindent blocks prepared: {detail}"

    summary._format_summary = format_summary
    summary._layout_indent_visibility_installed = True


__all__ = [
    "_draw_indent_blocks_visible",
    "install_layout_indent_visibility",
    "prepared_indent_counts",
]
