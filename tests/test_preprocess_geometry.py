from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.models import AppSettings
from picture_capture.preprocess_geometry import (
    LayoutDewarpEstimate,
    apply_layout_dewarp_image,
    estimate_layout_dewarp_from_polygons,
    estimate_perspective_from_polygons,
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


def test_layout_dewarp_detects_slow_column_bow() -> None:
    polygons: list[np.ndarray] = [_box(420, 45, 100, 18)]
    for row in range(30):
        y = 120 + row * 26
        phase = (row / 29.0) * np.pi
        bow = 9.0 * np.sin(phase)
        polygons.extend(
            (
                _box(100 + bow, y),
                _box(490 + bow * 0.8, y),
            )
        )

    estimate = estimate_layout_dewarp_from_polygons(
        polygons, (900, 1000), AppSettings(),
    )

    assert estimate.strength_px >= 3
    assert len(estimate.y_samples) >= 7
    assert len(estimate.target_starts) == 2
    assert len(estimate.source_starts) == len(estimate.y_samples)


def test_layout_dewarp_straightens_bowed_vertical_guides() -> None:
    width, height = 420, 520
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    ys = tuple(float(v) for v in np.linspace(0, height - 1, 11))
    rows = []
    for y in ys:
        bow = 12.0 * np.sin((y / (height - 1)) * np.pi)
        rows.append((120.0 + bow, 300.0 + bow))
    estimate = LayoutDewarpEstimate(
        y_samples=ys,
        target_starts=(120.0, 300.0),
        source_starts=tuple(rows),
        strength_px=12.0,
    )
    for y in range(height):
        bow = 12.0 * np.sin((y / (height - 1)) * np.pi)
        x = round(120.0 + bow)
        draw.line((x, y, x, y), fill="black")

    corrected = apply_layout_dewarp_image(image, estimate)
    gray = np.asarray(corrected.convert("L"))
    detected = []
    for y in range(20, height - 20, 20):
        band = gray[y : y + 1, 105:140]
        detected.append(105 + int(np.argmin(band.mean(axis=0))))

    assert max(detected) - min(detected) <= 2
    assert abs(float(np.median(detected)) - 120.0) <= 1.5
