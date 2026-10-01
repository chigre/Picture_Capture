from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from picture_capture.layout_grid_inference import grid_line_runs, indent_width_modes


def test_body_grid_splits_rows_even_when_specks_bridge_them() -> None:
    ink = np.zeros((90, 120), dtype=bool)
    # Two ordinary text rows with a thin scan-artifact bridge at the far left.
    ink[8:24, 20:92] = True
    ink[30:46, 18:88] = True
    ink[23:32, 2:3] = True

    runs = grid_line_runs(ink, 20.0)

    assert len(runs) >= 2
    # Grid slots must prevent the bridge from turning both rows into one tall run.
    assert all((y1 - y0) <= 23 for y0, y1 in runs)
    centers = [(y0 + y1) / 2.0 for y0, y1 in runs]
    assert any(12 <= center <= 22 for center in centers)
    assert any(33 <= center <= 43 for center in centers)


def _line(first_x: int, anchor_x: int) -> SimpleNamespace:
    return SimpleNamespace(
        first_x=first_x,
        anchor_x=anchor_x,
        patch=np.zeros((0, 0), dtype=bool),
    )


def test_indent_modes_cluster_by_first_x_not_anchor_x() -> None:
    # Anchor positions intentionally cross the physical indent groups.  If the
    # old anchor-based clustering returns, these four rows would be paired 2+2
    # by anchor instead of by the visible indent widths below.
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
