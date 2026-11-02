"""R7.3 RED-first tests for strict persisted orthogonal replay scalars."""
from __future__ import annotations

import pytest

from picture_capture.preprocess.coordinate_mapping import (
    CoordinateMappingUnavailable,
    PreprocessCoordinateMap,
)
from picture_capture.preprocess.models import PreprocessAnalysis


def _payload(**overrides):
    payload = {
        "row_gain": 0.7,
        "reference_x": 50.0,
        "y_knots": [0.0, 50.0, 100.0],
        "angle_knots_deg": [],
        "x_knots": [0.0, 50.0, 100.0],
        "row_grid_rows": 3,
        "row_grid_cols": 3,
        "row_angle_grid_deg": [0.1] * 9,
        "row_displacement_grid_px": [],
        "separator_y_knots": [],
        "separator_shift_knots_px": [],
    }
    payload.update(overrides)
    return payload


def _analysis(payload) -> PreprocessAnalysis:
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
        method="r7_3_orthogonal_payload_scalar_contract",
        geometry_mode="perspective",
        perspective_matrix=None,
        orthogonal_applied=True,
        orthogonal_steps=(payload,),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("row_grid_rows", 3.5),
        ("row_grid_cols", 3.5),
        ("row_grid_rows", "3"),
        ("row_grid_cols", "3"),
        ("row_grid_rows", True),
        ("row_grid_cols", True),
    ),
)
def test_orthogonal_replay_rejects_noninteger_grid_dimensions(field, value):
    with pytest.raises(CoordinateMappingUnavailable, match="orthogonal"):
        PreprocessCoordinateMap(_analysis(_payload(**{field: value})))


@pytest.mark.parametrize("row_gain", (-0.5, True, "0.7", None))
def test_orthogonal_replay_rejects_negative_boolean_text_or_null_row_gain(row_gain):
    with pytest.raises(CoordinateMappingUnavailable, match="orthogonal"):
        PreprocessCoordinateMap(_analysis(_payload(row_gain=row_gain)))


def test_orthogonal_replay_keeps_legacy_missing_row_gain_default():
    payload = _payload()
    payload.pop("row_gain")
    mapping = PreprocessCoordinateMap(_analysis(payload))
    assert mapping.approximate is True
    assert mapping.source_to_output_point((40.0, 40.0)).status == "mapped"
