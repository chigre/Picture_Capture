from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from picture_capture.layout_core_understanding import _resolve_near_tied_body_lanes


def _line(first_x: float) -> SimpleNamespace:
    return SimpleNamespace(
        first_x=float(first_x),
        y0=0,
        y1=30,
        role="unknown",
        patch=np.zeros((0, 0), dtype=bool),
    )


def _mode(center: float, support: int) -> SimpleNamespace:
    lines = [_line(center) for _ in range(support)]
    return SimpleNamespace(
        center=float(center),
        tolerance=2.0,
        lines=lines,
        role="unknown",
        support=support,
    )


def test_body_indent_near_tie_uses_inward_lane_as_body() -> None:
    outer = _mode(2.5, 35)
    inward = _mode(37.3, 34)
    column = SimpleNamespace(
        indent_modes=[outer, inward],
        lines=outer.lines + inward.lines,
        body_mode=outer,
        entry_modes=[],
    )
    layout = SimpleNamespace(
        indent_type="body",
        ordinary_line_height=35.0,
        columns=[column],
        display_heads=[],
    )

    _resolve_near_tied_body_lanes(layout)

    assert column.body_mode is inward
    assert outer.role == "entry"
    assert inward.role == "body"
    assert column.entry_modes == [outer]
    assert all(line.role == "entry" for line in outer.lines)
    assert all(line.role == "body" for line in inward.lines)


def test_headword_indent_near_tie_uses_outer_lane_as_body() -> None:
    outer = _mode(3.0, 31)
    inward = _mode(42.0, 32)
    column = SimpleNamespace(
        indent_modes=[outer, inward],
        lines=outer.lines + inward.lines,
        body_mode=inward,
        entry_modes=[],
    )
    layout = SimpleNamespace(
        indent_type="headword",
        ordinary_line_height=36.0,
        columns=[column],
        display_heads=[],
    )

    _resolve_near_tied_body_lanes(layout)

    assert column.body_mode is outer
    assert outer.role == "body"
    assert inward.role == "entry"
    assert column.entry_modes == [inward]
