"""Recover missing *Layout* entry-indentation evidence, before drawing PDIC.

Different from the downstream emergency PDIC rescue: this repairs the shared
Page Understanding column/row objects, so Layout overlays and ordinary drawing
agree. Only weak columns are considered and no entry is inferred merely from
"zero entries". Independent line families or literal printed CJK bracket pairs
must be observed in source image before any row is promoted.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
from PIL import Image

from . import dictionary_page_design as base
from .entry_classification import register_layout_line_classification
from .models import Entry
from .page_understanding import uses_cjk_role_model


def _weak_columns(layout: Any, *, cjk: bool = False) -> list[int]:
    result = []
    for i, column in enumerate(layout.columns):
        lines = column.lines
        entry_count = sum(line.role == "entry" for line in lines)
        # Bracketed CJK pages may merge dozens of tight printed rows into
        # oversized ink projection bands: a few accepted labels don't mean
        # the missing rows are absent from the source scan.
        pitch = max(8.0, float(getattr(layout, "ordinary_line_pitch", 0) or
                               layout.ordinary_line_height))
        expected = max(1.0, (layout.body_bottom - layout.body_top) / pitch)
        undersegmented = bool(cjk and 12 <= len(lines) < expected * .40)
        if (
            len(lines) >= 12
            and (entry_count <= max(3, round(len(lines) * .08))
                 or undersegmented)
        ):
            result.append(i)
    return result


def _row_at_y(column: Any, y: int, top: int, radius: float):
    lines = column.lines
    if not lines:
        return None
    nearest = min(lines, key=lambda row: abs((row.y0 + top) - y))
    if abs((nearest.y0 + top) - y) <= radius:
        return nearest
    return None


def _promote_at_y(
    layout: Any, column_index: int, absolute_y: int,
    *, source: str, y_height: int | None = None,
):
    column = layout.columns[column_index]
    top = int(layout.body_top)
    ref = max(8.0, float(layout.ordinary_line_height))
    if absolute_y < top or absolute_y >= int(layout.body_bottom):
        return None
    nearest = _row_at_y(column, absolute_y, top, ref * .52)
    if nearest is not None and nearest.role == "entry":
        return nearest
    if nearest is None:
        local = absolute_y - top
        nearest = base.LayoutLine(
            column=column_index, y0=local, y1=local + max(1, int(y_height or ref)),
            first_x=0, anchor_x=None, anchor_width=0, anchor_height=0,
            gap_before=0, patch=np.zeros((0, 0), dtype=bool),
        )
        column.lines.append(nearest)
    nearest.role = "entry"
    register_layout_line_classification(
        nearest, Entry(
            "", int(column.left), int(absolute_y),
            ocr_source=source,
            issue_type="ORDINARY_PROVEN_COLUMN_INDENT_EVIDENCE",
        )
    )
    return nearest


def _independently_proven_columns(
    image: Image.Image, settings: Any, layout: Any,
    weak: list[int], page_index: int,
) -> dict[int, tuple[list[int], float, float]]:
    """Demand two genuine row families with adequate independent support."""
    from . import dictionary_page_design_refined as refined

    try:
        independent = refined.detect_entries_from_page_design(
            image, settings, page_index=page_index, ops=base.RAW_LAYOUT_OPS,
        )
    except (TypeError, ValueError, RuntimeError, IndexError):
        return {}
    alternate = independent.layout
    if (
        not alternate.reliable or len(alternate.columns) != len(layout.columns)
        or str(alternate.transform.kind) != str(layout.transform.kind)
    ):
        return {}
    reference = max(8.0, float(alternate.ordinary_line_height))
    result = {}
    for index in weak:
        col, other = layout.columns[index], alternate.columns[index]
        if abs(col.left - other.left) > max(3.0 * reference, col.width * .10):
            continue
        body = other.body_mode
        if body is None or body.support < 5:
            continue
        good = [
            mode for mode in other.entry_modes
            if mode.support >= max(5, round(len(other.lines) * .08))
            and float(body.center) - float(mode.center) >= .30 * reference
        ]
        if not good:
            continue
        ys = sorted(set(
            int(alternate.body_top) + int(line.y0)
            for mode in good for line in mode.lines
        ))
        if len(ys) < 5:
            continue
        entry_center = min(float(mode.center) for mode in good) + (other.left - col.left)
        body_center = float(body.center) + (other.left - col.left)
        result[index] = ys, entry_center, body_center
    return result


def restore_proven_column_indents(
    image: Image.Image, settings: Any, layout: Any, *,
    page_index: int = 0,
) -> dict[str, int]:
    """Restore true Layout indentation families when a populated column collapsed.

    A normal page incurs NO second scan. Latin recovery requires an independent
    bimodal font-indent family. CJK bracket recovery requires paired ink glyphs;
    ordinary arbitrary body rows are never converted to entries.
    """
    stats = {"rescued_columns": 0, "rescued_rows": 0, "cjk_bracket_rows": 0}
    if layout.indent_type != "body" or len(layout.columns) < 2:
        return stats
    cjk = uses_cjk_role_model(settings)
    weak = _weak_columns(layout, cjk=cjk)
    if not weak:
        return stats
    alternate = {} if cjk else _independently_proven_columns(
        image, settings, layout, weak, page_index,
    )
    bracket_by_column: dict[int, list[int]] = {}
    if cjk and bool(getattr(settings, "profile_cjk_allow_bracketed_headword", True)):
        from .ordinary_bracket_pair import recover_bracketed_ordinary_entries
        transform = layout.transform
        rotated = str(getattr(transform, "kind", "identity")) != "identity"
        canonical = transform.canonical_image_for_analysis(image) if rotated else image
        try:
            marks = recover_bracketed_ordinary_entries(
                [], canonical, layout.columns, int(layout.body_top),
                int(layout.body_bottom), float(layout.ordinary_line_height),
                transform=transform, source_size=layout.source_size,
            )
        finally:
            if rotated:
                canonical.close()
        for mark in marks:
            u, v = transform.source_to_canonical_point(
                int(mark.x), int(mark.y), layout.source_size,
            )
            index = min(
                range(len(layout.columns)),
                key=lambda i: abs(u - layout.columns[i].left),
            )
            if index in weak and abs(u - layout.columns[index].left) <= max(
                6, layout.ordinary_line_height * .5,
            ):
                bracket_by_column.setdefault(index, []).append(int(v))

    for index in weak:
        col = layout.columns[index]
        entry_y, entry_x, body_x = [], None, None
        if index in alternate:
            entry_y, entry_x, body_x = alternate[index]
        elif index in bracket_by_column and len(bracket_by_column[index]) >= 3:
            entry_y = sorted(set(bracket_by_column[index]))
            # Prefer the *measured* outer/inner physical lanes. Brackets prove
            # the entry identity; observed X-mode separation proves the indent.
            measured = sorted(
                (mode for mode in col.indent_modes if mode.support >= 2),
                key=lambda mode: float(mode.center),
            )
            if len(measured) >= 2 and (
                measured[-1].center - measured[0].center
                >= max(6.0, layout.ordinary_line_height * .30)
            ):
                entry_x = float(measured[0].center)
                body_x = float(measured[-1].center)
            else:
                entry_x = 0.0
                body_x = float(col.body_mode.center) if col.body_mode else None
        entry_y = sorted({
            int(y) for y in entry_y
            if int(layout.body_top) <= int(y) < int(layout.body_bottom)
        })
        if len(entry_y) < 3:
            continue

        # Retain previously accepted entries instead of replacing them by
        # an independent alternative; this is an augmentation, not erasure.
        old_entries = [row for row in col.lines if row.role == "entry"]
        detected = list(old_entries)
        for y in entry_y:
            line = _promote_at_y(
                layout, index, y,
                source=("page_understanding:bracket_family" if cjk
                        else "page_understanding:independent_indent_family"),
            )
            if line is not None:
                detected.append(line)
        detected = list({id(line): line for line in detected}.values())
        if len(detected) < 3:
            continue

        # Rebuild the *visible Layout* family rather than only adding WW lines.
        proven_ids = {id(line) for line in detected}
        body_lines = [line for line in col.lines if id(line) not in proven_ids]
        if entry_x is None:
            entry_x = min((float(line.first_x) for line in detected), default=0.0)
        if body_x is None or body_x <= entry_x:
            body_x = float(entry_x) + max(8.0, layout.ordinary_line_height * .6)
        entry_mode = base.IndentMode(
            center=float(entry_x), tolerance=max(1.0, layout.ordinary_line_height * .13),
            lines=detected, role="entry",
        )
        body_mode = base.IndentMode(
            center=float(body_x), tolerance=max(1.0, layout.ordinary_line_height * .15),
            lines=body_lines, role="body",
        )
        col.entry_modes = [entry_mode]
        col.body_mode = body_mode
        col.indent_modes = [entry_mode, body_mode]
        col.lines.sort(key=lambda line: (line.y0, line.y1))
        stats["rescued_columns"] += 1
        stats["rescued_rows"] += len(detected)
        if cjk:
            stats["cjk_bracket_rows"] += len(detected)
    return stats
