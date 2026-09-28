from __future__ import annotations

import numpy as np
from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.preprocess_geometry import (
    estimate_perspective_from_polygons,
    perspective_from_quad,
    transform_points_homography,
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


