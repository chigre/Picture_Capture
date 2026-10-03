from __future__ import annotations

from types import SimpleNamespace

from picture_capture.layout_core_understanding import _resolve_directional_body_lanes


def _line(role: str = "unknown") -> SimpleNamespace:
    return SimpleNamespace(role=role, y0=0, y1=20)


def _mode(center: float, support: int, tolerance: float) -> SimpleNamespace:
    lines = [_line() for _ in range(support)]
    return SimpleNamespace(
        center=float(center),
        support=int(support),
        tolerance=float(tolerance),
        role="unknown",
        lines=lines,
    )


def test_body_indent_uses_inner_stable_lane_even_when_entries_are_more_frequent() -> None:
    # Regression from a real page: entry rows outnumber wrapped body rows.
    outer_entry = _mode(0.0, 45, 2.0)
    inner_body = _mode(34.0, 22, 5.0)
    near_body = _mode(39.0, 2, 2.0)
    column = SimpleNamespace(
        indent_modes=[outer_entry, inner_body, near_body],
        lines=outer_entry.lines + inner_body.lines + near_body.lines,
        body_mode=outer_entry,
        entry_modes=[],
    )
    layout = SimpleNamespace(
        indent_type="body",
        ordinary_line_height=35.0,
        columns=[column],
        display_heads=[],
    )

    _resolve_directional_body_lanes(layout)

    assert column.body_mode is inner_body
    assert outer_entry.role == "entry"
    assert all(line.role == "entry" for line in outer_entry.lines)
    assert inner_body.role == "body"
    assert near_body.role == "body"
    assert all(line.role == "body" for line in inner_body.lines + near_body.lines)


def test_headword_indent_uses_outer_stable_lane_not_sparse_outlier() -> None:
    outer_body = _mode(3.0, 24, 4.0)
    inner_entry = _mode(38.0, 40, 5.0)
    sparse_far = _mode(90.0, 1, 2.0)
    column = SimpleNamespace(
        indent_modes=[outer_body, inner_entry, sparse_far],
        lines=outer_body.lines + inner_entry.lines + sparse_far.lines,
        body_mode=inner_entry,
        entry_modes=[],
    )
    layout = SimpleNamespace(
        indent_type="headword",
        ordinary_line_height=40.0,
        columns=[column],
        display_heads=[],
    )

    _resolve_directional_body_lanes(layout)

    assert column.body_mode is outer_body
    assert outer_body.role == "body"
    assert inner_entry.role == "entry"
    assert sparse_far.role == "entry"
