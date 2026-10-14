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


def test_two_column_headword_indent_rejects_outside_column_phantom_body_lane() -> None:
    """An independently measured gutter/neighbor band cannot own right body.

    Anonymized structural counts from the 080176 role snapshot (no scan
    pixels or dictionary text): left 42 body/11 head; right 14 outside,
    31 body, 8 head. The old minimum-X stable-mode policy chose -96 and
    incorrectly promoted all 31 right body rows to entry.
    """
    left_body = _mode(7.75, 42, 4.0)
    left_head = _mode(137.04, 11, 4.0)
    left = SimpleNamespace(
        indent_modes=[left_body, left_head],
        lines=left_body.lines + left_head.lines,
        body_mode=None, entry_modes=[],
    )

    outside_right = _mode(-96.76, 14, 4.0)
    actual_right_body = _mode(7.65, 31, 4.0)
    right_head = _mode(135.96, 8, 4.0)
    right = SimpleNamespace(
        indent_modes=[outside_right, actual_right_body, right_head],
        lines=outside_right.lines + actual_right_body.lines + right_head.lines,
        body_mode=None, entry_modes=[],
    )
    layout = SimpleNamespace(
        indent_type="headword",
        ordinary_line_height=52.65,
        columns=[left, right], display_heads=[],
    )

    _resolve_directional_body_lanes(layout)

    assert left.body_mode is left_body
    assert [m for m in left.entry_modes] == [left_head]
    assert all(r.role == "body" for r in left_body.lines)
    assert all(r.role == "entry" for r in left_head.lines)
    assert right.body_mode is actual_right_body
    assert right.entry_modes == [right_head]
    assert all(r.role == "body" for r in actual_right_body.lines)
    assert all(r.role == "body" for r in outside_right.lines)
    assert all(r.role == "entry" for r in right_head.lines)


def test_outside_column_filter_abstains_without_two_plausible_supported_lanes() -> None:
    """An uncertain geometry must not reinterpret a genuine offset page."""
    left_body = _mode(0.0, 22, 3.0)
    left_head = _mode(70.0, 10, 3.0)
    left = SimpleNamespace(
        indent_modes=[left_body, left_head],
        lines=left_body.lines + left_head.lines,
        body_mode=None, entry_modes=[],
    )
    true_outside_body = _mode(-95.0, 14, 3.0)
    inner_head = _mode(110.0, 8, 3.0)
    right = SimpleNamespace(
        indent_modes=[true_outside_body, inner_head],
        lines=true_outside_body.lines + inner_head.lines,
        body_mode=None, entry_modes=[],
    )
    layout = SimpleNamespace(
        indent_type="headword",
        ordinary_line_height=53.0, columns=[left, right], display_heads=[],
    )

    _resolve_directional_body_lanes(layout)

    assert right.body_mode is true_outside_body
    assert right.entry_modes == [inner_head]


def test_moderate_negative_column_indent_is_not_dropped() -> None:
    """Ordinary printed margin slant/offset is not a phantom band."""
    left_body = _mode(-14.0, 20, 3.0)
    left_head = _mode(45.0, 8, 3.0)
    left = SimpleNamespace(
        indent_modes=[left_body, left_head],
        lines=left_body.lines + left_head.lines,
        body_mode=None, entry_modes=[],
    )
    right_body = _mode(-18.0, 25, 3.0)
    right_head = _mode(50.0, 10, 3.0)
    right = SimpleNamespace(
        indent_modes=[right_body, right_head],
        lines=right_body.lines + right_head.lines,
        body_mode=None, entry_modes=[],
    )
    layout = SimpleNamespace(
        indent_type="headword", ordinary_line_height=53.0,
        columns=[left, right], display_heads=[],
    )

    _resolve_directional_body_lanes(layout)

    assert right.body_mode is right_body
    assert right.entry_modes == [right_head]
