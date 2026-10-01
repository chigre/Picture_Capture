from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from picture_capture.layout_grid_inference import (
    assign_physical_indent_roles,
    indent_width_modes,
    projection_line_runs,
)


def test_projection_preserves_real_nonuniform_row_positions() -> None:
    ink = np.zeros((120, 140), dtype=bool)
    ink[7:22, 18:100] = True
    ink[31:49, 24:108] = True
    ink[66:84, 14:96] = True

    runs = projection_line_runs(ink, 20.0)

    assert runs == [(7, 22), (31, 49), (66, 84)]


def test_projection_splits_only_tall_run_when_sparse_bridge_connects_rows() -> None:
    ink = np.zeros((90, 120), dtype=bool)
    # Two real rows plus a one-pixel dust bridge in the inter-line valley.
    ink[8:24, 20:92] = True
    ink[31:47, 18:88] = True
    ink[23:32, 2:3] = True

    runs = projection_line_runs(ink, 20.0)

    assert len(runs) == 2
    centers = [(y0 + y1) / 2.0 for y0, y1 in runs]
    assert 14 <= centers[0] <= 19
    assert 36 <= centers[1] <= 42


def test_single_tall_dense_glyph_run_is_not_forced_onto_grid() -> None:
    ink = np.zeros((80, 120), dtype=bool)
    # Dense tall display typography: there is no low-ink internal separator.
    ink[10:42, 20:78] = True

    runs = projection_line_runs(ink, 20.0)

    assert runs == [(10, 42)]


def _line(first_x: int, anchor_x: int, *, small_prefix: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        first_x=first_x,
        anchor_x=anchor_x,
        has_small_prefix=small_prefix,
        patch=np.zeros((0, 0), dtype=bool),
    )


def test_indent_modes_cluster_by_first_x_not_anchor_x() -> None:
    # Anchor positions intentionally cross the physical indent groups. Lane
    # grouping must follow visible indent widths within this column.
    lines = [
        _line(4, 20),
        _line(6, 52),
        _line(34, 20),
        _line(36, 52),
    ]

    modes = indent_width_modes(lines, reference=20.0)

    assert len(modes) == 2
    assert [round(mode.center) for mode in modes] == [5, 35]
    assert {line.first_x for line in modes[0].lines} == {4, 6}
    assert {line.first_x for line in modes[1].lines} == {34, 36}


def test_small_prefix_does_not_change_physical_lane_membership() -> None:
    # A '~'-like prefix may move anchor_x, but the visible indent is the same.
    lines = [
        _line(34, 34),
        _line(35, 58, small_prefix=True),
        _line(36, 61, small_prefix=True),
    ]

    modes = indent_width_modes(lines, reference=20.0)

    assert len(modes) == 1
    assert round(modes[0].center) == 35
    assert len(modes[0].lines) == 3


def test_roles_are_assigned_from_physical_lanes_only() -> None:
    # Typical 'body indentation' page: entry rows sit near the column edge,
    # while the dominant body lane is farther inward. Anchor positions are
    # deliberately noisy and must not affect role assignment.
    entry_lines = [
        _line(4, 40),
        _line(5, 70, small_prefix=True),
        _line(6, 18),
    ]
    body_lines = [
        _line(34, 34),
        _line(35, 61),
        _line(36, 22),
        _line(35, 55),
        _line(34, 48),
        _line(36, 66),
    ]
    uncertain_lines = [
        _line(58, 12, small_prefix=True),
        _line(60, 90),
    ]

    modes = indent_width_modes(
        entry_lines + body_lines + uncertain_lines,
        reference=20.0,
    )
    column = SimpleNamespace(indent_modes=modes, body_mode=None, entry_modes=[])

    assign_physical_indent_roles(column, "body", 20.0)

    by_center = {round(mode.center): mode for mode in modes}
    assert by_center[5].role == "entry"
    assert by_center[35].role == "body"
    assert by_center[59].role == "unknown"
    assert column.body_mode is by_center[35]
    assert column.entry_modes == [by_center[5]]
