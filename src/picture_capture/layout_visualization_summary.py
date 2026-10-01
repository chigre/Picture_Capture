from __future__ import annotations

"""Richer, page-anchored summary for the Layout diagnostic overlay.

The base overlay owns geometry drawing. This module intercepts the one summary
text item so it can be placed at the horizontal centre of column 1, five
line-heights below ``body_top``, while containing the physical evidence needed
to audit layout inference.  It also renders Page Understanding's per-line
indent spans as pale-yellow translucent-looking blocks.
"""

from typing import Any, Callable

from .layout_visualization_readability import draw_layout_visualization_readable
from .layout_visualization_ui import _snapshot_for_app
from .processing import ORDINARY_AUTO_LAYOUT_FIELDS


_SUMMARY_TAG = "layout-visualization-summary"
_INDENT_TAG = "layout-visualization-indent"
_BASE_LAYOUT_TAG = "layout-visualization"


def _append_tag(tags: object, tag: str) -> tuple[str, ...]:
    if isinstance(tags, str):
        values = (tags,)
    else:
        try:
            values = tuple(str(value) for value in (tags or ()))
        except TypeError:
            values = ()
    return values if tag in values else values + (tag,)


def _format_summary(app: Any, snapshot: Any) -> str:
    geometry = snapshot.geometry
    settings = app._current_effective_profile_settings()
    values = snapshot.used_values
    confidence = (
        f"{snapshot.confidence:.2f}" if snapshot.confidence is not None else "—"
    )
    source_size = tuple(getattr(geometry, "source_size", (0, 0)) or (0, 0))
    if source_size == (0, 0) and getattr(app, "image", None) is not None:
        source_size = tuple(app.image.size)

    indent_blocks = list(getattr(app, "_layout_visualization_indent_blocks", []) or [])
    role_counts: dict[str, int] = {}
    for block in indent_blocks:
        role = str(block.get("role", "unknown") or "unknown")
        role_counts[role] = role_counts.get(role, 0) + 1
    role_text = ", ".join(
        f"{name}={count}" for name, count in sorted(role_counts.items())
    ) or "none"

    lines = [
        f"Layout {'AUTO' if snapshot.auto_enabled else 'CURRENT'}",
        f"method={snapshot.method}   confidence={confidence}",
        (
            f"page={source_size[0]}x{source_size[1]}   "
            f"transform={getattr(settings, 'layout_transform', 'identity')}   "
            f"writing={getattr(settings, 'layout_writing_mode', 'horizontal-tb')}   "
            f"direction={getattr(settings, 'layout_text_direction', 'ltr')}"
        ),
        (
            f"body: top={int(geometry.top)}   bottom={int(geometry.bottom)}   "
            f"height={max(0, int(geometry.bottom) - int(geometry.top))}"
        ),
        (
            f"used: columns={values['columns']}   start_y={values['start_y']}   "
            f"manual_x={values['manual_x']}   column_width={values['column_width']}   "
            f"gutter={values['gutter']}"
        ),
        (
            f"text scale: character_height={values['character_height']}   "
            f"row_padding={values['row_padding']}"
        ),
        f"line indents: {len(indent_blocks)}   roles: {role_text}",
    ]

    top = int(geometry.top)
    bottom = int(geometry.bottom)
    for index in range(len(geometry.column_starts)):
        left_top = int(geometry.x_at(index, top))
        left_bottom = int(geometry.x_at(index, bottom))
        width = int(geometry.column_widths[index])
        lines.append(
            f"C{index + 1}: left(top/bottom)={left_top}/{left_bottom}   "
            f"width={width}   right(top/bottom)={left_top + width}/{left_bottom + width}"
        )

    for index in range(max(0, len(geometry.column_starts) - 1)):
        left_width = int(geometry.column_widths[index])
        gutter_top = int(geometry.x_at(index + 1, top)) - (
            int(geometry.x_at(index, top)) + left_width
        )
        gutter_bottom = int(geometry.x_at(index + 1, bottom)) - (
            int(geometry.x_at(index, bottom)) + left_width
        )
        lines.append(
            f"G{index + 1}: width(top/bottom)={gutter_top}/{gutter_bottom}"
        )

    if snapshot.auto_enabled:
        switch_by_field = dict(ORDINARY_AUTO_LAYOUT_FIELDS)
        lines.append("auto fields:")
        for field, _switch in ORDINARY_AUTO_LAYOUT_FIELDS:
            used = values.get(field, getattr(settings, field, "—"))
            if field not in snapshot.raw_estimate:
                lines.append(f"  {field}: used={used}   raw=—   NO RAW ESTIMATE")
                continue
            raw = snapshot.raw_estimate[field]
            applied = field in snapshot.applied_fields
            state = "APPLIED" if applied else "RAW ONLY"
            switch = switch_by_field.get(field, "")
            lines.append(
                f"  {field}: used={used}   raw={raw}   {state}   switch={switch}"
            )

    return "\n".join(lines)


def _summary_anchor(app: Any, snapshot: Any) -> tuple[float, float]:
    """Return Canvas coordinates at column-1 centre and +5 line-heights."""
    geometry = snapshot.geometry
    scale = float(getattr(app, "view_scale", 1.0) or 1.0)
    top = int(geometry.top)
    bottom = int(geometry.bottom)

    values = getattr(snapshot, "used_values", {})
    line_height = max(1, int(values.get("character_height", 1) or 1))
    anchor_y = min(bottom, top + 5 * line_height)

    if geometry.column_starts and geometry.column_widths:
        left = int(geometry.x_at(0, anchor_y))
        width = int(geometry.column_widths[0])
    else:
        left = int(values.get("manual_x", 0) or 0)
        width = int(values.get("column_width", 0) or 0)

    centre_x = left + width / 2.0
    sx, sy = geometry.canonical_to_source(round(centre_x), anchor_y)
    return (sx * scale, sy * scale)


def _draw_indent_blocks(app: Any, snapshot: Any) -> None:
    """Draw each inferred line's indent span as a translucent-looking yellow block."""
    canvas = getattr(app, "canvas", None)
    if canvas is None:
        return
    try:
        canvas.delete(_INDENT_TAG)
    except Exception:
        return

    var = getattr(app, "_layout_visualization_var", None)
    if var is None or not bool(var.get()):
        return

    geometry = snapshot.geometry
    scale = float(getattr(app, "view_scale", 1.0) or 1.0)
    blocks = list(getattr(app, "_layout_visualization_indent_blocks", []) or [])
    if not blocks:
        return

    for block in blocks:
        try:
            x0 = float(block["x0"])
            x1 = float(block["x1"])
            y0 = int(block["y0"])
            y1 = int(block["y1"])
        except (KeyError, TypeError, ValueError):
            continue

        # Zero/near-zero indent is deliberately not painted: no yellow width is
        # itself the visual statement that this row sits on the body baseline.
        if abs(x1 - x0) < 1.0 or y1 <= y0:
            continue

        p0 = geometry.canonical_to_source(round(x0), y0)
        p1 = geometry.canonical_to_source(round(x1), y1)
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
                fill="#fff59d",
                outline="#f6d94a",
                width=1,
                stipple="gray50",
                tags=(_INDENT_TAG,),
            )
        except Exception:
            continue

    # Blocks are created after the base overlay so they are visible above the
    # page image. Lower them just beneath the base Layout guides/text so yellow
    # never obscures diagnostic lines or labels.
    try:
        canvas.tag_lower(_INDENT_TAG, _BASE_LAYOUT_TAG)
    except Exception:
        pass


def draw_layout_visualization_detailed(app: Any) -> None:
    """Draw readable Layout overlay with line indents and centred summary."""
    canvas = getattr(app, "canvas", None)
    if canvas is None:
        return

    try:
        snapshot = _snapshot_for_app(app)
    except Exception:
        # Let the base diagnostic renderer show its normal error label.
        draw_layout_visualization_readable(app)
        return

    summary_text = _format_summary(app, snapshot)
    summary_x, summary_y = _summary_anchor(app, snapshot)
    original_create_text: Callable[..., Any] = canvas.create_text

    def create_text_repositioned(*args: Any, **kwargs: Any) -> Any:
        text = str(kwargs.get("text", "") or "")
        if text.startswith("Layout "):
            args = (summary_x, summary_y) + tuple(args[2:]) if len(args) >= 2 else args
            if len(args) < 2:
                kwargs["x"] = summary_x
                kwargs["y"] = summary_y
            kwargs["anchor"] = "n"
            kwargs["justify"] = "center"
            kwargs["text"] = summary_text
            kwargs["tags"] = _append_tag(kwargs.get("tags", ()), _SUMMARY_TAG)
        return original_create_text(*args, **kwargs)

    canvas.create_text = create_text_repositioned
    try:
        draw_layout_visualization_readable(app)
    finally:
        canvas.create_text = original_create_text

    _draw_indent_blocks(app, snapshot)

    # Summary text and the readability rectangle share this tag. Raising the tag
    # after the complete overlay is drawn guarantees the panel stays on top.
    try:
        canvas.tag_raise(_SUMMARY_TAG)
    except Exception:
        pass
