from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from picture_capture.layout_grid_inference import (
    assign_physical_indent_roles,
    indent_width_modes,
)
from picture_capture.layout_lane_summary_extension import append_physical_lane_summary


def _line(first_x: int) -> SimpleNamespace:
    return SimpleNamespace(
        first_x=first_x,
        anchor_x=first_x,
        has_small_prefix=False,
        patch=np.zeros((0, 0), dtype=bool),
    )


def test_clustering_is_independent_of_character_height() -> None:
    lines = [_line(2), _line(4), _line(5), _line(13), _line(15), _line(16)]

    small = indent_width_modes(lines, reference=20.0)
    large = indent_width_modes(lines, reference=80.0)

    assert [round(mode.center) for mode in small] == [4, 15]
    assert [round(mode.center) for mode in large] == [4, 15]


def test_c1_like_distribution_merges_continuous_body_peak() -> None:
    values = (
        [0, 0, 1, 1, 2, 2] * 3
        + [21, 22, 23, 24, 25, 25, 26, 27, 28, 29, 30] * 4
        + [31, 32, 33, 34, 35] * 2
        + [43]
        + [97]
    )
    modes = indent_width_modes([_line(v) for v in values], reference=50.0)

    ranges = [
        (
            min(line.first_x for line in mode.lines),
            max(line.first_x for line in mode.lines),
            len(mode.lines),
        )
        for mode in modes
    ]

    assert ranges[0][0:2] == (0, 2)
    assert any(lo == 21 and hi == 35 and n > 40 for lo, hi, n in ranges)
    assert any(lo == 43 and hi == 43 for lo, hi, _n in ranges)
    assert any(lo == 97 and hi == 97 for lo, hi, _n in ranges)


def test_binary_roles_choose_entry_then_make_everything_else_body() -> None:
    values = (
        [12, 13, 13, 14, 14, 15, 15, 16, 16, 17] * 2
        + [19, 20, 19]
        + [31]
        + [43, 44, 45, 46, 47, 48, 49, 49, 50, 51, 52, 53, 54] * 4
        + [85, 90]
        + [118]
    )
    modes = indent_width_modes([_line(v) for v in values], reference=50.0)
    column = SimpleNamespace(indent_modes=modes, body_mode=None, entry_modes=[])

    assign_physical_indent_roles(column, "body", reference=50.0)

    assert len(column.entry_modes) == 1
    entry = column.entry_modes[0]
    assert 12 <= entry.center <= 20
    assert entry.role == "entry"
    assert all(mode.role in {"entry", "body"} for mode in modes)
    assert all(mode.role == "body" for mode in modes if mode is not entry)
    assert column.body_mode is not None
    assert column.body_mode is not entry


def test_single_lane_page_stays_body() -> None:
    modes = indent_width_modes([_line(v) for v in [2, 2, 3, 3, 4, 4]], reference=50.0)
    column = SimpleNamespace(indent_modes=modes, body_mode=None, entry_modes=[])

    assign_physical_indent_roles(column, "body", reference=50.0)

    assert len(modes) == 1
    assert modes[0].role == "body"
    assert column.body_mode is modes[0]
    assert column.entry_modes == []


def test_lane_summary_reports_only_entry_or_body_roles() -> None:
    app = SimpleNamespace(
        _layout_visualization_indent_lanes=[
            {"column": 0, "lane": 0, "center": 3.0, "min": 2.0, "max": 5.0, "support": 8, "role": "entry"},
            {"column": 0, "lane": 1, "center": 15.0, "min": 13.0, "max": 17.0, "support": 5, "role": "body"},
            {"column": 0, "lane": 2, "center": 35.0, "min": 32.0, "max": 38.0, "support": 22, "role": "body"},
        ]
    )

    text = append_physical_lane_summary("Layout AUTO", app)

    assert "physical indent lanes:" in text
    assert "C1/L1: center=3.0   range=2.0-5.0   n=8   role=entry" in text
    assert "C1/L2: center=15.0   range=13.0-17.0   n=5   role=body" in text
    assert "C1/L3: center=35.0   range=32.0-38.0   n=22   role=body" in text
    assert "unknown" not in text
