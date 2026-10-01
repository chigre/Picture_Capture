from __future__ import annotations

from types import SimpleNamespace

from picture_capture.dictionary_page_design import ColumnDesign, IndentMode, LayoutLine
from picture_capture.layout_physical_indent import assign_binary_roles


def _line(y: int) -> LayoutLine:
    return LayoutLine(
        column=0,
        y0=y,
        y1=y + 20,
        first_x=0,
        anchor_x=0,
        anchor_width=10,
        anchor_height=18,
        gap_before=0,
        patch=__import__("numpy").zeros((0, 0), dtype=bool),
    )


def _mode(center: float, support: int, y0: int) -> IndentMode:
    lines = [_line(y0 + index * 24) for index in range(support)]
    return IndentMode(center=center, tolerance=1.5, lines=lines)


def test_headword_indent_keeps_nearby_lanes_as_body() -> None:
    body = _mode(2.0, 30, 0)
    near = _mode(7.0, 3, 800)
    entry = _mode(20.0, 1, 900)
    column = ColumnDesign(index=0, left=0, right=500, gutter_after=30)
    column.lines = body.lines + near.lines + entry.lines
    column.indent_modes = [body, near, entry]

    assign_binary_roles(column, "headword", 60.0)

    assert body.role == "body"
    assert near.role == "body"
    assert entry.role == "entry"
    assert all(line.role == "body" for line in near.lines)
    assert all(line.role == "entry" for line in entry.lines)


def test_body_indent_uses_same_neighborhood_in_reverse() -> None:
    body = _mode(30.0, 25, 0)
    near = _mode(24.0, 2, 700)
    entry = _mode(12.0, 1, 800)
    column = ColumnDesign(index=0, left=0, right=500, gutter_after=30)
    column.lines = body.lines + near.lines + entry.lines
    column.indent_modes = [entry, near, body]

    assign_binary_roles(column, "body", 60.0)

    assert body.role == "body"
    assert near.role == "body"
    assert entry.role == "entry"
