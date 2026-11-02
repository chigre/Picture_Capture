"""R7.3 RED-first tests for malformed coordinate point scalar inputs.

Only synthetic point/polygon inputs; no image or persistence writes.
"""
from __future__ import annotations

import numpy as np
import pytest

from picture_capture.preprocess.coordinate_mapping import PreprocessCoordinateMap
from picture_capture.preprocess.models import PreprocessAnalysis


def _mapping() -> PreprocessCoordinateMap:
    analysis = PreprocessAnalysis(
        source_width=20,
        source_height=20,
        correction_angle_deg=0.0,
        applied_angle_deg=0.0,
        crop_box=(0, 0, 20, 20),
        raw_content_box=(0, 0, 20, 20),
        text_box=(0, 0, 20, 20),
        source_boxes=0,
        angle_samples=0,
        angle_mad_deg=0.0,
        retained_ratio=1.0,
        confidence=1.0,
        status="synthetic",
        method="r7_3_coordinate_scalar_contract",
        geometry_mode="perspective",
        perspective_matrix=None,
        orthogonal_applied=False,
        orthogonal_steps=(),
    )
    return PreprocessCoordinateMap(analysis)


@pytest.mark.parametrize(
    "point",
    (
        (True, 1.0),
        (1.0, False),
        (np.bool_(True), 1.0),
        (1.0, np.bool_(False)),
        ("12", 1.0),
        (1.0, "2"),
        (b"1", 2.0),
        "12",
        b"12",
        bytearray(b"12"),
    ),
)
def test_point_mapping_rejects_boolean_or_text_coordinates(point):
    with pytest.raises(ValueError, match="coordinate point"):
        _mapping().source_to_output_point(point)


def test_polygon_mapping_rejects_text_coordinates_instead_of_coercing_them():
    mapping = _mapping()
    polygon = (
        ("2", 2.0),
        (10.0, 2.0),
        (10.0, 10.0),
        (2.0, 10.0),
    )
    with pytest.raises(ValueError, match="coordinate point"):
        mapping.source_to_output_polygon(polygon)


@pytest.mark.parametrize(
    "point",
    (
        (1, 2),
        (1.25, 2.5),
        np.asarray((1.25, 2.5), dtype=np.float64),
        np.asarray((3, 4), dtype=np.int64),
    ),
)
def test_point_mapping_preserves_valid_integer_and_numpy_real_inputs(point):
    result = _mapping().source_to_output_point(point)
    assert result.status == "mapped"
    assert result.point == pytest.approx((float(point[0]), float(point[1])))
