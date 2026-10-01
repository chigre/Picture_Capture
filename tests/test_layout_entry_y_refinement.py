from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from picture_capture.layout_entry_y_refinement import refine_entry_separator_y


def _line(y0: int, y1: int, role: str = "body") -> SimpleNamespace:
    return SimpleNamespace(y0=y0, y1=y1, role=role)


def test_entry_y_moves_to_real_whitespace_above_entry() -> None:
    ink = np.zeros((180, 220), dtype=bool)
    # Previous body text and current entry text, leaving a clear inter-line band.
    ink[70:92, 20:200] = True
    ink[108:136, 20:200] = True

    refined = refine_entry_separator_y(
        ink,
        column_left=10,
        column_right=210,
        body_top=20,
        body_bottom=170,
        previous_line=_line(50, 72, "body"),   # absolute 70..92
        line=_line(88, 116, "entry"),          # coarse absolute Y = 108
        line_height=28,
    )

    # The separator belongs in the real blank band, not on the entry glyph top.
    assert 96 <= refined <= 104
    assert refined < 108


def test_entry_y_refinement_is_local() -> None:
    ink = np.zeros((220, 240), dtype=bool)
    ink[40:75, 10:230] = True
    ink[150:180, 10:230] = True

    coarse = 150
    refined = refine_entry_separator_y(
        ink,
        column_left=0,
        column_right=240,
        body_top=0,
        body_bottom=220,
        previous_line=_line(40, 75, "body"),
        line=_line(coarse, 180, "entry"),
        line_height=30,
    )

    # Even a huge whitespace region cannot make the separator jump to another row.
    assert abs(refined - coarse) <= round(30 * 0.36)


def test_refinement_does_not_depend_on_role_support() -> None:
    ink = np.zeros((120, 160), dtype=bool)
    ink[30:50, 10:150] = True
    ink[62:82, 10:150] = True

    single_entry = _line(62, 82, "entry")
    refined = refine_entry_separator_y(
        ink,
        column_left=0,
        column_right=160,
        body_top=0,
        body_bottom=120,
        previous_line=_line(30, 50, "body"),
        line=single_entry,
        line_height=20,
    )

    assert single_entry.role == "entry"
    assert refined <= 62
