"""R7.3 RED-first: tangential knot contacts after composed nonlinear stages.

Synthetic coordinate geometry only; no raster or persistent annotation writes.
"""
from __future__ import annotations

import math

from picture_capture.preprocess.coordinate_mapping import PreprocessCoordinateMap
from picture_capture.preprocess.models import PreprocessAnalysis


def _analysis() -> tuple[PreprocessAnalysis, float]:
    # The first stage's row-angle field varies linearly in X from +2 to -2
    # degrees. Its Y displacement is the integral of that slope field, so
    # transformed Y has a smooth local minimum at x=950 even though x=950 is
    # not a saved grid knot (the only X knots are 900 and 1000).
    first_stage = {
        "row_gain": 1.0,
        "reference_x": 900.0,
        "y_knots": [0.0, 101.0],
        "angle_knots_deg": [],
        "x_knots": [900.0, 1000.0],
        "row_grid_rows": 2,
        "row_grid_cols": 2,
        "row_angle_grid_deg": [2.0, -2.0, 2.0, -2.0],
        "row_displacement_grid_px": [],
        "separator_y_knots": [],
        "separator_shift_knots_px": [],
    }

    # The next stage has a narrow separator excursion at y=53. It moves the
    # exact tangency point past the half-open crop edge, but has returned to
    # zero by y=53.001.
    second_stage = {
        "row_gain": 1.0,
        "reference_x": 0.0,
        "y_knots": [],
        "angle_knots_deg": [],
        "x_knots": [],
        "row_grid_rows": 0,
        "row_grid_cols": 0,
        "row_angle_grid_deg": [],
        "row_displacement_grid_px": [],
        "separator_y_knots": [0.0, 53.0, 53.001, 101.0],
        "separator_shift_knots_px": [0.0, -47.0001, 0.0, 0.0],
    }

    source_y = 53.0 + 25.0 * math.tan(math.radians(2.0))
    analysis = PreprocessAnalysis(
        source_width=1000,
        source_height=101,
        correction_angle_deg=0.0,
        applied_angle_deg=0.0,
        crop_box=(0, 0, 997, 101),
        raw_content_box=(0, 0, 997, 101),
        text_box=(0, 0, 997, 101),
        source_boxes=0,
        angle_samples=0,
        angle_mad_deg=0.0,
        retained_ratio=1.0,
        confidence=1.0,
        status="synthetic",
        method="r7_3_tangential_knot_preimage",
        geometry_mode="perspective",
        perspective_matrix=None,
        orthogonal_applied=True,
        orthogonal_steps=(first_stage, second_stage),
    )
    return analysis, source_y


def test_polygon_fails_closed_when_composed_stage_path_touches_knot_without_crossing():
    analysis, source_y = _analysis()
    mapping = PreprocessCoordinateMap(analysis)

    # The true stage-1 input Y reaches exactly 53 at x=950, then rises again.
    # The ordinary 8 px edge samples land at x=948 and x=956, where Y is
    # respectively 53.001397 and 53.012571: both are above both saved knots.
    tangent = mapping.source_to_output_point((950.0, source_y))
    left_sample = mapping.source_to_output_point((948.0, source_y))
    right_sample = mapping.source_to_output_point((956.0, source_y))
    assert tangent.status == "outside_crop"
    assert left_sample.status == "mapped"
    assert right_sample.status == "mapped"

    polygon = (
        (900.0, source_y),
        (996.0, source_y),
        (996.0, source_y + 1.0),
        (900.0, source_y + 1.0),
    )
    vertices = tuple(mapping.source_to_output_point(point) for point in polygon)
    assert all(item.status == "mapped" for item in vertices)

    # Vertex-only and endpoint-bracketed knot checks miss the interior touch.
    # The polygon contract must nevertheless refuse this partially unmappable
    # ROI boundary.
    assert mapping.source_to_output_polygon(polygon) is None
