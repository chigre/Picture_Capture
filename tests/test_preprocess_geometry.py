from __future__ import annotations

import numpy as np
from picture_capture.models import AppSettings
from picture_capture.preprocess_geometry import (
    audit_horizontal_alignment,
    audit_homography_distortion,
    PerspectiveEstimate,
    audit_text_scale_stability,
    estimate_horizontal_perspective_from_polygons,
    estimate_perspective_from_polygons,
    optimize_horizontal_perspective_strength,
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


def test_horizontal_vanishing_candidate_does_not_flip_for_left_side_vp() -> None:
    polygons: list[np.ndarray] = []
    for row in range(22):
        t = row / 21.0
        y = 140 + row * 34
        angle = -0.42 + 0.84 * t
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

    assert estimate.horizontal_vanishing_x < 0
    assert audit.verdict == "improved"
    # The first box should remain on the left half of the page; a homogeneous
    # direction-sign mistake would rotate the page by ~180 degrees.
    before_center = polygons[0].mean(axis=0)
    after_center = transformed[0].mean(axis=0)
    assert before_center[0] < 450
    assert after_center[0] < 450
    assert abs(audit.after_trend_deg) <= 0.12


def test_horizontal_strength_optimizer_avoids_full_strength_overshoot() -> None:
    polygons: list[np.ndarray] = []
    for row in range(24):
        t = row / 23.0
        y = 130 + row * 32
        angle = 0.40 - 0.80 * t
        polygons.extend(
            (
                _rotated_box(250, y, 280, 22, angle),
                _rotated_box(650, y, 280, 22, angle),
            )
        )

    correct = estimate_horizontal_perspective_from_polygons(
        polygons, (900, 1000),
    )
    correct_matrix = np.asarray(correct.matrix, dtype=float).reshape(3, 3)
    exaggerated = np.eye(3, dtype=float) + 1.65 * (
        correct_matrix - np.eye(3, dtype=float)
    )
    exaggerated /= exaggerated[2, 2]
    full = PerspectiveEstimate(
        matrix=tuple(float(v) for v in exaggerated.reshape(-1)),
        source_quad=correct.source_quad,
        target_quad=correct.target_quad,
        strength_px=correct.strength_px * 1.65,
        classification="horizontal_vp",
        candidate_source="horizontal_vp",
        horizontal_vanishing_x=correct.horizontal_vanishing_x,
        horizontal_vanishing_y=correct.horizontal_vanishing_y,
        horizontal_row_count=correct.horizontal_row_count,
    )

    optimized, audit, strength = optimize_horizontal_perspective_strength(
        polygons, (900, 1000), full,
    )
    transformed = transform_polygons_homography(polygons, optimized.matrix)
    verified = audit_horizontal_alignment(polygons, transformed)

    assert 0.45 <= strength <= 0.80
    assert audit.verdict == "improved"
    assert verified.verdict == "improved"
    assert abs(verified.after_trend_deg) <= 0.12
    assert max(
        abs(verified.after_top_angle_deg),
        abs(verified.after_bottom_angle_deg),
    ) <= 0.18


def test_horizontal_geometry_separates_staggered_rows_across_three_columns() -> None:
    settings = AppSettings(layout_columns_policy="fixed", columns=3)
    polygons: list[np.ndarray] = []
    centers = (190.0, 590.0, 990.0)
    offsets = (0.0, 11.0, 23.0)
    for column, (cx, offset) in enumerate(zip(centers, offsets)):
        for row in range(20):
            t = row / 19.0
            y = 150 + row * 42 + offset
            angle = 0.36 - 0.72 * t
            polygons.append(_rotated_box(cx, y, 260, 22, angle))

    estimate = estimate_horizontal_perspective_from_polygons(
        polygons, (1200, 1100), settings,
    )
    optimized, audit, _strength = optimize_horizontal_perspective_strength(
        polygons, (1200, 1100), estimate, settings,
    )
    transformed = transform_polygons_homography(polygons, optimized.matrix)
    verified = audit_horizontal_alignment(
        polygons, transformed, size=(1200, 1100), settings=settings,
    )

    assert estimate.horizontal_column_count == 3
    assert audit.valid_column_count == 3
    assert verified.valid_column_count == 3
    assert len(verified.column_row_counts) == 3
    assert min(verified.column_row_counts) >= 18
    assert verified.verdict == "improved"
    assert verified.after_worst_region_deg <= 0.18
    assert max(abs(value) for value in verified.after_column_trends_deg) <= 0.12


def test_horizontal_geometry_auto_detects_three_columns_without_cross_row_pairing() -> None:
    settings = AppSettings(layout_columns_policy="detect")
    polygons: list[np.ndarray] = []
    centers = (170.0, 520.0, 870.0)
    offsets = (0.0, 13.0, 25.0)
    for cx, offset in zip(centers, offsets):
        for row in range(19):
            t = row / 18.0
            y = 135 + row * 43 + offset
            angle = 0.34 - 0.68 * t
            polygons.append(_rotated_box(cx, y, 210, 21, angle))

    estimate = estimate_horizontal_perspective_from_polygons(
        polygons, (1050, 1050), settings,
    )
    transformed = transform_polygons_homography(polygons, estimate.matrix)
    audit = audit_horizontal_alignment(
        polygons, transformed, size=(1050, 1050), settings=settings,
    )

    assert estimate.horizontal_column_count == 3
    assert audit.column_count == 3
    assert audit.valid_column_count == 3
    assert audit.verdict == "improved"
    assert audit.after_worst_region_deg <= 0.18


def test_horizontal_geometry_supports_two_three_and_n_columns() -> None:
    for columns in (2, 3, 4, 5):
        width = 300 * columns
        settings = AppSettings(layout_columns_policy="fixed", columns=columns)
        polygons: list[np.ndarray] = []
        for column in range(columns):
            cx = 150 + column * 300
            y_offset = float((column % 3) * 7)
            for row in range(18):
                t = row / 17.0
                y = 140 + row * 42 + y_offset
                angle = 0.30 - 0.60 * t
                polygons.append(_rotated_box(cx, y, 190, 20, angle))

        estimate = estimate_horizontal_perspective_from_polygons(
            polygons, (width, 1000), settings,
        )
        transformed = transform_polygons_homography(polygons, estimate.matrix)
        audit = audit_horizontal_alignment(
            polygons, transformed, size=(width, 1000), settings=settings,
        )

        assert estimate.horizontal_column_count == columns
        assert audit.valid_column_count == columns
        assert audit.verdict == "improved"
        assert audit.after_worst_region_deg <= 0.18


def test_worst_column_residual_cannot_hide_in_page_average() -> None:
    settings = AppSettings(layout_columns_policy="fixed", columns=2)
    before: list[np.ndarray] = []
    after: list[np.ndarray] = []
    for column, cx in enumerate((260.0, 760.0)):
        for row in range(20):
            t = row / 19.0
            y = 150 + row * 40 + column * 9
            before_angle = 0.32 - 0.64 * t
            # Left column is fully corrected. Right-column lower third retains
            # a visible tilt that a whole-page average must not conceal.
            after_angle = (
                -0.26
                if column == 1 and row >= 13
                else 0.0
            )
            before.append(_rotated_box(cx, y, 300, 22, before_angle))
            after.append(_rotated_box(cx, y, 300, 22, after_angle))

    audit = audit_horizontal_alignment(
        before, after, size=(1050, 1100), settings=settings,
    )

    assert audit.valid_column_count == 2
    assert audit.after_worst_column_index == 1
    assert audit.after_worst_region_deg > 0.18
    assert audit.verdict != "improved"


def test_horizontal_vp_evidence_includes_localized_region_span() -> None:
    settings = AppSettings(layout_columns_policy="fixed", columns=2)
    polygons: list[np.ndarray] = []
    for column, cx in enumerate((260.0, 760.0)):
        for row in range(21):
            y = 145 + row * 40 + column * 7
            # Most of each column is already level; only the lower third keeps
            # a consistent residual. Robust trend fitting may down-weight this,
            # so direct region span must still trigger horizontal-VP analysis.
            angle = -0.22 if row >= 14 else 0.0
            polygons.append(_rotated_box(cx, y, 300, 22, angle))

    identity_audit = audit_horizontal_alignment(
        polygons, polygons, size=(1050, 1100), settings=settings,
    )
    estimate = estimate_horizontal_perspective_from_polygons(
        polygons, (1050, 1100), settings,
    )

    assert identity_audit.before_worst_region_span_deg >= 0.18
    assert estimate.horizontal_column_count == 2
    assert estimate.horizontal_row_count >= 30


def test_localized_lower_right_tilt_is_caught_by_region_gate() -> None:
    settings = AppSettings(layout_columns_policy="fixed", columns=2)
    before: list[np.ndarray] = []
    after: list[np.ndarray] = []
    for column, cx in enumerate((260.0, 760.0)):
        for row in range(21):
            t = row / 20.0
            y = 145 + row * 40 + column * 8
            before_angle = 0.30 - 0.60 * t
            # Only the final five rows of the right column remain visibly
            # tilted. A whole-column linear trend can dilute this local defect,
            # but the direct bottom-region median must keep it visible.
            after_angle = (
                -0.24
                if column == 1 and row >= 16
                else 0.0
            )
            before.append(_rotated_box(cx, y, 300, 22, before_angle))
            after.append(_rotated_box(cx, y, 300, 22, after_angle))

    audit = audit_horizontal_alignment(
        before, after, size=(1050, 1100), settings=settings,
    )

    assert audit.valid_column_count == 2
    assert audit.after_worst_column_index == 1
    assert audit.after_column_bottom_angles_deg[1] <= -0.18
    assert audit.after_worst_region_deg >= 0.18
    assert audit.verdict != "improved"


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

