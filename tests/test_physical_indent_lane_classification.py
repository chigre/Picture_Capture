from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from picture_capture.layout_grid_inference import indent_width_modes
from picture_capture.layout_lane_summary_extension import append_physical_lane_summary
from picture_capture.layout_physical_role_refinement import assign_refined_physical_roles


def _line(first_x: int) -> SimpleNamespace:
    return SimpleNamespace(
        first_x=first_x,
        anchor_x=first_x,
        has_small_prefix=False,
        patch=np.zeros((0, 0), dtype=bool),
    )


def test_nearby_but_visibly_distinct_physical_lanes_are_not_merged() -> None:
    # At 50-px text height the old 0.24*height tolerance was 12 px and would
    # merge these flush-left headword and nearby '~' continuation lanes.
    lines = [_line(2), _line(4), _line(5), _line(13), _line(15), _line(16)]

    modes = indent_width_modes(lines, reference=50.0)

    assert len(modes) == 2
    assert [round(mode.center) for mode in modes] == [4, 15]
    assert {line.first_x for line in modes[0].lines} == {2, 4, 5}
    assert {line.first_x for line in modes[1].lines} == {13, 15, 16}


def test_lane_role_assignment_uses_physical_clusters_only() -> None:
    entry_lines = [_line(2), _line(3), _line(4), _line(3)]
    continuation_lines = [_line(14), _line(15), _line(16), _line(15)]
    body_lines = [_line(34), _line(35), _line(36), _line(35), _line(34), _line(36)]
    modes = indent_width_modes(entry_lines + continuation_lines + body_lines, reference=50.0)
    column = SimpleNamespace(indent_modes=modes, body_mode=None, entry_modes=[])

    assign_refined_physical_roles(column, "body", reference=50.0)

    by_center = {round(mode.center): mode for mode in modes}
    assert by_center[3].role == "entry"
    assert by_center[15].role == "unknown"
    assert by_center[35].role == "body"


def test_lane_summary_reports_cluster_geometry_support_and_role() -> None:
    app = SimpleNamespace(
        _layout_visualization_indent_lanes=[
            {"column": 0, "lane": 0, "center": 3.0, "min": 2.0, "max": 5.0, "support": 8, "role": "entry"},
            {"column": 0, "lane": 1, "center": 15.0, "min": 13.0, "max": 17.0, "support": 5, "role": "unknown"},
            {"column": 0, "lane": 2, "center": 35.0, "min": 32.0, "max": 38.0, "support": 22, "role": "body"},
        ]
    )

    text = append_physical_lane_summary("Layout AUTO", app)

    assert "physical indent lanes:" in text
    assert "C1/L1: center=3.0   range=2.0-5.0   n=8   role=entry" in text
    assert "C1/L2: center=15.0   range=13.0-17.0   n=5   role=unknown" in text
    assert "C1/L3: center=35.0   range=32.0-38.0   n=22   role=body" in text
