from __future__ import annotations

import numpy as np

from picture_capture.layout_physical_indent import (
    _logical_slots_for_oversized_run,
    projection_line_runs,
)


def test_continuous_two_line_display_run_recovers_two_logical_rows() -> None:
    reference = 50.0
    ink = np.zeros((180, 160), dtype=bool)
    # One vertically continuous display-size glyph/word block spanning about
    # 2.2 ordinary rows.  There is deliberately no horizontal white valley.
    ink[30:140, 80:130] = True

    runs = projection_line_runs(ink, reference)

    assert len(runs) == 2
    assert runs[0][0] == 30
    assert runs[-1][1] == 140
    assert all(45 <= (y1 - y0) <= 65 for y0, y1 in runs)


def test_ordinary_run_is_not_split_into_logical_slots() -> None:
    reference = 50.0
    ink = np.zeros((120, 160), dtype=bool)
    ink[20:80, 60:125] = True

    runs = projection_line_runs(ink, reference)

    assert runs == [(20, 80)]


def test_logical_slot_helper_uses_row_height_not_semantics() -> None:
    slots = _logical_slots_for_oversized_run(10, 115, 50.0)

    assert len(slots) == 2
    assert slots[0][0] == 10
    assert slots[-1][1] == 115
