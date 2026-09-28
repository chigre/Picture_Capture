from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.models import AppSettings
from picture_capture.text_line_geometry import analyze_text_line_geometry


def _tilted_box(
    x0: float,
    y0: float,
    width: float,
    height: float,
    angle_deg: float,
) -> np.ndarray:
    slope = math.tan(math.radians(angle_deg))
    dy = slope * width
    return np.asarray(
        [
            [x0, y0],
            [x0 + width, y0 + dy],
            [x0 + width, y0 + height + dy],
            [x0, y0 + height],
        ],
        dtype=float,
    )


def _two_column_polygons(
    *,
    rows: int = 22,
    angle_at=lambda _t: 0.0,
) -> list[np.ndarray]:
    polygons: list[np.ndarray] = [_tilted_box(360, 55, 120, 22, 0.0)]
    for row in range(rows):
        y = 150 + row * 32
        t = row / max(1, rows - 1)
        angle = float(angle_at(t))
        polygons.extend(
            (
                _tilted_box(80, y, 280, 20, angle),
                _tilted_box(500, y, 280, 20, angle),
            )
        )
    return polygons


def test_line_geometry_recommends_deskew_for_uniform_row_angle() -> None:
    image = Image.new("RGB", (900, 1000), "white")
    draw = ImageDraw.Draw(image)
    draw.line((430, 140, 430, 870), fill="black", width=2)

    analysis = analyze_text_line_geometry(
        image,
        _two_column_polygons(angle_at=lambda _t: 0.42),
        AppSettings(),
    )

    assert analysis.row_count >= 18
    assert abs(analysis.global_angle_deg - 0.42) < 0.08
    assert abs(analysis.angle_trend_deg) < 0.08
    assert analysis.separator_found
    assert analysis.separator_residual_px <= 2.5
    assert analysis.recommendation == "deskew"


def test_line_geometry_tracks_slanted_physical_separator() -> None:
    image = Image.new("RGB", (900, 1000), "white")
    draw = ImageDraw.Draw(image)
    top, bottom = 140, 870
    draw.line((420, top, 438, bottom), fill="black", width=2)

    analysis = analyze_text_line_geometry(
        image,
        _two_column_polygons(angle_at=lambda _t: 0.18),
        AppSettings(),
    )

    assert analysis.separator_found
    assert analysis.separator_span_ratio >= 0.55
    assert abs(analysis.separator_drift_px) >= 10
    assert abs(analysis.separator_slope_px_per_1000y) >= 10
    assert analysis.separator_residual_px <= 3.0


def test_line_geometry_recommends_perspective_for_coherent_angle_trend() -> None:
    image = Image.new("RGB", (900, 1000), "white")
    draw = ImageDraw.Draw(image)
    draw.line((430, 140, 430, 870), fill="black", width=2)

    analysis = analyze_text_line_geometry(
        image,
        _two_column_polygons(angle_at=lambda t: -0.12 + 0.48 * t),
        AppSettings(),
    )

    assert analysis.row_count >= 18
    assert analysis.angle_trend_deg > 0.35
    assert analysis.residual_mad_deg < 0.12
    assert analysis.separator_found
    assert analysis.separator_residual_px <= 2.5
    assert analysis.recommendation == "perspective"


def test_perspective_recommendation_does_not_require_separator() -> None:
    image = Image.new("RGB", (900, 1000), "white")

    analysis = analyze_text_line_geometry(
        image,
        _two_column_polygons(angle_at=lambda t: -0.12 + 0.48 * t),
        AppSettings(),
    )

    assert analysis.row_count >= 18
    assert analysis.separator_found is False
    assert analysis.angle_trend_deg > 0.35
    assert analysis.recommendation == "perspective"
    assert analysis.confidence >= 0.8


def test_line_geometry_uses_curved_real_separator_for_uvdoc_review() -> None:
    image = Image.new("RGB", (900, 1000), "white")
    draw = ImageDraw.Draw(image)
    top, bottom = 140, 870
    previous = None
    for y in range(top, bottom + 1):
        phase = (y - top) / max(1, bottom - top) * 2.0 * math.pi
        point = (round(430 + 8.0 * math.sin(phase)), y)
        if previous is not None:
            draw.line((*previous, *point), fill="black", width=2)
        previous = point

    analysis = analyze_text_line_geometry(
        image,
        _two_column_polygons(angle_at=lambda _t: 0.0),
        AppSettings(),
    )

    assert analysis.separator_found
    assert analysis.separator_span_ratio >= 0.55
    assert analysis.separator_residual_px >= 5.0
    assert analysis.recommendation == "uvdoc_review"


def test_straight_separator_blocks_false_nonlinear_interpretation() -> None:
    image = Image.new("RGB", (900, 1000), "white")
    draw = ImageDraw.Draw(image)
    draw.line((430, 140, 430, 870), fill="black", width=2)

    # Deliberately introduce row-to-row OCR angle noise while the real physical
    # separator remains straight. This is analogous to dictionary typography
    # producing noisy OCR geometry without actual page curvature.
    pattern = (0.0, 0.36, -0.31, 0.28, -0.34, 0.1)
    analysis = analyze_text_line_geometry(
        image,
        _two_column_polygons(
            rows=24,
            angle_at=lambda t: pattern[
                min(len(pattern) - 1, int(t * len(pattern)))
            ],
        ),
        AppSettings(),
    )

    assert analysis.separator_found
    assert analysis.separator_residual_px <= 2.5
    assert analysis.recommendation != "uvdoc_review"
