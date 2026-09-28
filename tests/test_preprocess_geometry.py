from __future__ import annotations

import numpy as np
from picture_capture.models import AppSettings
from picture_capture.preprocess_geometry import (
    audit_horizontal_alignment,
    audit_homography_distortion,
    audit_text_scale_stability,
    estimate_horizontal_perspective_from_polygons,
    estimate_perspective_from_polygons,
    perspective_from_quad,
    transform_points_homography,
    transform_polygons_homography,
)


def _box(x0: float, y0: float, width: float = 220, height: float = 18) -> np.ndarray:
    return np.asarray(
        [
            [x0, y0],
            [x0 + width, y0],
            [x0 + width, y0 + height],
            [x0, y0 + height],
        ],
        dtype=float,
    )


def _rotated_box(
    cx: float,
    cy: float,
    width: float,
    height: float,
    angle_deg: float,
) -> np.ndarray:
    half = np.asarray(
        [
            [-width / 2.0, -height / 2.0],
            [width / 2.0, -height / 2.0],
            [width / 2.0, height / 2.0],
            [-width / 2.0, height / 2.0],
        ],
        dtype=float,
    )
    radians = np.deg2rad(angle_deg)
    rotation = np.asarray(
        [
            [np.cos(radians), -np.sin(radians)],
            [np.sin(radians), np.cos(radians)],
        ],
        dtype=float,
    )
    return half @ rotation.T + np.asarray([cx, cy], dtype=float)


def test_horizontal_vanishing_candidate_flattens_y_dependent_row_angles() -> None:
    polygons: list[np.ndarray] = []
    for row in range(22):
        t = row / 21.0
        y = 140 + row * 34
        angle = 0.42 - 0.84 * t
        polygons.extend(
            (
                _rotated_box(260, y, 280, 22, angle),
                _rotated_box(650, y, 280, 22, angle),
            )
        )

    estimate = estimate_horizontal_perspective_from_polygons(
        polygons, (900, 1000),
    )
    transformed = transform_polygons_homography(polygons, estimate.matrix)
    audit = audit_horizontal_alignment(polygons, transformed)

    assert estimate.classification == "horizontal_vp"
    assert estimate.candidate_source == "horizontal_vp"
    assert estimate.horizontal_row_count >= 18
    assert abs(estimate.horizontal_vanishing_x) > 3000
    assert audit.verdict == "improved"
    assert abs(audit.before_trend_deg) > 0.6
    assert abs(audit.after_trend_deg) <= 0.12
    assert max(abs(audit.after_top_angle_deg), abs(audit.after_bottom_angle_deg)) <= 0.18
    assert audit.improvement_ratio >= 0.5


def test_horizontal_vanishing_candidate_keeps_character_scale_safe() -> None:
    polygons: list[np.ndarray] = []
    for row in range(22):
        t = row / 21.0
        y = 140 + row * 34
        angle = 0.36 - 0.72 * t
        polygons.extend(
            (
                _rotated_box(260, y, 280, 22, angle),
                _rotated_box(650, y, 280, 22, angle),
            )
        )

    estimate = estimate_horizontal_perspective_from_polygons(
        polygons, (900, 1000),
    )
    transformed = transform_polygons_homography(polygons, estimate.matrix)
    jacobian = audit_homography_distortion(
        estimate.matrix, (900, 1000), polygons=polygons,
    )
    scale = audit_text_scale_stability(
        polygons, transformed, (900, 1000),
    )

    assert jacobian.valid is True
    assert jacobian.horizontal_scale_span_ratio <= 0.04
    assert jacobian.vertical_scale_span_ratio <= 0.07
    assert scale.verdict == "stable"


def test_perspective_estimate_straightens_diverging_column_starts() -> None:
    polygons: list[np.ndarray] = [_box(420, 45, 100, 18)]
    for row in range(22):
        y = 120 + row * 34
        t = row / 21.0
        left = 90 + 12 * t
        right = 480 - 10 * t
        polygons.extend((_box(left, y), _box(right, y)))

    estimate = estimate_perspective_from_polygons(
        polygons, (900, 1000), AppSettings(),
    )

    assert estimate.strength_px >= 5.5
    src = np.asarray(estimate.source_quad, dtype=float).reshape(4, 2)
    mapped = transform_points_homography(src, estimate.matrix)
    dst = np.asarray(estimate.target_quad, dtype=float).reshape(4, 2)
    assert np.max(np.abs(mapped - dst)) < 1e-5
    assert abs(mapped[0, 0] - mapped[3, 0]) < 1e-5
    assert abs(mapped[1, 0] - mapped[2, 0]) < 1e-5
    assert estimate.classification == "keystone"
    assert estimate.width_change_ratio > 0.01
    assert estimate.scale_delta_ratio > 0.01


def test_parallel_column_drift_is_not_classified_as_keystone() -> None:
    polygons: list[np.ndarray] = [_box(420, 45, 100, 18)]
    for row in range(22):
        y = 120 + row * 34
        t = row / 21.0
        drift = 28.0 * t
        polygons.extend(
            (
                _box(90 + drift, y),
                _box(480 + drift, y),
            )
        )

    estimate = estimate_perspective_from_polygons(
        polygons, (900, 1000), AppSettings(),
    )

    assert estimate.strength_px > 10
    assert estimate.classification == "parallel_drift"
    assert abs(estimate.common_drift_px) > 15
    assert abs(estimate.width_delta_px) < 2
    assert estimate.width_change_ratio < 0.005
    assert estimate.scale_delta_ratio < 0.005


def test_manual_four_corner_perspective_maps_to_axis_aligned_rectangle() -> None:
    quad = (
        30.0, 20.0,
        370.0, 35.0,
        350.0, 480.0,
        45.0, 465.0,
    )
    estimate = perspective_from_quad(quad, (400, 500))
    source = np.asarray(quad, dtype=float).reshape(4, 2)
    mapped = transform_points_homography(source, estimate.matrix)

    assert abs(mapped[0, 1] - mapped[1, 1]) < 1e-5
    assert abs(mapped[2, 1] - mapped[3, 1]) < 1e-5
    assert abs(mapped[0, 0] - mapped[3, 0]) < 1e-5
    assert abs(mapped[1, 0] - mapped[2, 0]) < 1e-5
    assert estimate.strength_px > 0

def test_identity_homography_has_zero_local_scale_distortion() -> None:
    polygons = [_box(100 + (row % 2) * 360, 120 + row * 32, 260, 22) for row in range(20)]
    audit = audit_homography_distortion(
        (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        (900, 1000),
        polygons=polygons,
    )

    assert audit.valid is True
    assert audit.sample_count >= 25
    assert audit.horizontal_scale_span_ratio < 1e-9
    assert audit.vertical_scale_span_ratio < 1e-9
    assert audit.area_scale_span_ratio < 1e-9
    assert audit.anisotropy_p95_ratio < 1e-9


def test_identity_text_scale_field_is_exactly_stable() -> None:
    polygons: list[np.ndarray] = []
    for row in range(18):
        y = 160 + row * 38
        polygons.extend((_box(100, y, 280, 22), _box(500, y, 280, 22)))

    audit = audit_text_scale_stability(
        polygons, polygons, (900, 1000),
    )

    assert audit.verdict == "stable"
    assert abs(audit.inline_ratio_median - 1.0) < 1e-12
    assert abs(audit.cross_ratio_median - 1.0) < 1e-12
    assert audit.inline_ratio_span_ratio < 1e-12
    assert audit.cross_ratio_span_ratio < 1e-12
    assert audit.anisotropy_p95_ratio < 1e-12


def test_0004_style_homography_stays_within_auto_distortion_budget() -> None:
    matrix = (
        1.0176582443, 0.0144603422, -30.5796527,
        0.0, 1.0279464072, -8.1571133,
        0.0, 7.89669602e-6, 1.0,
    )
    polygons: list[np.ndarray] = []
    for row in range(24):
        y = 240 + row * 120
        polygons.extend((_box(180, y, 720, 24), _box(1260, y, 720, 24)))

    audit = audit_homography_distortion(
        matrix, (2480, 3567), polygons=polygons,
    )
    transformed = transform_polygons_homography(polygons, matrix)
    text_audit = audit_text_scale_stability(
        polygons, transformed, (2480, 3567),
    )

    assert audit.valid is True
    assert audit.horizontal_scale_span_ratio <= 0.04
    assert audit.vertical_scale_span_ratio <= 0.07
    assert audit.area_scale_span_ratio <= 0.055
    assert audit.anisotropy_p95_ratio <= 0.035
    assert text_audit.verdict == "stable"
    assert text_audit.inline_ratio_span_ratio <= 0.045
    assert text_audit.cross_ratio_span_ratio <= 0.075
    assert text_audit.anisotropy_p95_ratio <= 0.04


def test_0011_style_homography_is_detected_as_scale_instability() -> None:
    matrix = (
        0.983649529, -0.0250342872, 24.2672841,
        0.0, 0.938147196, 16.8167594,
        0.0, -1.76118462e-5, 1.0,
    )
    polygons: list[np.ndarray] = []
    for row in range(24):
        y = 220 + row * 120
        polygons.extend((_box(170, y, 700, 24), _box(1250, y, 700, 24)))

    audit = audit_homography_distortion(
        matrix, (2480, 3567), polygons=polygons,
    )
    transformed = transform_polygons_homography(polygons, matrix)
    text_audit = audit_text_scale_stability(
        polygons, transformed, (2480, 3567),
    )

    assert audit.valid is True
    assert audit.horizontal_scale_span_ratio > 0.04
    assert audit.vertical_scale_span_ratio > 0.07
    assert audit.area_scale_span_ratio > 0.055
    assert audit.anisotropy_p95_ratio > 0.035
    assert text_audit.sample_count >= 40
    assert text_audit.verdict == "worse"
    assert text_audit.inline_ratio_span_ratio > 0.045
    assert text_audit.cross_ratio_span_ratio > 0.075
    assert text_audit.anisotropy_p95_ratio > 0.04


def test_text_scale_audit_recognizes_corrective_homography() -> None:
    estimate = perspective_from_quad(
        (
            120.0, 120.0,
            820.0, 150.0,
            770.0, 900.0,
            160.0, 870.0,
        ),
        (960, 1040),
    )
    matrix = np.asarray(estimate.matrix, dtype=float).reshape(3, 3)
    inverse = np.linalg.inv(matrix).reshape(-1)

    canonical: list[np.ndarray] = []
    for row in range(20):
        y = 180 + row * 34
        canonical.extend((_box(120, y, 300, 22), _box(500, y, 300, 22)))
    distorted = [
        transform_points_homography(poly, inverse)
        for poly in canonical
    ]
    corrected = transform_polygons_homography(distorted, estimate.matrix)
    text_audit = audit_text_scale_stability(
        distorted, corrected, (960, 1040),
    )

    assert text_audit.sample_count >= 30
    # This deliberately large correction improves the synthetic page's absolute
    # size trend, but the paired ratio field still records how strongly the
    # transform itself rescaled text. Automatic mode may therefore remain
    # conservative even when a manual/ground-truth correction is meaningful.
    assert text_audit.after_score < text_audit.before_score
    assert text_audit.inline_ratio_p05 > 0
    assert text_audit.inline_ratio_p95 >= text_audit.inline_ratio_p05
    assert text_audit.cross_ratio_p95 >= text_audit.cross_ratio_p05

