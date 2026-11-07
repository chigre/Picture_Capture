"""R7.3: an applied orthogonal stage must carry replayable geometry."""
from __future__ import annotations

import pytest

from picture_capture.preprocess.coordinate_mapping import (
    CoordinateMappingUnavailable,
    PreprocessCoordinateMap,
)
from picture_capture.preprocess.models import PreprocessAnalysis


def _analysis(*, steps=()) -> PreprocessAnalysis:
    return PreprocessAnalysis(
        source_width=100,
        source_height=100,
        correction_angle_deg=0.0,
        applied_angle_deg=0.0,
        crop_box=(0, 0, 100, 100),
        raw_content_box=(0, 0, 100, 100),
        text_box=(0, 0, 100, 100),
        source_boxes=0,
        angle_samples=0,
        angle_mad_deg=0.0,
        retained_ratio=1.0,
        confidence=1.0,
        status="synthetic",
        method="r7_3_orthogonal_replay_contract",
        geometry_mode="deskew",
        perspective_matrix=None,
        orthogonal_applied=True,
        orthogonal_steps=steps,
    )


@pytest.mark.parametrize("case", ("missing", "empty_step", "incomplete_legacy", "partial_separator", "invalid_row_grid"))
def test_coordinate_map_rejects_applied_orthogonal_stage_without_replay_geometry(case):
    analysis = _analysis()
    if case == "empty_step":
        # The current decoder accepts this payload and silently builds an
        # identity point transform despite orthogonal_applied=True.
        analysis.orthogonal_steps = ({"row_gain": 0.7},)
    elif case == "incomplete_legacy":
        analysis.orthogonal_y_knots = (0.0, 50.0, 100.0)
        analysis.orthogonal_angle_knots_deg = ()
    elif case == "partial_separator":
        analysis.orthogonal_steps = (
            {"separator_y_knots": [0.0, 100.0]},
        )
    elif case == "invalid_row_grid":
        analysis.orthogonal_steps = (
            {
                "y_knots": [0.0, 100.0],
                "x_knots": [0.0, 100.0],
                "row_grid_rows": 3,
                "row_grid_cols": 2,
                "row_angle_grid_deg": [0.0] * 6,
            },
        )

    with pytest.raises(
        CoordinateMappingUnavailable,
        match="orthogonal.*replay|replay.*orthogonal",
    ):
        PreprocessCoordinateMap(analysis)


def test_coordinate_map_accepts_legacy_orthogonal_replay_geometry():
    analysis = _analysis()
    analysis.orthogonal_y_knots = (0.0, 50.0, 100.0)
    analysis.orthogonal_angle_knots_deg = (0.1, 0.0, -0.1)
    analysis.orthogonal_reference_x = 50.0

    mapping = PreprocessCoordinateMap(analysis)
    assert mapping.approximate is True
    result = mapping.source_to_output_point((40.0, 40.0))
    assert result.status == "mapped"


def test_coordinate_map_accepts_separator_only_orthogonal_replay_geometry():
    analysis = _analysis(
        steps=(
            {
                "row_gain": 1.0,
                "reference_x": 0.0,
                "separator_y_knots": [0.0, 100.0],
                "separator_shift_knots_px": [2.0, 2.0],
            },
        )
    )

    mapping = PreprocessCoordinateMap(analysis)
    result = mapping.source_to_output_point((40.0, 40.0))
    assert result.status == "mapped"
    assert result.point == pytest.approx((38.0, 40.0))
