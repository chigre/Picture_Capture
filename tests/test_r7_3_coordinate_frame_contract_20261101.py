"""R7.3: read-only source→canonical→preprocessed coordinate-map contract tests.

These tests deliberately use synthetic geometry only. They do not rewrite PDIC,
PPP, SECTION, crop plans, preprocessing metadata, or source images.
"""
from __future__ import annotations

import numpy as np
import pytest

from picture_capture.geometry.layout_transform import LayoutTransform
from picture_capture.preprocess.canvas import output_canvas_info
from picture_capture.preprocess.models import PreprocessAnalysis
from picture_capture.preprocess.orthogonal_dewarp import (
    OrthogonalWarpEstimate,
    inverse_transform_points_orthogonal,
    transform_points_orthogonal,
)


def _orthogonal_step() -> dict[str, object]:
    return {
        "row_gain": 0.7,
        "reference_x": 50.0,
        "y_knots": [0.0, 50.0, 100.0],
        "angle_knots_deg": [0.1, 0.15, 0.2],
        "x_knots": [0.0, 50.0, 100.0],
        "row_grid_rows": 3,
        "row_grid_cols": 3,
        "row_angle_grid_deg": [
            0.05, 0.10, 0.15,
            0.10, 0.15, 0.20,
            0.15, 0.20, 0.25,
        ],
        "row_displacement_grid_px": [],
        "separator_y_knots": [0.0, 50.0, 100.0],
        "separator_shift_knots_px": [0.0, 1.0, -0.5],
    }


def _analysis(
    *,
    source_size: tuple[int, int] = (100, 100),
    crop_box: tuple[int, int, int, int] = (5, 5, 95, 95),
    geometry_mode: str = "perspective",
    applied_angle_deg: float = 0.35,
    perspective_matrix: tuple[float, ...] | None = (
        1.0, 0.0005, 2.0,
        -0.0003, 1.0, 1.5,
        0.000001, -0.000001, 1.0,
    ),
    orthogonal_steps: tuple[dict[str, object], ...] = (_orthogonal_step(),),
) -> PreprocessAnalysis:
    width, height = source_size
    return PreprocessAnalysis(
        source_width=width,
        source_height=height,
        correction_angle_deg=0.0,
        applied_angle_deg=applied_angle_deg,
        crop_box=crop_box,
        raw_content_box=crop_box,
        text_box=crop_box,
        source_boxes=0,
        angle_samples=0,
        angle_mad_deg=0.0,
        retained_ratio=0.81,
        confidence=1.0,
        status="synthetic",
        method="r7_3_coordinate_contract",
        geometry_mode=geometry_mode,
        perspective_matrix=perspective_matrix,
        orthogonal_applied=bool(orthogonal_steps),
        orthogonal_steps=orthogonal_steps,
    )


def test_layout_transform_maps_source_to_canonical_and_back_for_points_and_boxes():
    source_size = (101, 151)
    points = ((0, 0), (100, 150), (20, 50), (73, 91))
    boxes = ((0, 0, 1, 1), (5, 8, 33, 41), (97, 147, 101, 151))

    for kind in ("identity", "mirror_x", "rotate_ccw90", "rotate_cw90"):
        transform = LayoutTransform(kind)
        for point in points:
            canonical = transform.source_to_canonical_point(*point, source_size)
            assert transform.canonical_to_source_point(*canonical, source_size) == point
        for box in boxes:
            canonical = transform.source_box_to_canonical(box, source_size)
            assert transform.canonical_box_to_source(canonical, source_size) == box


def test_orthogonal_forward_and_inverse_point_mapping_share_the_image_mesh_contract():
    estimate = OrthogonalWarpEstimate(
        y_knots=(0.0, 50.0, 100.0),
        angle_knots_deg=(0.1, 0.15, 0.2),
        x_knots=(0.0, 50.0, 100.0),
        row_grid_rows=3,
        row_grid_cols=3,
        row_angle_grid_deg=(
            0.05, 0.10, 0.15,
            0.10, 0.15, 0.20,
            0.15, 0.20, 0.25,
        ),
        separator_y_knots=(0.0, 50.0, 100.0),
        separator_shift_knots_px=(0.0, 1.0, -0.5),
        reference_x=50.0,
        active=True,
    )
    source = np.asarray(((20.0, 18.0), (62.5, 54.0), (83.0, 81.0)))
    mapped = transform_points_orthogonal(
        source, estimate, row_gain=0.7, separator_gain=1.0,
    )
    restored = inverse_transform_points_orthogonal(
        mapped, estimate, row_gain=0.7, separator_gain=1.0,
    )
    assert np.allclose(restored, source, atol=0.02)


def test_coordinate_map_composes_layout_homography_orthogonal_crop_and_canvas_roundtrip():
    from picture_capture.preprocess.coordinate_mapping import (
        COORDINATE_MAPPING_CONTRACT_VERSION,
        PreprocessCoordinateMap,
    )

    analysis = _analysis()
    canvas = output_canvas_info(
        analysis,
        enabled=True,
        mode="custom",
        requested_width=130,
        requested_height=120,
        canvas_width=130,
        canvas_height=120,
        margin_top=10,
        margin_bottom=10,
        margin_left=15,
        margin_right=15,
        align_x="center",
        align_y="center",
    )
    mapping = PreprocessCoordinateMap(analysis=analysis, canvas=canvas)
    source_point = (40.25, 42.5)

    output = mapping.source_to_output_point(source_point)
    assert output.status == "mapped"
    assert output.point is not None
    assert output.contract_version == COORDINATE_MAPPING_CONTRACT_VERSION == 1
    assert output.approximate is True

    restored = mapping.output_to_source_point(output.point)
    assert restored.status == "mapped"
    assert restored.point is not None
    assert np.allclose(restored.point, source_point, atol=0.02)


def test_coordinate_map_uses_layout_transform_as_the_canonical_stage():
    from picture_capture.preprocess.coordinate_mapping import PreprocessCoordinateMap

    source_size = (100, 80)
    transform = LayoutTransform("rotate_ccw90")
    canonical_size = transform.canonical_size(source_size)
    analysis = _analysis(
        source_size=canonical_size,
        crop_box=(0, 0, canonical_size[0], canonical_size[1]),
        applied_angle_deg=0.0,
        perspective_matrix=None,
        orthogonal_steps=(),
    )
    mapping = PreprocessCoordinateMap(
        analysis=analysis,
        source_size=source_size,
        layout_transform=transform,
    )
    source_point = (10.0, 20.0)
    output = mapping.source_to_output_point(source_point)
    assert output.status == "mapped"
    assert output.point == (20.0, 89.0)
    restored = mapping.output_to_source_point(output.point)
    assert np.allclose(restored.point, source_point, atol=1e-9)


def test_coordinate_map_fails_closed_for_uvdoc_and_points_outside_crop():
    from picture_capture.preprocess.coordinate_mapping import (
        CoordinateMappingUnavailable,
        PreprocessCoordinateMap,
    )

    with pytest.raises(CoordinateMappingUnavailable, match="UVDoc"):
        PreprocessCoordinateMap(
            _analysis(
                geometry_mode="uvdoc",
                perspective_matrix=None,
                orthogonal_steps=(),
            )
        )

    mapping = PreprocessCoordinateMap(
        _analysis(
            crop_box=(20, 20, 80, 80),
            applied_angle_deg=0.0,
            perspective_matrix=None,
            orthogonal_steps=(),
        )
    )
    outside = mapping.source_to_output_point((5.0, 5.0))
    assert outside.status == "outside_crop"
    assert outside.point is None


def test_coordinate_map_refuses_analysis_whose_dimensions_do_not_match_canonical_frame():
    from picture_capture.preprocess.coordinate_mapping import PreprocessCoordinateMap

    with pytest.raises(ValueError, match="canonical"):
        PreprocessCoordinateMap(
            _analysis(source_size=(100, 100), applied_angle_deg=0.0),
            source_size=(100, 80),
            layout_transform=LayoutTransform("rotate_ccw90"),
        )


def test_coordinate_map_roundtrips_roi_polygon_vertices_and_refuses_partial_crop():
    from picture_capture.preprocess.coordinate_mapping import PreprocessCoordinateMap

    analysis = _analysis()
    mapping = PreprocessCoordinateMap(analysis=analysis)
    polygon = ((30.0, 30.0), (60.0, 30.0), (60.0, 60.0), (30.0, 60.0))
    output = mapping.source_to_output_polygon(polygon)
    assert output is not None and len(output) == 4
    restored = mapping.output_to_source_polygon(output)
    assert restored is not None and len(restored) == 4
    assert np.allclose(restored, polygon, atol=0.02)

    crossing = ((0.0, 30.0), (60.0, 30.0), (60.0, 60.0), (0.0, 60.0))
    assert mapping.source_to_output_polygon(crossing) is None
