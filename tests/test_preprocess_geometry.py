from __future__ import annotations

import numpy as np
from picture_capture.models import AppSettings
from picture_capture.preprocess_geometry import (
    audit_homography_distortion,
    audit_text_scale_stability,
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
    assert text_audit.after_score > text_audit.before_score


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
    assert text_audit.verdict == "improved"
    assert text_audit.after_score < text_audit.before_score

