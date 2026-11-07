"""R7.3 RED-first malformed layout-transform construction contracts."""
from __future__ import annotations

import pytest

from picture_capture.geometry.layout_transform import LayoutTransform
from picture_capture.preprocess.coordinate_mapping import (
    CoordinateMappingUnavailable,
    PreprocessCoordinateMap,
)
from picture_capture.preprocess.models import PreprocessAnalysis


def _analysis() -> PreprocessAnalysis:
    return PreprocessAnalysis(
        source_width=20,
        source_height=30,
        correction_angle_deg=0.0,
        applied_angle_deg=0.0,
        crop_box=(0, 0, 20, 30),
        raw_content_box=(0, 0, 20, 30),
        text_box=(0, 0, 20, 30),
        source_boxes=0,
        angle_samples=0,
        angle_mad_deg=0.0,
        retained_ratio=1.0,
        confidence=1.0,
        status="synthetic",
        method="r7_3_malformed_layout_transform_contract",
        geometry_mode="perspective",
        perspective_matrix=None,
        orthogonal_applied=False,
        orthogonal_steps=(),
    )


@pytest.mark.parametrize("kind", (None, [], {}, 1, True))
def test_layout_transform_rejects_non_string_or_unknown_kind_with_value_error(kind):
    with pytest.raises(ValueError, match="Unsupported layout transform"):
        LayoutTransform(kind)


def test_coordinate_map_rejects_non_layout_transform_object():
    with pytest.raises(CoordinateMappingUnavailable, match="layout transform"):
        PreprocessCoordinateMap(_analysis(), layout_transform="identity")


@pytest.mark.parametrize(
    "kind",
    ("identity", "mirror_x", "rotate_ccw90", "rotate_cw90"),
)
def test_layout_transform_keeps_all_supported_kinds(kind):
    assert LayoutTransform(kind).kind == kind
