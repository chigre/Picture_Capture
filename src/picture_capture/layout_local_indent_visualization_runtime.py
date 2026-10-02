from __future__ import annotations

"""Show physical indent relative to each row's drift-corrected local baseline.

A fixed Project/Profile column origin is useful semantic geometry, but it is not
always the physical left edge at every Y on a skewed/curved scan.  Layout role
clustering already consumes slant-normalized ``first_x`` values.  Diagnostics
must visualize that same quantity rather than drawing raw first-X from a fixed
vertical origin, otherwise a left-drifting row can misleadingly appear to have
"no indent".
"""

from typing import Any

from .layout_physical_indent import normalized_physical_indents


def drift_corrected_indent_blocks(understanding: Any) -> list[dict[str, Any]]:
    """Return per-line blank spans from local column baseline to first ink."""
    layout = understanding.layout
    blocks: list[dict[str, Any]] = []
    body_top = int(getattr(layout, "body_top", 0) or 0)

    for column in list(getattr(layout, "columns", []) or []):
        column_left = float(getattr(column, "left", 0) or 0)
        lines = list(getattr(column, "lines", []) or [])
        corrected_by_line = normalized_physical_indents(lines)
        body = getattr(column, "body_mode", None)
        body_local_x = float(body.center) if body is not None else None

        for line in lines:
            try:
                raw_local_x = float(getattr(line, "first_x", 0) or 0)
                corrected_local_x = float(
                    corrected_by_line.get(id(line), raw_local_x)
                )
                y0 = body_top + int(getattr(line, "y0", 0) or 0)
                y1 = body_top + int(getattr(line, "y1", 0) or 0)
            except (TypeError, ValueError):
                continue
            if y1 <= y0:
                continue

            # raw = common scan drift + semantic indent.  After normalization,
            # corrected is the semantic/local indent, so raw-corrected recovers
            # the row-local movement of the physical column baseline.
            common_drift = raw_local_x - corrected_local_x
            local_origin_x = column_left + common_drift
            indent_width = max(0.0, corrected_local_x)
            first_ink_x = local_origin_x + indent_width

            anchor = getattr(line, "anchor_x", None)
            anchor_local_x = float(anchor) if anchor is not None else None
            blocks.append({
                "column": int(getattr(column, "index", 0) or 0),
                "x0": float(local_origin_x),
                "x1": float(first_ink_x),
                "y0": int(y0),
                "y1": int(y1),
                "first_x": float(first_ink_x),
                "raw_first_x": float(raw_local_x),
                "corrected_indent_px": float(corrected_local_x),
                "local_origin_x": float(local_origin_x),
                "anchor_x": (
                    column_left + anchor_local_x
                    if anchor_local_x is not None else None
                ),
                "body_x": (
                    column_left + body_local_x
                    if body_local_x is not None else None
                ),
                "indent_px": float(indent_width),
                "role": str(getattr(line, "role", "") or "unknown"),
            })
    return blocks


def install_local_indent_visualization() -> None:
    """Make Layout diagnostics consume the same corrected indent as role logic."""
    from . import layout_visualization_shared as shared

    if bool(getattr(shared, "_local_indent_visualization_installed", False)):
        return
    shared._indent_blocks_from_understanding = drift_corrected_indent_blocks
    shared._local_indent_visualization_installed = True


__all__ = [
    "drift_corrected_indent_blocks",
    "install_local_indent_visualization",
]
