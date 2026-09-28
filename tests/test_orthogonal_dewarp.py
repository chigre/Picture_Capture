from __future__ import annotations

import math

import numpy as np
from PIL import Image

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
