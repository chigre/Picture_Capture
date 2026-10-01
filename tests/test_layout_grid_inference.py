from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from picture_capture.layout_grid_inference import projection_line_runs, indent_width_modes


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


def _line(first_x: int, anchor_x: int) -> SimpleNamespace:
    return SimpleNamespace(
        first_x=first_x,
        anchor_x=anchor_x,
        patch=np.zeros((0, 0), dtype=bool),
    )


def test_indent_modes_cluster_by_first_x_not_anchor_x() -> None:
    # Anchor positions intentionally cross the physical indent groups.  Lane
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
