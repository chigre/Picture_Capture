from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from picture_capture.layout_lane_summary_extension import append_physical_lane_summary
from picture_capture.layout_physical_indent import (
    assign_binary_roles,
    estimate_column_slant,
    normalize_layout_roles,
    physical_indent_modes,
)


def _line(first_x: int | float, y0: int | None = None) -> SimpleNamespace:
    payload = dict(
        first_x=first_x,
        anchor_x=first_x,
        has_small_prefix=False,
        patch=np.zeros((0, 0), dtype=bool),
        role="unknown",
    )
    if y0 is not None:
        payload["y0"] = int(y0)
        payload["y1"] = int(y0) + 30
    return SimpleNamespace(**payload)


def test_clustering_is_independent_of_character_height() -> None:
    lines = [_line(2), _line(4), _line(5), _line(13), _line(15), _line(16)]

    small = physical_indent_modes(lines, 20.0)
    large = physical_indent_modes(lines, 80.0)

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
    modes = physical_indent_modes([_line(v) for v in values], 50.0)

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


def test_slanted_column_is_detrended_before_lane_clustering() -> None:
    # One real body lane and one real headword lane both drift +30 px from top
    # to bottom because the scanned column is tilted.
    lines = [
        _line(10 + 0.01 * y, y)
        for y in range(0, 3000, 100)
    ]
    lines += [
        _line(55 + 0.01 * y, y)
        for y in (250, 1250, 2250)
    ]

    slope = estimate_column_slant(lines)
    modes = physical_indent_modes(lines, 60.0)

    assert 0.006 <= slope <= 0.014
    assert len(modes) == 2
    assert modes[0].support == 30
    assert modes[1].support == 3
    assert modes[1].center - modes[0].center > 35


def test_binary_roles_partition_all_lanes_into_two_classes() -> None:
    values = (
        [12, 13, 13, 14, 14, 15, 15, 16, 16, 17] * 2
        + [19, 20, 19]
        + [31]
        + [43, 44, 45, 46, 47, 48, 49, 49, 50, 51, 52, 53, 54] * 4
        + [85, 90]
        + [118]
    )
    lines = [_line(v) for v in values]
    modes = physical_indent_modes(lines, 50.0)
    column = SimpleNamespace(
        indent_modes=modes,
        lines=lines,
        body_mode=None,
        entry_modes=[],
    )

    assign_binary_roles(column, "body", 50.0)

    assert column.entry_modes
    assert all(mode.role in {"entry", "body"} for mode in modes)
    assert all(
        line.role == mode.role
        for mode in modes
        for line in mode.lines
    )
    assert max(mode.center for mode in column.entry_modes) < column.body_mode.center


def test_headword_indent_keeps_multiple_high_indent_entry_lanes() -> None:
    body = SimpleNamespace(center=6.0, support=60, role="unknown", lines=[_line(6) for _ in range(60)])
    normal_head = SimpleNamespace(center=45.0, support=8, role="unknown", lines=[_line(45) for _ in range(8)])
    display_head = SimpleNamespace(center=88.0, support=1, role="unknown", lines=[_line(88)])
    column = SimpleNamespace(
        indent_modes=[body, normal_head, display_head],
        lines=body.lines + normal_head.lines + display_head.lines,
        body_mode=None,
        entry_modes=[],
    )

    assign_binary_roles(column, "headword")

    assert column.body_mode is body
    assert column.entry_modes == [normal_head, display_head]
    assert body.role == "body"
    assert normal_head.role == "entry"
    assert display_head.role == "entry"
    assert display_head.lines[0].role == "entry"


def test_final_normalization_removes_legacy_sparse_entry() -> None:
    entry = SimpleNamespace(center=1.0, support=10, role="unknown", lines=[_line(1) for _ in range(10)])
    body = SimpleNamespace(center=28.0, support=30, role="body", lines=[_line(28) for _ in range(30)])
    stray = SimpleNamespace(center=70.0, support=1, role="entry", lines=[_line(70)])
    column = SimpleNamespace(
        indent_modes=[entry, body, stray],
        lines=entry.lines + body.lines + stray.lines,
        body_mode=body,
        entry_modes=[stray],
    )
    layout = SimpleNamespace(indent_type="body", columns=[column])

    normalize_layout_roles(layout)

    assert entry.role == "entry"
    assert body.role == "body"
    assert stray.role == "body"
    assert all(line.role == "entry" for line in entry.lines)
    assert all(line.role == "body" for line in body.lines + stray.lines)


def test_single_lane_page_stays_body() -> None:
    lines = [_line(v) for v in [2, 2, 3, 3, 4, 4]]
    modes = physical_indent_modes(lines, 50.0)
    column = SimpleNamespace(indent_modes=modes, lines=lines, body_mode=None, entry_modes=[])

    assign_binary_roles(column, "body", 50.0)

    assert len(modes) == 1
    assert modes[0].role == "body"
    assert all(line.role == "body" for line in lines)
    assert column.entry_modes == []


def test_lane_summary_distinguishes_corrected_and_raw_ranges() -> None:
    app = SimpleNamespace(
        _layout_visualization_indent_lanes=[
            {
                "column": 0,
                "lane": 0,
                "center": 3.0,
                "min": 2.0,
                "max": 5.0,
                "raw_min": 4.0,
                "raw_max": 9.0,
                "support": 8,
                "role": "entry",
            },
            {
                "column": 0,
                "lane": 1,
                "center": 15.0,
                "min": 13.0,
                "max": 17.0,
                "raw_min": 16.0,
                "raw_max": 22.0,
                "support": 5,
                "role": "body",
            },
            {
                "column": 0,
                "lane": 2,
                "center": 35.0,
                "min": 32.0,
                "max": 38.0,
                "raw_min": 35.0,
                "raw_max": 43.0,
                "support": 22,
                "role": "body",
            },
        ]
    )

    text = append_physical_lane_summary("Layout AUTO", app)

    assert (
        "C1/L1: center=3.0   corrected=2.0-5.0   raw=4.0-9.0   "
        "n=8   role=entry"
    ) in text
    assert (
        "C1/L2: center=15.0   corrected=13.0-17.0   raw=16.0-22.0   "
        "n=5   role=body"
    ) in text
    assert "unknown" not in text
