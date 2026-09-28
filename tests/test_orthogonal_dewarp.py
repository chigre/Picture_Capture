from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from picture_capture import orthogonal_dewarp
from picture_capture.models import AppSettings
from picture_capture.orthogonal_dewarp import (
    apply_orthogonal_warp_image,
    estimate_orthogonal_warp,
    transform_points_orthogonal,
    transform_polygons_orthogonal,
)
from picture_capture.preprocess_geometry import audit_horizontal_alignment


def _rotated_box(
    cx: float,
    cy: float,
    width: float,
    height: float,
    angle_deg: float,
) -> np.ndarray:
    angle = math.radians(angle_deg)
    c = math.cos(angle)
    s = math.sin(angle)
    raw = np.asarray(
        [
            [-width / 2.0, -height / 2.0],
            [width / 2.0, -height / 2.0],
            [width / 2.0, height / 2.0],
            [-width / 2.0, height / 2.0],
        ],
        dtype=float,
    )
    mapped = np.empty_like(raw)
    mapped[:, 0] = cx + raw[:, 0] * c - raw[:, 1] * s
    mapped[:, 1] = cy + raw[:, 0] * s + raw[:, 1] * c
    return mapped


def _warped_dictionary_polygons() -> list[np.ndarray]:
    polygons: list[np.ndarray] = []
    for column, cx in enumerate((270.0, 760.0)):
        for row in range(24):
            t = row / 23.0
            y = 130.0 + row * 38.0 + column * 6.0
            angle = 0.52 - 1.04 * t
            polygons.append(_rotated_box(cx, y, 330.0, 22.0, angle))
    return polygons


def test_orthogonal_warp_flattens_top_and_bottom_rows_and_separator(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (1050, 1100), "white")
    polygons = _warped_dictionary_polygons()
    separator = tuple(
        (
            120.0 + index * 40.0,
            520.0
            + 7.0 * ((index / 23.0) - 0.5)
            + 3.0 * math.sin(index / 23.0 * math.pi),
        )
        for index in range(24)
    )
    monkeypatch.setattr(
        orthogonal_dewarp,
        "separator_track_points",
        lambda *_args, **_kwargs: separator,
    )
    settings = AppSettings(layout_columns_policy="fixed", columns=2)

    estimate = estimate_orthogonal_warp(image, polygons, settings)
    transformed = transform_polygons_orthogonal(polygons, estimate)
    audit = audit_horizontal_alignment(
        polygons, transformed, size=image.size, settings=settings,
    )

    assert estimate.active is True
    assert estimate.row_count >= 40
    assert estimate.valid_column_count == 2
    assert estimate.max_row_angle_deg >= 0.35
    assert estimate.max_horizontal_shift_px >= 2.0
    assert estimate.max_scale_deviation <= 0.035
    assert audit.after_worst_region_deg <= 0.18
    assert max(abs(value) for value in audit.after_column_trends_deg) <= 0.12
    assert audit.after_top_edge_p90_abs_deg <= 0.18
    assert audit.after_bottom_edge_p90_abs_deg <= 0.18

    separator_array = np.asarray(
        [[x, y] for y, x in separator],
        dtype=float,
    )
    straightened = transform_points_orthogonal(separator_array, estimate)
    assert np.percentile(straightened[:, 0], 95) - np.percentile(
        straightened[:, 0], 5
    ) <= 1.5


def test_orthogonal_warp_stays_inactive_for_already_level_page(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (1050, 1100), "white")
    polygons: list[np.ndarray] = []
    for cx in (270.0, 760.0):
        for row in range(20):
            polygons.append(
                _rotated_box(cx, 150.0 + row * 42.0, 330.0, 22.0, 0.03)
            )
    monkeypatch.setattr(
        orthogonal_dewarp,
        "separator_track_points",
        lambda *_args, **_kwargs: (),
    )

    estimate = estimate_orthogonal_warp(
        image,
        polygons,
        AppSettings(layout_columns_policy="fixed", columns=2),
    )

    assert estimate.active is False
    assert estimate.max_row_angle_deg < 0.14


def test_orthogonal_image_warp_preserves_canvas_size(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (900, 1000), "white")
    polygons: list[np.ndarray] = []
    for cx in (230.0, 660.0):
        for row in range(18):
            t = row / 17.0
            polygons.append(
                _rotated_box(
                    cx,
                    130.0 + row * 44.0,
                    280.0,
                    20.0,
                    0.42 - 0.84 * t,
                )
            )
    monkeypatch.setattr(
        orthogonal_dewarp,
        "separator_track_points",
        lambda *_args, **_kwargs: (),
    )
    estimate = estimate_orthogonal_warp(
        image,
        polygons,
        AppSettings(layout_columns_policy="fixed", columns=2),
    )

    output = apply_orthogonal_warp_image(image, estimate)

    assert output.size == image.size


def test_2d_row_field_handles_column_disagreement_and_header_rule(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (1050, 1100), "white")
    polygons: list[np.ndarray] = []
    for row in range(24):
        t = row / 23.0
        y = 150.0 + row * 37.0
        # Deliberately make the right upper column more tilted. The previous
        # shared-angle implementation treated this >0.35° disagreement as a
        # reason to disable the correction entirely.
        left_angle = 0.38 - 0.78 * t
        right_angle = 0.88 - 1.28 * t
        polygons.append(_rotated_box(270.0, y, 330.0, 22.0, left_angle))
        polygons.append(_rotated_box(760.0, y + 5.0, 330.0, 22.0, right_angle))

    header = tuple(
        (80.0 + index * 38.0, 105.0 + 0.010 * (80.0 + index * 38.0))
        for index in range(24)
    )
    monkeypatch.setattr(
        orthogonal_dewarp,
        "separator_track_points",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        orthogonal_dewarp,
        "horizontal_rule_track_points",
        lambda *_args, **_kwargs: header,
    )
    settings = AppSettings(layout_columns_policy="fixed", columns=2)

    estimate = estimate_orthogonal_warp(image, polygons, settings)

    assert estimate.active is True
    assert estimate.column_spread_deg > 0.35
    assert estimate.row_grid_cols >= 4
    assert estimate.horizontal_rule_point_count >= 20

    # Production optimizes the same small gain family against absolute final
    # horizontality. Select the best synthetic candidate using the strict trend
    # gate, then verify the header rule with that same gain.
    candidates = []
    for gain in (0.85, 1.0, 1.10, 1.15):
        transformed = transform_polygons_orthogonal(
            polygons, estimate, row_gain=gain
        )
        audit = audit_horizontal_alignment(
            polygons,
            transformed,
            size=image.size,
            settings=settings,
        )
        worst_trend = max(
            abs(value) for value in audit.after_column_trends_deg
        )
        objective = max(
            audit.after_worst_region_deg / 0.18,
            worst_trend / 0.12,
            audit.after_top_edge_p90_abs_deg / 0.18,
            audit.after_bottom_edge_p90_abs_deg / 0.18,
        )
        candidates.append((objective, gain, audit))
    _objective, best_gain, audit = min(candidates, key=lambda item: item[0])

    assert audit.after_worst_region_deg <= 0.18
    assert max(abs(value) for value in audit.after_column_trends_deg) <= 0.12

    header_array = np.asarray(header, dtype=float)
    mapped_header = transform_points_orthogonal(
        header_array, estimate, row_gain=best_gain
    )
    slope, _intercept = np.polyfit(
        mapped_header[:, 0],
        mapped_header[:, 1],
        1,
    )
    mapped_angle = math.degrees(math.atan(float(slope)))
    assert abs(mapped_angle) <= 0.10



def test_orthogonal_bottom_boundary_does_not_extrapolate_past_last_right_rows(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (1050, 1150), "white")
    polygons: list[np.ndarray] = []

    # Left column extends farther down the page. The right column ends earlier
    # while retaining a clear negative residual at its last measured rows.
    for row in range(24):
        t = row / 23.0
        polygons.append(
            _rotated_box(
                270.0,
                140.0 + row * 39.0,
                330.0,
                22.0,
                0.40 - 0.72 * t,
            )
        )
    for row in range(20):
        t = row / 19.0
        polygons.append(
            _rotated_box(
                760.0,
                150.0 + row * 39.0,
                330.0,
                22.0,
                0.48 - 0.88 * t,
            )
        )

    monkeypatch.setattr(
        orthogonal_dewarp,
        "separator_track_points",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        orthogonal_dewarp,
        "horizontal_rule_track_points",
        lambda *_args, **_kwargs: (),
    )
    estimate = estimate_orthogonal_warp(
        image,
        polygons,
        AppSettings(layout_columns_policy="fixed", columns=2),
    )

    grid = np.asarray(estimate.row_angle_grid_deg, dtype=float).reshape(
        estimate.row_grid_rows,
        estimate.row_grid_cols,
    )
    x_knots = np.asarray(estimate.x_knots, dtype=float)
    right_index = int(np.argmin(np.abs(x_knots - 760.0)))
    # The final grid value must stay negative like the last real right-column
    # rows; a one-sided local regression must not flip or invent a new trend.
    assert grid[-1, right_index] <= -0.18
    assert np.min(grid[-3:, right_index]) >= -0.60



def test_pixel_projection_recovers_local_angle_when_ocr_hint_is_biased() -> None:
    image = Image.new("RGB", (1000, 900), "white")
    draw = ImageDraw.Draw(image)
    target_angle = -0.62
    slope = math.tan(math.radians(target_angle))
    rows: list[tuple[float, float, float, float]] = []
    for index in range(15):
        cy = 220.0 + index * 30.0
        x0 = 120.0
        x1 = 880.0
        y0 = cy - slope * (x1 - x0) / 2.0
        y1 = cy + slope * (x1 - x0) / 2.0
        # Broken segments mimic text rather than one continuous ruling line.
        for start in range(120, 860, 74):
            end = min(880, start + 48)
            t0 = (start - x0) / (x1 - x0)
            t1 = (end - x0) / (x1 - x0)
            sy = y0 * (1.0 - t0) + y1 * t0
            ey = y0 * (1.0 - t1) + y1 * t1
            draw.line((start, sy, end, ey), fill="black", width=3)
        # Deliberately biased OCR angle hint; the physical pixels must win.
        rows.append((500.0, cy, -0.20, 760.0))

    angle, confidence = orthogonal_dewarp._pixel_projection_angle(
        image,
        rows,
        440.0,
        250.0,
        AppSettings(),
        -0.20,
    )

    assert confidence >= orthogonal_dewarp.PIXEL_ANGLE_MIN_CONFIDENCE
    assert abs(angle - target_angle) <= 0.10


def test_pixel_projection_field_overrides_systematic_polygon_angle_bias(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (1000, 1000), "white")
    polygons: list[np.ndarray] = []
    for cx in (260.0, 740.0):
        for row in range(20):
            y = 150.0 + row * 38.0
            polygons.append(_rotated_box(cx, y, 300.0, 22.0, -0.20))

    monkeypatch.setattr(
        orthogonal_dewarp,
        "separator_track_points",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        orthogonal_dewarp,
        "horizontal_rule_track_points",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        orthogonal_dewarp,
        "_pixel_projection_angle",
        lambda *_args, **_kwargs: (-0.58, 0.40),
    )

    estimate = estimate_orthogonal_warp(
        image,
        polygons,
        AppSettings(layout_columns_policy="fixed", columns=2),
    )
    grid = np.asarray(estimate.row_angle_grid_deg, dtype=float)

    assert estimate.pixel_angle_used_count >= 10
    assert estimate.pixel_angle_confidence >= 0.30
    assert np.median(grid) <= -0.50



def test_pixel_row_profile_audit_detects_cross_column_row_bend() -> None:
    settings = AppSettings(layout_columns_policy="fixed", columns=1)
    polygons: list[np.ndarray] = []
    bent = Image.new("RGB", (900, 950), "white")
    straight = Image.new("RGB", (900, 950), "white")
    bent_draw = ImageDraw.Draw(bent)
    straight_draw = ImageDraw.Draw(straight)

    for row in range(18):
        y = 120.0 + row * 42.0
        polygons.append(_rotated_box(450.0, y, 720.0, 22.0, 0.0))
        for start, end, offset in (
            (110, 320, 4),
            (345, 555, 0),
            (580, 790, -4),
        ):
            for x in range(start, end, 55):
                bent_draw.line(
                    (x, y + offset, min(end, x + 38), y + offset),
                    fill="black",
                    width=3,
                )
                straight_draw.line(
                    (x, y, min(end, x + 38), y),
                    fill="black",
                    width=3,
                )

    bent_audit = orthogonal_dewarp.audit_pixel_row_profiles(
        bent, polygons, settings,
    )
    straight_audit = orthogonal_dewarp.audit_pixel_row_profiles(
        straight, polygons, settings,
    )

    assert bent_audit.sample_count >= 8
    assert bent_audit.p90_shift_px >= 3.0
    assert bent_audit.passed is False
    assert straight_audit.sample_count >= 8
    assert straight_audit.p90_shift_px <= 1.0
    assert straight_audit.passed is True


def test_pixel_angle_field_samples_multiple_x_positions_inside_column(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (900, 950), "white")
    polygons = [
        _rotated_box(450.0, 120.0 + row * 42.0, 720.0, 22.0, -0.20)
        for row in range(18)
    ]

    monkeypatch.setattr(
        orthogonal_dewarp,
        "separator_track_points",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        orthogonal_dewarp,
        "horizontal_rule_track_points",
        lambda *_args, **_kwargs: (),
    )

    def fake_pixel_angle(
        _image,
        _rows,
        _y,
        _radius,
        _settings,
        fallback,
        *,
        x_center=None,
        x_window=None,
    ):
        assert x_window is not None
        if x_center is None:
            return float(fallback), 0.0
        if x_center < 360.0:
            return -0.55, 0.35
        if x_center > 540.0:
            return 0.20, 0.35
        return -0.15, 0.35

    monkeypatch.setattr(
        orthogonal_dewarp,
        "_pixel_projection_angle",
        fake_pixel_angle,
    )

    estimate = estimate_orthogonal_warp(
        image,
        polygons,
        AppSettings(layout_columns_policy="fixed", columns=1),
    )
    grid = np.asarray(
        estimate.row_angle_grid_deg,
        dtype=float,
    ).reshape(estimate.row_grid_rows, estimate.row_grid_cols)

    assert estimate.pixel_angle_used_count >= 12
    assert estimate.row_grid_cols >= 6
    assert float(np.max(grid) - np.min(grid)) >= 0.55
