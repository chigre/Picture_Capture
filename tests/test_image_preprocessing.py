from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from picture_capture import image_preprocessing
from picture_capture.image_preprocessing import (
    PreprocessAnalysis,
    analysis_is_current,
    analyze_preprocess_page,
    estimate_skew_from_polygons,
    clear_manual_perspective_quad,
    load_analysis,
    load_manual_perspective_quad,
    output_canvas_info,
    overlay_excluded_regions,
    processed_image_with_canvas,
    promote_processed_pages,
    export_diagnostic_json,
    export_summary_csv,
    geometry_corrected_image,
    save_analysis,
    save_manual_perspective_quad,
)
from picture_capture.layout_detection import detect_text_polygons
from picture_capture.models import AppSettings


def _tilted_box(
    x0: float, y0: float, width: float, height: float, angle_deg: float,
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


def test_polygon_skew_estimator_preserves_small_angle() -> None:
    polygons = [
        _tilted_box(80, 100 + row * 45, 260, 28, 1.25)
        for row in range(12)
    ]
    angle, samples, mad = estimate_skew_from_polygons(polygons)

    assert samples >= 20
    assert abs(angle - 1.25) < 0.08
    assert mad < 0.05


def test_text_polygon_detection_preserves_polygon_geometry(monkeypatch) -> None:
    class FakeDetector:
        @staticmethod
        def predict(_image, **_kwargs):
            return [
                {
                    "res": {
                        "dt_polys": [
                            [[10, 20], [110, 23], [109, 48], [9, 45]],
                        ]
                    }
                }
            ]

    import picture_capture.layout_detection as layout_detection

    monkeypatch.setattr(layout_detection, "_get_text_detector", lambda _settings: FakeDetector())
    polygons = detect_text_polygons(Image.new("RGB", (200, 120), "white"), AppSettings())

    assert len(polygons) == 1
    assert polygons[0].shape == (4, 2)
    assert polygons[0][1, 1] == 23
    assert polygons[0][2, 0] == 109


def test_preprocess_crop_uses_layout_columns_not_edge_ink(monkeypatch) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    draw = ImageDraw.Draw(image)
    # Strong scanner/binding noise must not influence normal structural cropping.
    draw.rectangle((3, 60, 12, 1340), fill="black")
    polygons = [
        _tilted_box(350, 80, 120, 24, 0.0),  # running header
        _tilted_box(4, 300, 8, 120, 0.0),  # 0008-like left-edge false detection
    ]
    for row in range(20):
        y = 180 + row * 48
        left = _tilted_box(100, y, 300, 24, 0.0)
        right = _tilted_box(460, y, 300, 24, 0.0)
        polygons.extend((left, right))
        draw.rectangle((100, y, 400, y + 24), fill="black")
        draw.rectangle((460, y, 760, y + 24), fill="black")

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: polygons,
    )
    analysis = analyze_preprocess_page(
        image,
        AppSettings(),
        safety_margin_px=20,
        auto_deskew=True,
    )

    x0, y0, x1, y1 = analysis.crop_box
    assert x0 == 80
    assert 775 <= x1 <= 785
    assert y0 == 60
    assert y1 < 1200
    assert analysis.method.startswith("paddle_layout_roi")
    assert analysis.source_boxes >= 40
    assert not any("投影回退" in warning for warning in analysis.warnings)


def test_deskewed_layout_keeps_fixed_margin_after_correction(monkeypatch) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    polygons = [_tilted_box(350, 80, 120, 24, 1.25)]  # running header
    for row in range(20):
        y = 180 + row * 48
        polygons.extend(
            (
                _tilted_box(100, y, 300, 24, 1.25),
                _tilted_box(460, y, 300, 24, 1.25),
            )
        )

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: polygons,
    )
    analysis = analyze_preprocess_page(
        image,
        AppSettings(),
        safety_margin_px=20,
        auto_deskew=True,
    )

    assert abs(analysis.applied_angle_deg) > 0.5
    raw_x0, raw_y0, raw_x1, raw_y1 = analysis.raw_content_box
    crop_x0, crop_y0, crop_x1, crop_y1 = analysis.crop_box
    assert raw_x0 - crop_x0 == 20
    assert raw_y0 - crop_y0 == 20
    assert crop_x1 - raw_x1 == 20
    assert crop_y1 - raw_y1 == 20


def _two_column_angle_field(angle_at) -> list[np.ndarray]:
    polygons = [_tilted_box(350, 80, 120, 24, 0.0)]
    for row in range(20):
        y = 180 + row * 48
        t = row / 19.0
        angle = float(angle_at(t))
        polygons.extend(
            (
                _tilted_box(100, y, 300, 24, angle),
                _tilted_box(460, y, 300, 24, angle),
            )
        )
    return polygons


def test_auto_geometry_uses_orthogonal_dewarp_not_uvdoc_for_nonlinear_rows(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    warped = _two_column_angle_field(lambda t: 0.50 - 1.00 * t)
    flattened = _two_column_angle_field(lambda _t: 0.0)
    detect_calls = 0

    def fake_detect(_image, _settings):
        nonlocal detect_calls
        detect_calls += 1
        return warped if detect_calls == 1 else flattened

    monkeypatch.setattr(image_preprocessing, "detect_text_polygons", fake_detect)
    monkeypatch.setattr(
        image_preprocessing,
        "unwarp_document_image",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("auto nonlinear correction must not invoke UVDoc")
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "analyze_text_line_geometry",
        lambda *_args, **_kwargs: image_preprocessing.TextLineGeometryAnalysis(
            row_count=40,
            separator_found=True,
            separator_residual_px=9.0,
            separator_span_ratio=0.9,
            separator_track_quality=0.95,
            separator_curvature_score=0.8,
            separator_curve_reliable=True,
            recommendation="uvdoc_review",
            confidence=0.9,
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "estimate_orthogonal_warp",
        lambda *_args, **_kwargs: image_preprocessing.OrthogonalWarpEstimate(
            y_knots=(180.0, 1092.0),
            angle_knots_deg=(0.50, -0.50),
            reference_x=500.0,
            row_count=40,
            valid_column_count=2,
            separator_point_count=8,
            max_row_angle_deg=0.50,
            row_angle_span_deg=1.0,
            max_vertical_shift_px=4.4,
            max_scale_deviation=0.01,
            confidence=0.95,
            active=True,
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "apply_orthogonal_warp_image",
        lambda source, *_args, **_kwargs: source.copy(),
    )
    separator_calls = 0

    def fake_separator_track(_image, _polygons, _settings):
        nonlocal separator_calls
        separator_calls += 1
        if separator_calls == 1:
            return tuple(
                (100.0 + i * 100.0, 500.0 + i * 1.5)
                for i in range(8)
            )
        return tuple(
            (100.0 + i * 100.0, 505.0 + i * 0.1)
            for i in range(8)
        )

    monkeypatch.setattr(
        image_preprocessing,
        "separator_track_points",
        fake_separator_track,
    )

    analysis = analyze_preprocess_page(
        image,
        AppSettings(layout_columns_policy="fixed", columns=2),
        safety_margin_px=20,
        auto_deskew=True,
        geometry_mode="auto",
    )

    assert analysis.geometry_mode == "orthogonal"
    assert analysis.orthogonal_applied is True
    assert analysis.orthogonal_row_gain > 0
    assert "orthogonal_dewarp" in analysis.method
    assert analysis.line_geometry_recommendation == "uvdoc_review"
    assert analysis.final_alignment_verdict == "passed"
    assert analysis.final_alignment_top_edge_p90_abs_deg <= 0.18
    assert analysis.final_alignment_bottom_edge_p90_abs_deg <= 0.18
    assert analysis.final_alignment_edge_pair_delta_p90_deg <= 0.15
    assert analysis.orthogonal_vertical_verdict == "passed"
    assert analysis.orthogonal_after_separator_span_px <= 3.5


def test_auto_geometry_rolls_back_orthogonal_candidate_without_real_improvement(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    warped = _two_column_angle_field(lambda t: 0.50 - 1.00 * t)

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: warped,
    )
    monkeypatch.setattr(
        image_preprocessing,
        "unwarp_document_image",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("auto nonlinear correction must not invoke UVDoc")
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "analyze_text_line_geometry",
        lambda *_args, **_kwargs: image_preprocessing.TextLineGeometryAnalysis(
            row_count=40,
            separator_found=True,
            separator_residual_px=9.0,
            separator_span_ratio=0.9,
            separator_track_quality=0.95,
            separator_curvature_score=0.8,
            separator_curve_reliable=True,
            recommendation="uvdoc_review",
            confidence=0.9,
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "estimate_orthogonal_warp",
        lambda *_args, **_kwargs: image_preprocessing.OrthogonalWarpEstimate(
            y_knots=(180.0, 1092.0),
            angle_knots_deg=(0.50, -0.50),
            reference_x=500.0,
            row_count=40,
            valid_column_count=2,
            max_row_angle_deg=0.50,
            row_angle_span_deg=1.0,
            max_vertical_shift_px=4.4,
            max_scale_deviation=0.01,
            confidence=0.95,
            active=True,
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "apply_orthogonal_warp_image",
        lambda source, *_args, **_kwargs: source.copy(),
    )

    analysis = analyze_preprocess_page(
        image,
        AppSettings(layout_columns_policy="fixed", columns=2),
        geometry_mode="auto",
    )

    assert analysis.geometry_mode != "orthogonal"
    assert analysis.geometry_mode != "uvdoc"
    assert analysis.orthogonal_applied is False
    assert any(
        "正交网格候选" in warning and "验收未通过" in warning
        for warning in analysis.warnings
    )
    assert any(
        "可手动选择UVDoc复核" in warning
        for warning in analysis.warnings
    )


def test_auto_perspective_requires_line_geometry_support(monkeypatch) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    polygons = [_tilted_box(350, 80, 120, 24, 0.0)]
    for row in range(20):
        y = 180 + row * 48
        polygons.extend(
            (
                _tilted_box(100, y, 300, 24, 0.0),
                _tilted_box(460, y, 300, 24, 0.0),
            )
        )

    class Perspective:
        strength_px = 20.0
        matrix = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: polygons,
    )
    monkeypatch.setattr(
        image_preprocessing,
        "estimate_perspective_from_polygons",
        lambda *_args, **_kwargs: Perspective(),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "analyze_text_line_geometry",
        lambda *_args, **_kwargs: image_preprocessing.TextLineGeometryAnalysis(
            row_count=20,
            recommendation="none",
            confidence=0.9,
        ),
    )

    def forbidden_homography(*_args, **_kwargs):
        raise AssertionError("auto mode must not apply unsupported perspective")

    monkeypatch.setattr(
        image_preprocessing, "apply_homography_image", forbidden_homography,
    )

    analysis = analyze_preprocess_page(
        image,
        AppSettings(),
        geometry_mode="auto",
    )

    assert analysis.geometry_mode == "deskew"
    assert "perspective_review" in analysis.method
    assert any("文本行几何证据不足" in warning for warning in analysis.warnings)


def test_auto_perspective_applies_with_coherent_line_support(monkeypatch) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    polygons = [_tilted_box(350, 80, 120, 24, 0.0)]
    for row in range(20):
        y = 180 + row * 48
        polygons.extend(
            (
                _tilted_box(100, y, 300, 24, 0.0),
                _tilted_box(460, y, 300, 24, 0.0),
            )
        )

    class Perspective:
        strength_px = 20.0
        matrix = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
        source_quad = (100.0, 100.0, 800.0, 100.0, 795.0, 1200.0, 105.0, 1200.0)
        target_quad = (105.0, 100.0, 795.0, 100.0, 795.0, 1200.0, 105.0, 1200.0)
        classification = "keystone"
        left_drift_px = 5.0
        right_drift_px = -5.0
        common_drift_px = 0.0
        width_delta_px = -10.0
        width_change_ratio = 0.014
        scale_top = 0.986
        scale_bottom = 1.0
        scale_delta_ratio = 0.014

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: polygons,
    )
    monkeypatch.setattr(
        image_preprocessing,
        "estimate_perspective_from_polygons",
        lambda *_args, **_kwargs: Perspective(),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "analyze_text_line_geometry",
        lambda *_args, **_kwargs: image_preprocessing.TextLineGeometryAnalysis(
            row_count=20,
            angle_trend_deg=0.35,
            recommendation="perspective",
            confidence=0.9,
        ),
    )
    class RowAudit:
        row_count = 20
        before_global_angle_deg = 0.0
        after_global_angle_deg = 0.0
        before_top_angle_deg = 0.22
        after_top_angle_deg = 0.04
        before_bottom_angle_deg = -0.22
        after_bottom_angle_deg = -0.04
        before_trend_deg = -0.44
        after_trend_deg = -0.08
        before_residual_mad_deg = 0.04
        after_residual_mad_deg = 0.04
        before_metric_deg = 0.43
        after_metric_deg = 0.09
        improvement_ratio = 0.79
        verdict = "improved"

    monkeypatch.setattr(
        image_preprocessing,
        "audit_horizontal_alignment",
        lambda *_args, **_kwargs: RowAudit(),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "apply_homography_image",
        lambda source, _matrix: source.copy(),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "transform_polygons_homography",
        lambda values, _matrix: list(values),
    )

    analysis = analyze_preprocess_page(
        image,
        AppSettings(),
        geometry_mode="auto",
    )

    assert analysis.geometry_mode == "perspective"
    assert "perspective" in analysis.method


def test_safe_structural_keystone_does_not_require_row_improvement(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    polygons = [_tilted_box(350, 80, 120, 24, 0.0)]
    for row in range(20):
        y = 180 + row * 48
        polygons.extend(
            (
                _tilted_box(100, y, 300, 24, 0.0),
                _tilted_box(460, y, 300, 24, 0.0),
            )
        )

    class Perspective:
        strength_px = 20.0
        matrix = (
            0.995, 0.0, 2.0,
            0.0, 1.0, 0.0,
            0.0, 0.0, 1.0,
        )
        source_quad = (
            100.0, 100.0,
            800.0, 100.0,
            795.0, 1200.0,
            105.0, 1200.0,
        )
        target_quad = (
            105.0, 100.0,
            795.0, 100.0,
            795.0, 1200.0,
            105.0, 1200.0,
        )
        classification = "keystone"
        candidate_source = "structural"
        left_drift_px = 5.0
        right_drift_px = -5.0
        common_drift_px = 0.0
        width_delta_px = -10.0
        width_change_ratio = 0.014
        scale_top = 0.986
        scale_bottom = 1.0
        scale_delta_ratio = 0.014
        horizontal_vanishing_x = 0.0
        horizontal_vanishing_y = 0.0
        horizontal_row_count = 0

    class StableRows:
        row_count = 20
        before_global_angle_deg = 0.0
        after_global_angle_deg = 0.0
        before_top_angle_deg = 0.10
        after_top_angle_deg = 0.10
        before_bottom_angle_deg = -0.10
        after_bottom_angle_deg = -0.10
        before_trend_deg = -0.20
        after_trend_deg = -0.20
        before_residual_mad_deg = 0.03
        after_residual_mad_deg = 0.03
        before_metric_deg = 0.20
        after_metric_deg = 0.20
        improvement_ratio = 0.0
        verdict = "stable"

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: polygons,
    )
    monkeypatch.setattr(
        image_preprocessing,
        "estimate_perspective_from_polygons",
        lambda *_args, **_kwargs: Perspective(),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "estimate_horizontal_perspective_from_polygons",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("no residual horizontal candidate")
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "audit_horizontal_alignment",
        lambda *_args, **_kwargs: StableRows(),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "analyze_text_line_geometry",
        lambda *_args, **_kwargs: image_preprocessing.TextLineGeometryAnalysis(
            row_count=20,
            angle_trend_deg=-0.20,
            recommendation="perspective",
            confidence=0.9,
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "apply_homography_image",
        lambda source, _matrix: source.copy(),
    )

    analysis = analyze_preprocess_page(
        image,
        AppSettings(),
        geometry_mode="auto",
    )

    assert analysis.geometry_mode == "perspective"
    assert analysis.perspective_candidate_source == "structural"
    assert analysis.perspective_structural_safe is True
    assert analysis.perspective_structural_applied is True
    assert analysis.perspective_auto_safe is True


def test_auto_geometry_can_use_horizontal_vanishing_point_without_ruling_line(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    polygons = [_tilted_box(350, 80, 120, 24, 0.0)]
    for row in range(22):
        y = 180 + row * 44
        t = row / 21.0
        angle = 0.38 - 0.76 * t
        polygons.extend(
            (
                _tilted_box(100, y, 300, 24, angle),
                _tilted_box(500, y, 300, 24, angle),
            )
        )

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: polygons,
    )
    monkeypatch.setattr(
        image_preprocessing,
        "estimate_perspective_from_polygons",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("no structural candidate")
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "analyze_text_line_geometry",
        lambda *_args, **_kwargs: image_preprocessing.TextLineGeometryAnalysis(
            row_count=22,
            angle_trend_deg=-0.76,
            recommendation="perspective",
            confidence=0.95,
            separator_found=False,
        ),
    )

    analysis = analyze_preprocess_page(
        image,
        AppSettings(),
        geometry_mode="auto",
    )

    assert analysis.geometry_mode == "perspective"
    assert analysis.perspective_candidate_source == "horizontal_vp"
    assert analysis.perspective_classification == "horizontal_vp"
    assert analysis.perspective_horizontal_row_count >= 18
    assert analysis.perspective_row_alignment_verdict == "improved"
    assert abs(analysis.perspective_row_after_trend_deg) <= 0.12
    assert analysis.perspective_auto_safe is True
    assert "horizontal_vp" in analysis.method


def test_reliable_nonlinear_curve_blocks_horizontal_vp_in_auto_mode(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    polygons = [_tilted_box(350, 80, 120, 24, 0.0)]
    for row in range(22):
        y = 180 + row * 44
        t = row / 21.0
        angle = 0.38 - 0.76 * t
        polygons.extend(
            (
                _tilted_box(100, y, 300, 24, angle),
                _tilted_box(500, y, 300, 24, angle),
            )
        )

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: polygons,
    )
    monkeypatch.setattr(
        image_preprocessing,
        "estimate_perspective_from_polygons",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("no structural candidate")
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "analyze_text_line_geometry",
        lambda *_args, **_kwargs: image_preprocessing.TextLineGeometryAnalysis(
            row_count=22,
            angle_trend_deg=-0.76,
            recommendation="uvdoc_review",
            confidence=0.95,
            separator_found=True,
            separator_curve_reliable=True,
            separator_residual_px=6.0,
            separator_span_ratio=1.0,
            separator_track_quality=0.98,
            separator_curvature_score=0.9,
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "estimate_orthogonal_warp",
        lambda *_args, **_kwargs: image_preprocessing.OrthogonalWarpEstimate(
            row_count=44,
            valid_column_count=2,
            confidence=0.95,
            active=False,
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "unwarp_document_image",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("auto mode must not invoke UVDoc")
        ),
    )

    analysis = analyze_preprocess_page(
        image,
        AppSettings(),
        geometry_mode="auto",
    )

    assert analysis.geometry_mode == "deskew"
    assert analysis.perspective_auto_safe is False
    assert "horizontal_vp" not in analysis.method
    assert analysis.orthogonal_applied is False
    assert any(
        "正交网格未能通过闭环验收" in warning
        for warning in analysis.warnings
    )


def test_0011_style_large_ocr_homography_is_blocked_even_with_separator(monkeypatch) -> None:
    image = Image.new("RGB", (2480, 3567), "white")
    polygons = [_tilted_box(900, 80, 160, 24, -0.46)]
    for row in range(24):
        y = 180 + row * 120
        polygons.extend(
            (
                _tilted_box(170, y, 700, 24, -0.46),
                _tilted_box(1250, y, 700, 24, -0.46),
            )
        )

    class Perspective:
        strength_px = 48.186
        matrix = (
            0.98365, -0.02503, 24.267,
            0.0, 0.93815, 16.817,
            0.0, -1.761e-5, 1.0,
        )
        source_quad = (
            160.0, 178.0,
            2330.0, 178.0,
            2280.0, 3218.0,
            185.0, 3218.0,
        )
        target_quad = (
            180.0, 178.0,
            2300.0, 178.0,
            2300.0, 3218.0,
            180.0, 3218.0,
        )
        classification = "keystone"
        left_drift_px = 25.0
        right_drift_px = -50.0
        common_drift_px = -12.5
        width_delta_px = -75.0
        width_change_ratio = 0.035
        scale_top = 0.9867
        scale_bottom = 1.0427
        scale_delta_ratio = 0.056

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: polygons,
    )
    monkeypatch.setattr(
        image_preprocessing,
        "estimate_perspective_from_polygons",
        lambda *_args, **_kwargs: Perspective(),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "analyze_text_line_geometry",
        lambda *_args, **_kwargs: image_preprocessing.TextLineGeometryAnalysis(
            row_count=57,
            global_angle_deg=-0.4581,
            angle_trend_deg=-0.7777,
            residual_mad_deg=0.0791,
            separator_found=True,
            separator_residual_px=1.8,
            separator_span_ratio=0.9,
            recommendation="perspective",
            confidence=0.9,
        ),
    )

    def forbidden_homography(*_args, **_kwargs):
        raise AssertionError("0011-style unsafe auto homography must be blocked")

    monkeypatch.setattr(
        image_preprocessing, "apply_homography_image", forbidden_homography,
    )

    analysis = analyze_preprocess_page(
        image,
        AppSettings(),
        geometry_mode="auto",
    )

    assert analysis.geometry_mode == "deskew"
    assert analysis.perspective_candidate_strength_px == 48.186
    assert analysis.perspective_scale_delta_ratio == 0.056
    assert analysis.perspective_auto_safe is False
    assert "perspective_review" in analysis.method
    assert analysis.perspective_jacobian_horizontal_scale_span_ratio > 0.04
    assert analysis.perspective_jacobian_vertical_scale_span_ratio > 0.07
    assert analysis.perspective_text_scale_verdict == "worse"
    assert analysis.perspective_text_scale_inline_ratio_span_ratio > 0.045
    assert analysis.perspective_text_scale_cross_ratio_span_ratio > 0.075
    assert analysis.perspective_text_scale_anisotropy_p95_ratio > 0.04
    assert any("局部尺度漂移" in warning for warning in analysis.warnings)
    assert any("配对文本框尺度场" in warning for warning in analysis.warnings)


def test_auto_parallel_drift_candidate_is_blocked_even_with_line_support(monkeypatch) -> None:
    image = Image.new("RGB", (1200, 1600), "white")
    polygons = [_tilted_box(400, 80, 140, 24, 0.0)]
    for row in range(20):
        y = 180 + row * 60
        polygons.extend(
            (
                _tilted_box(100, y, 360, 24, 0.0),
                _tilted_box(620, y, 360, 24, 0.0),
            )
        )

    class Perspective:
        strength_px = 30.0
        matrix = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
        source_quad = (100.0, 100.0, 800.0, 100.0, 830.0, 1400.0, 130.0, 1400.0)
        target_quad = (115.0, 100.0, 815.0, 100.0, 815.0, 1400.0, 115.0, 1400.0)
        classification = "parallel_drift"
        left_drift_px = 30.0
        right_drift_px = 30.0
        common_drift_px = 30.0
        width_delta_px = 0.0
        width_change_ratio = 0.0
        scale_top = 1.0
        scale_bottom = 1.0
        scale_delta_ratio = 0.0

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: polygons,
    )
    monkeypatch.setattr(
        image_preprocessing,
        "estimate_perspective_from_polygons",
        lambda *_args, **_kwargs: Perspective(),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "analyze_text_line_geometry",
        lambda *_args, **_kwargs: image_preprocessing.TextLineGeometryAnalysis(
            row_count=20,
            angle_trend_deg=0.5,
            recommendation="perspective",
            confidence=0.9,
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "apply_homography_image",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("parallel drift must not trigger auto homography")
        ),
    )

    analysis = analyze_preprocess_page(
        image,
        AppSettings(),
        geometry_mode="auto",
    )

    assert analysis.geometry_mode == "deskew"
    assert analysis.perspective_classification == "parallel_drift"
    assert analysis.perspective_auto_safe is False
    assert any("平行漂移" in warning for warning in analysis.warnings)


def test_uvdoc_mode_redetects_layout_after_unwarping(monkeypatch) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    polygons = [_tilted_box(350, 80, 120, 24, 0.0)]
    for row in range(20):
        y = 180 + row * 48
        polygons.extend(
            (
                _tilted_box(100, y, 300, 24, 0.0),
                _tilted_box(460, y, 300, 24, 0.0),
            )
        )

    calls = {"detect": 0, "uvdoc": 0}

    def fake_detect(_image, _settings):
        calls["detect"] += 1
        return polygons

    def fake_uvdoc(source):
        calls["uvdoc"] += 1
        return source.copy()

    monkeypatch.setattr(image_preprocessing, "detect_text_polygons", fake_detect)
    monkeypatch.setattr(image_preprocessing, "unwarp_document_image", fake_uvdoc)

    analysis = analyze_preprocess_page(
        image,
        AppSettings(),
        safety_margin_px=20,
        auto_deskew=True,
        geometry_mode="uvdoc",
    )

    assert analysis.requested_geometry_mode == "uvdoc"
    assert analysis.geometry_mode == "uvdoc"
    assert "uvdoc" in analysis.method
    assert "redetect" in analysis.method
    assert calls["uvdoc"] == 1
    assert calls["detect"] >= 2


def test_preview_overlay_marks_only_nonretained_area() -> None:
    source = Image.new("RGB", (100, 100), "white")
    preview = overlay_excluded_regions(source, (20, 20, 80, 80))

    assert preview.getpixel((5, 5)) != (255, 255, 255)
    assert preview.getpixel((50, 50)) == (255, 255, 255)
    assert preview.getpixel((20, 20)) != (255, 255, 255)


def _sample_export_analysis() -> PreprocessAnalysis:
    return PreprocessAnalysis(
        source_width=120,
        source_height=180,
        correction_angle_deg=0.0,
        applied_angle_deg=0.0,
        crop_box=(10, 20, 110, 170),
        raw_content_box=(12, 22, 108, 168),
        text_box=(12, 22, 108, 168),
        source_boxes=20,
        angle_samples=30,
        angle_mad_deg=0.1,
        retained_ratio=0.69,
        confidence=0.9,
        status="normal",
        method="paddle_layout_roi+line_geometry",
        line_geometry_rows=24,
        line_geometry_trend_deg=0.22,
        line_geometry_separator_found=True,
        line_geometry_separator_residual_px=1.4,
        line_geometry_separator_span_ratio=0.88,
        line_geometry_recommendation="perspective",
        line_geometry_confidence=0.86,
    )


def test_geometry_export_replays_saved_orthogonal_field(monkeypatch) -> None:
    analysis = _sample_export_analysis()
    analysis.geometry_mode = "orthogonal"
    analysis.orthogonal_applied = True
    analysis.orthogonal_row_count = 30
    analysis.orthogonal_valid_column_count = 2
    analysis.orthogonal_separator_point_count = 12
    analysis.orthogonal_row_gain = 0.85
    analysis.orthogonal_reference_x = 60.0
    analysis.orthogonal_y_knots = (20.0, 90.0, 160.0)
    analysis.orthogonal_angle_knots_deg = (0.4, 0.0, -0.4)
    analysis.orthogonal_separator_y_knots = (20.0, 160.0)
    analysis.orthogonal_separator_shift_knots_px = (2.0, -2.0)
    analysis.orthogonal_confidence = 0.9
    analysis.orthogonal_max_row_angle_deg = 0.4
    analysis.orthogonal_row_angle_span_deg = 0.8
    analysis.orthogonal_max_horizontal_shift_px = 2.0
    analysis.orthogonal_max_vertical_shift_px = 0.5
    analysis.orthogonal_max_scale_deviation = 0.01

    captured = {}

    def fake_apply(source, estimate, *, row_gain, separator_gain):
        captured["estimate"] = estimate
        captured["row_gain"] = row_gain
        captured["separator_gain"] = separator_gain
        return source.copy()

    monkeypatch.setattr(
        image_preprocessing,
        "apply_orthogonal_warp_image",
        fake_apply,
    )

    source = Image.new("RGB", (120, 180), "white")
    output = geometry_corrected_image(source, analysis)

    assert output.size == source.size
    assert captured["row_gain"] == 0.85
    assert captured["separator_gain"] == 1.0
    estimate = captured["estimate"]
    assert estimate.reference_x == 60.0
    assert estimate.y_knots == (20.0, 90.0, 160.0)
    assert estimate.angle_knots_deg == (0.4, 0.0, -0.4)
    assert estimate.separator_shift_knots_px == (2.0, -2.0)


def test_output_canvas_alignment_preserves_crop_without_rescaling() -> None:
    analysis = _sample_export_analysis()
    canvas = output_canvas_info(
        analysis,
        enabled=True,
        mode="custom",
        requested_width=200,
        requested_height=240,
        canvas_width=200,
        canvas_height=240,
        align_x="right",
        align_y="bottom",
    )

    assert canvas.width == 200
    assert canvas.height == 240
    assert canvas.content_box == (100, 90, 200, 240)

    source = Image.new("RGB", (120, 180), (80, 90, 100))
    exported = processed_image_with_canvas(source, analysis, canvas)
    assert exported.size == (200, 240)
    assert exported.getpixel((5, 5)) == (255, 255, 255)
    assert exported.getpixel((150, 150)) == (80, 90, 100)


def test_output_canvas_places_content_inside_page_body_margins() -> None:
    analysis = _sample_export_analysis()
    canvas = output_canvas_info(
        analysis,
        enabled=True,
        mode="custom",
        requested_width=240,
        requested_height=260,
        canvas_width=240,
        canvas_height=260,
        margin_top=20,
        margin_bottom=30,
        margin_left=15,
        margin_right=25,
        align_x="center",
        align_y="top",
    )

    assert canvas.width == 240
    assert canvas.height == 260
    assert canvas.body_box == (15, 20, 215, 230)
    assert canvas.content_box == (65, 20, 165, 170)

    source = Image.new("RGB", (120, 180), (80, 90, 100))
    exported = processed_image_with_canvas(source, analysis, canvas)
    assert exported.size == (240, 260)
    assert exported.getpixel((5, 5)) == (255, 255, 255)
    assert exported.getpixel((70, 25)) == (80, 90, 100)


def test_output_canvas_expands_page_to_preserve_body_margins() -> None:
    analysis = _sample_export_analysis()
    canvas = output_canvas_info(
        analysis,
        enabled=True,
        mode="custom",
        requested_width=120,
        requested_height=160,
        canvas_width=120,
        canvas_height=160,
        margin_top=10,
        margin_bottom=20,
        margin_left=12,
        margin_right=18,
        align_x="right",
        align_y="bottom",
    )

    assert canvas.width == 130
    assert canvas.height == 180
    assert canvas.body_box == (12, 10, 112, 160)
    assert canvas.content_box == (12, 10, 112, 160)
    assert canvas.expanded_width is True
    assert canvas.expanded_height is True


def test_output_canvas_expands_instead_of_scaling_oversize_content() -> None:
    analysis = _sample_export_analysis()
    canvas = output_canvas_info(
        analysis,
        enabled=True,
        mode="custom",
        requested_width=80,
        requested_height=100,
        canvas_width=80,
        canvas_height=100,
        align_x="center",
        align_y="center",
    )

    assert canvas.width == 100
    assert canvas.height == 150
    assert canvas.content_box == (0, 0, 100, 150)
    assert canvas.expanded_width is True
    assert canvas.expanded_height is True


def test_preprocess_export_writes_diagnostic_json_and_summary_csv(tmp_path: Path) -> None:
    analysis = _sample_export_analysis()
    page = tmp_path / "0004.tif"
    page.write_bytes(b"scan")
    output = tmp_path / "processed" / "0004.tif"
    canvas = output_canvas_info(
        analysis,
        enabled=True,
        mode="batch_max",
        requested_width=200,
        requested_height=240,
        canvas_width=200,
        canvas_height=240,
        margin_top=10,
        margin_bottom=20,
        margin_left=15,
        margin_right=25,
        align_x="center",
        align_y="top",
    )

    metadata = tmp_path / "meta" / "0004.preprocess.json"
    export_diagnostic_json(
        page,
        analysis,
        metadata,
        output_path=output,
        canvas=canvas,
        settings=AppSettings(
            columns=3,
            layout_columns_policy="fixed",
            preprocess_safety_margin_px=20,
            preprocess_geometry_mode="auto",
        ),
    )
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    assert payload["crop_box"] == [10, 20, 110, 170]
    assert payload["line_geometry_rows"] == 24
    assert payload["line_geometry_separator_residual_px"] == 1.4
    assert payload["export"]["canvas"]["width"] == 200
    assert payload["export"]["canvas"]["body_box"] == [15, 10, 175, 220]
    assert payload["export"]["canvas"]["content_box"] == [45, 10, 145, 160]
    assert payload["effective_settings"]["fixed_columns"] == 3
    assert payload["effective_settings"]["layout_columns_policy"] == "fixed"
    assert payload["algorithm_constants"]["max_auto_deskew_deg"] == 5.0
    assert (
        payload["algorithm_constants"]["auto_homography_horizontal_scale_span_max"]
        == 0.04
    )
    assert (
        payload["algorithm_constants"]["auto_homography_anisotropy_p95_max"]
        == 0.035
    )
    assert payload["algorithm_constants"]["text_scale_inline_span_max"] == 0.045
    assert payload["algorithm_constants"]["text_scale_cross_span_max"] == 0.075
    assert payload["algorithm_constants"]["text_scale_anisotropy_p95_max"] == 0.04
    assert payload["algorithm_constants"]["horizontal_vp_column_spread_max_deg"] == 0.35
    assert payload["algorithm_constants"]["horizontal_strength_min"] == 0.15
    assert payload["algorithm_constants"]["horizontal_strength_coarse_step"] == 0.10
    assert payload["algorithm_constants"]["horizontal_strength_fine_step"] == 0.025
    assert payload["algorithm_constants"]["separator_curve_span_min"] == 0.72
    assert payload["algorithm_constants"]["separator_curvature_score_min"] == 0.35

    summary = tmp_path / "preprocess_summary.csv"
    export_summary_csv([(page, analysis, output, canvas)], summary)
    text = summary.read_text(encoding="utf-8-sig")
    assert "line_geometry_recommendation" in text
    assert "separator_residual_px" in text
    assert "separator_drift_px" in text
    assert "perspective_scale_delta_ratio" in text
    assert "perspective_horizontal_strength" in text
    assert "perspective_row_valid_column_indices" in text
    assert "line_geometry_columns" in text
    assert "line_geometry_valid_column_indices" in text
    assert "line_geometry_worst_region_angle_deg" in text
    assert "perspective_structural_safe" in text
    assert "perspective_structural_applied" in text
    assert "perspective_jacobian_horizontal_scale_span_ratio" in text
    assert "perspective_jacobian_vertical_scale_span_ratio" in text
    assert "perspective_text_scale_inline_ratio_p05" in text
    assert "perspective_text_scale_inline_ratio_span_ratio" in text
    assert "perspective_text_scale_cross_ratio_span_ratio" in text
    assert "perspective_text_scale_anisotropy_p95_ratio" in text
    assert "perspective_text_scale_verdict" in text
    assert "separator_track_quality" in text
    assert "separator_track_jump_p95_px" in text
    assert "separator_curvature_score" in text
    assert "separator_curve_reliable" in text
    assert "perspective_auto_safe" in text
    assert "canvas_body_x0" in text
    assert "canvas_margin_top" in text
    assert "canvas_content_x0" in text
    assert "perspective" in text


def test_preprocess_analysis_roundtrip_and_source_signature(tmp_path: Path) -> None:
    page = tmp_path / "0001.png"
    Image.new("RGB", (120, 180), "white").save(page)
    stat = page.stat()
    analysis = PreprocessAnalysis(
        source_width=120,
        source_height=180,
        correction_angle_deg=0.5,
        applied_angle_deg=0.5,
        crop_box=(10, 12, 110, 170),
        raw_content_box=(12, 14, 108, 168),
        text_box=(15, 18, 105, 165),
        source_boxes=20,
        angle_samples=30,
        angle_mad_deg=0.1,
        retained_ratio=0.73,
        confidence=0.9,
        status="normal",
        method="paddle_layout_roi",
        safety_margin_px=20,
        auto_deskew=True,
        perspective_horizontal_column_count=3,
        perspective_row_valid_column_count=2,
        perspective_row_valid_column_indices=(0, 2),
        perspective_row_column_row_counts=(18, 2, 17),
        perspective_row_after_worst_region_deg=0.14,
        perspective_row_after_worst_column_index=2,
        line_geometry_columns=3,
        line_geometry_valid_columns=2,
        line_geometry_valid_column_indices=(0, 2),
        line_geometry_column_row_counts=(18, 2, 17),
        line_geometry_column_trends_deg=(-0.08, -0.11),
        line_geometry_worst_column_index=2,
        line_geometry_worst_column_trend_deg=-0.11,
        line_geometry_worst_region_angle_deg=0.16,
        source_size_bytes=stat.st_size,
        source_mtime_ns=stat.st_mtime_ns,
    )

    save_analysis(tmp_path, page, analysis)
    loaded = load_analysis(tmp_path, page)

    assert loaded is not None
    assert loaded.crop_box == analysis.crop_box
    assert loaded.auto_deskew is True
    assert loaded.perspective_row_valid_column_indices == (0, 2)
    assert loaded.perspective_row_column_row_counts == (18, 2, 17)
    assert loaded.line_geometry_columns == 3
    assert loaded.line_geometry_valid_column_indices == (0, 2)
    assert loaded.line_geometry_column_trends_deg == (-0.08, -0.11)
    assert loaded.line_geometry_worst_column_index == 2
    assert analysis_is_current(
        loaded, page, safety_margin_px=20, auto_deskew=True
    )
    assert not analysis_is_current(
        loaded, page, safety_margin_px=30, auto_deskew=True
    )
    assert not analysis_is_current(
        loaded, page, safety_margin_px=20, auto_deskew=False
    )


def test_preprocess_export_canvas_settings_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = AppSettings(
        preprocess_export_canvas_enabled=True,
        preprocess_export_canvas_mode="custom",
        preprocess_export_canvas_width=1800,
        preprocess_export_canvas_height=2400,
        preprocess_export_margin_top=30,
        preprocess_export_margin_bottom=40,
        preprocess_export_margin_left=50,
        preprocess_export_margin_right=60,
        preprocess_export_align_x="right",
        preprocess_export_align_y="bottom",
    )
    settings.to_json(path)
    reopened = AppSettings.from_json(path)

    assert reopened.preprocess_export_canvas_enabled is True
    assert reopened.preprocess_export_canvas_mode == "custom"
    assert reopened.preprocess_export_canvas_width == 1800
    assert reopened.preprocess_export_canvas_height == 2400
    assert reopened.preprocess_export_margin_top == 30
    assert reopened.preprocess_export_margin_bottom == 40
    assert reopened.preprocess_export_margin_left == 50
    assert reopened.preprocess_export_margin_right == 60
    assert reopened.preprocess_export_align_x == "right"
    assert reopened.preprocess_export_align_y == "bottom"


def test_manual_perspective_quad_roundtrip(tmp_path: Path) -> None:
    page = tmp_path / "0004.tif"
    Image.new("RGB", (400, 600), "white").save(page)
    quad = (10.0, 20.0, 390.0, 25.0, 380.0, 580.0, 15.0, 575.0)

    save_manual_perspective_quad(tmp_path, page, quad)
    assert load_manual_perspective_quad(tmp_path, page) == quad

    clear_manual_perspective_quad(tmp_path, page)
    assert load_manual_perspective_quad(tmp_path, page) is None


def test_promote_processed_pages_supports_incremental_selected_ranges(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    pages = []
    original_values = (40, 80, 120)
    for index, value in enumerate(original_values, start=1):
        page = root / f"{index:04d}.tif"
        Image.new("L", (40, 60), value).save(page)
        pages.append(page)

    output = image_preprocessing.processed_output_root(root)
    for index, value in enumerate((180, 220), start=1):
        Image.new("L", (32, 48), value).save(output / f"{index:04d}.tif")

    # Promote only body pages 1-2. Page 3 represents an appendix/table page and
    # must remain untouched even though the project contains it.
    backup, promoted = promote_processed_pages(root, pages[:2])

    assert backup == root / "__before__"
    assert len(promoted) == 2
    assert not (backup / "0003.tif").exists()
    with Image.open(root / "0003.tif") as opened:
        assert opened.size == (40, 60)
        assert opened.getpixel((0, 0)) == 120

    for index, original_value in enumerate((40, 80), start=1):
        with Image.open(backup / f"{index:04d}.tif") as opened:
            assert opened.size == (40, 60)
            assert opened.getpixel((0, 0)) == original_value
    for index, processed_value in enumerate((180, 220), start=1):
        with Image.open(root / f"{index:04d}.tif") as opened:
            assert opened.size == (32, 48)
            assert opened.getpixel((0, 0)) == processed_value

    # A later, different page range may be promoted into the same __before__
    # directory without altering the originals already stored there.
    Image.new("L", (34, 50), 240).save(output / "0003.tif")
    promote_processed_pages(root, [root / "0003.tif"])

    with Image.open(backup / "0001.tif") as opened:
        assert opened.getpixel((0, 0)) == 40
    with Image.open(backup / "0003.tif") as opened:
        assert opened.size == (40, 60)
        assert opened.getpixel((0, 0)) == 120
    with Image.open(root / "0003.tif") as opened:
        assert opened.size == (34, 50)
        assert opened.getpixel((0, 0)) == 240

    # Processed exports remain as provenance/reproducibility output.
    assert (output / "0001.tif").is_file()
    assert (output / "0002.tif").is_file()
    assert (output / "0003.tif").is_file()


def test_promote_processed_pages_requires_only_selected_exports_and_never_overwrites_page_backup(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    pages = []
    for index in (1, 2):
        page = root / f"{index:04d}.png"
        Image.new("RGB", (30, 40), "white").save(page)
        pages.append(page)

    output = image_preprocessing.processed_output_root(root)
    Image.new("RGB", (28, 38), "white").save(output / "0001.png")

    # Requiring both pages still fails because page 2 is missing.
    try:
        promote_processed_pages(root, pages)
    except RuntimeError as exc:
        assert "所选范围" in str(exc)
        assert "0002.png" in str(exc)
    else:
        raise AssertionError("incomplete selected range must not be promoted")

    assert all(page.is_file() for page in pages)
    assert not (root / "__before__").exists()

    # But selecting page 1 alone is valid; page 2 is not forced through this
    # preprocessing path.
    promote_processed_pages(root, [pages[0]])
    assert (root / "__before__" / "0001.png").is_file()
    assert (root / "0002.png").is_file()
    assert not (root / "__before__" / "0002.png").exists()

    # The immutable first-generation backup for a page is never overwritten.
    try:
        promote_processed_pages(root, [root / "0001.png"])
    except RuntimeError as exc:
        assert "__before__" in str(exc)
        assert "0001.png" in str(exc)
    else:
        raise AssertionError("existing page backup must never be overwritten")


def test_main_workspace_exposes_and_locks_preprocess_mode() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/picture_capture/app.py").read_text(encoding="utf-8")

    assert '"图片预处理（前置）"' in source
    assert 'text="进入预处理模式"' in source
    assert 'text="自动纠偏"' in source
    assert 'text="安全边界："' in source
    assert '"自动几何（推荐）"' in source
    assert '"UVDoc展平（Paddle高级）"' in source
    assert 'text="统一最终页面"' in source
    assert 'text="页边空(px)：" ' .strip() in source
    assert '"本批最大裁剪尺寸"' in source
    assert '"自定义尺寸"' in source
    assert '"左对齐", "居中", "右对齐"' in source
    assert "preprocess_export_margin_top_var" in source
    assert "preprocess_export_margin_bottom_var" in source
    assert "preprocess_export_margin_left_var" in source
    assert "preprocess_export_margin_right_var" in source
    assert '"顶端对齐", "居中", "底部对齐"' in source
    assert "export_diagnostic_json(" in source
    assert "export_summary_csv(" in source
    assert "allow_page_navigation: bool = False" in source
    assert source.count("allow_page_navigation=True") >= 4
    assert source.count(
        'and not getattr(self, "_batch_allow_page_navigation", False)'
    ) >= 2
    assert 'text="手动四角"' in source
    assert 'text="重置四角"' in source
    assert 'text="px"' in source
    assert '"分析当前页"' not in source
    assert '"分析所选范围"' in source
    assert '("诊断信息", self.show_preprocess_diagnostics)' in source
    assert 'text="导出检查小图"' in source
    assert 'text="导出预处理图片"' in source
    assert 'text="所选设为工作图片"' in source
    assert 'textvariable=self.preprocess_status_var' not in source
    assert 'section_keys = ("normal", "aux", "ocr", "actions", "postproduction")' in source
    assert '("review_window", "词条校对")' in source
    assert '("_settings_dialog", "设置中心")' in source
    assert '("_project_profile_wizard", "项目Profile")' in source
    assert "self.project_footer_buttons.append(button)" in source
    assert 'if self._preprocess_mode_active():\n            self.status_var.set("预处理模式中：SECTION 编辑已锁定。")' in source
    assert "if self._preprocess_mode_active():" in source
    assert "self._redraw_preprocess_preview(size)" in source
    assert "普通编辑已锁定" in source



def test_global_deskew_prefers_reliable_physical_header_rule(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    polygons = [
        _tilted_box(120, 180 + row * 44, 330, 24, -0.80)
        for row in range(22)
    ]

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: polygons,
    )
    monkeypatch.setattr(
        image_preprocessing,
        "horizontal_rule_metrics",
        lambda *_args, **_kwargs: (30, -0.26, 0.8, 120.0),
    )

    analysis = analyze_preprocess_page(
        image,
        AppSettings(),
        geometry_mode="deskew",
    )

    assert analysis.deskew_anchor_source == "header_rule"
    assert analysis.source_header_rule_point_count == 30
    assert abs(analysis.source_header_rule_angle_deg + 0.26) < 1e-6
    assert abs(analysis.ocr_correction_angle_deg + 0.80) <= 0.05
    assert abs(analysis.applied_angle_deg + 0.26) < 1e-6
    assert "header_rule_deskew" in analysis.method



def test_pixel_row_geometry_can_accept_safe_candidate_when_ocr_tail_is_biased(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    warped = _two_column_angle_field(lambda t: 0.45 - 0.90 * t)

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: warped,
    )
    monkeypatch.setattr(
        image_preprocessing,
        "analyze_text_line_geometry",
        lambda *_args, **_kwargs: image_preprocessing.TextLineGeometryAnalysis(
            row_count=40,
            recommendation="uvdoc_review",
            confidence=0.9,
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "estimate_orthogonal_warp",
        lambda *_args, **_kwargs: image_preprocessing.OrthogonalWarpEstimate(
            y_knots=(180.0, 1092.0),
            angle_knots_deg=(0.45, -0.45),
            reference_x=500.0,
            row_count=40,
            valid_column_count=2,
            pixel_angle_sample_count=18,
            pixel_angle_used_count=18,
            pixel_angle_confidence=0.30,
            max_row_angle_deg=0.45,
            row_angle_span_deg=0.90,
            max_vertical_shift_px=4.0,
            max_scale_deviation=0.01,
            confidence=0.95,
            active=True,
        ),
    )
    monkeypatch.setattr(
        image_preprocessing,
        "apply_orthogonal_warp_image",
        lambda source, *_args, **_kwargs: source.copy(),
    )

    pixel_calls = 0

    def fake_pixel_rows(*_args, **_kwargs):
        nonlocal pixel_calls
        pixel_calls += 1
        if pixel_calls == 1:
            return type(
                "PixelAudit",
                (),
                {
                    "sample_count": 24,
                    "valid_column_count": 2,
                    "p90_shift_px": 5.0,
                    "worst_shift_px": 6.0,
                    "passed": False,
                },
            )()
        return type(
            "PixelAudit",
            (),
            {
                "sample_count": 24,
                "valid_column_count": 2,
                "p90_shift_px": 1.0,
                "worst_shift_px": 1.5,
                "passed": True,
            },
        )()

    monkeypatch.setattr(
        image_preprocessing,
        "audit_pixel_row_profiles",
        fake_pixel_rows,
    )

    analysis = analyze_preprocess_page(
        image,
        AppSettings(layout_columns_policy="fixed", columns=2),
        geometry_mode="auto",
    )

    assert analysis.orthogonal_applied is True
    assert analysis.geometry_mode == "orthogonal"
    assert analysis.orthogonal_pixel_row_verdict == "passed"
    assert analysis.orthogonal_before_pixel_row_p90_px == 5.0
    assert analysis.orthogonal_after_pixel_row_p90_px == 1.0



def test_geometry_corrected_image_replays_all_saved_orthogonal_steps(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (800, 1000), "white")
    calls: list[tuple[float, float]] = []

    monkeypatch.setattr(
        image_preprocessing,
        "deskew_image",
        lambda source, _angle: source.copy(),
    )

    def fake_apply(source, estimate, *, row_gain, separator_gain):
        calls.append((float(row_gain), float(estimate.reference_x)))
        return source.copy()

    monkeypatch.setattr(
        image_preprocessing,
        "apply_orthogonal_warp_image",
        fake_apply,
    )

    analysis = image_preprocessing.PreprocessAnalysis(
        source_width=800,
        source_height=1000,
        correction_angle_deg=0.0,
        applied_angle_deg=0.0,
        crop_box=(0, 0, 800, 1000),
        raw_content_box=(0, 0, 800, 1000),
        text_box=None,
        source_boxes=20,
        angle_samples=20,
        angle_mad_deg=0.1,
        retained_ratio=1.0,
        confidence=1.0,
        status="ok",
        method="test",
        orthogonal_applied=True,
        orthogonal_passes=2,
        orthogonal_steps=(
            {
                "row_gain": 1.0,
                "reference_x": 390.0,
                "y_knots": [100.0, 900.0],
                "angle_knots_deg": [0.3, -0.3],
                "x_knots": [100.0, 700.0],
                "row_grid_rows": 2,
                "row_grid_cols": 2,
                "row_angle_grid_deg": [0.3, 0.3, -0.3, -0.3],
                "row_displacement_grid_px": [0.0, 3.0, 0.0, -3.0],
                "separator_y_knots": [],
                "separator_shift_knots_px": [],
            },
            {
                "row_gain": 0.7,
                "reference_x": 405.0,
                "y_knots": [100.0, 900.0],
                "angle_knots_deg": [0.1, -0.1],
                "x_knots": [100.0, 700.0],
                "row_grid_rows": 2,
                "row_grid_cols": 2,
                "row_angle_grid_deg": [0.1, 0.1, -0.1, -0.1],
                "row_displacement_grid_px": [0.0, 1.0, 0.0, -1.0],
                "separator_y_knots": [],
                "separator_shift_knots_px": [],
            },
        ),
    )

    output = image_preprocessing.geometry_corrected_image(image, analysis)

    assert output.size == image.size
    assert calls == [(1.0, 390.0), (0.7, 405.0)]


def test_auto_orthogonal_runs_second_residual_pass_after_improved_review(
    monkeypatch,
) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    polygons = _two_column_angle_field(lambda t: 0.35 - 0.70 * t)
    detect_calls = 0

    def fake_detect(_image, _settings):
        nonlocal detect_calls
        detect_calls += 1
        return polygons

    monkeypatch.setattr(image_preprocessing, "detect_text_polygons", fake_detect)
    monkeypatch.setattr(
        image_preprocessing,
        "analyze_text_line_geometry",
        lambda *_args, **_kwargs: image_preprocessing.TextLineGeometryAnalysis(
            row_count=40,
            recommendation="none",
            confidence=0.9,
        ),
    )

    estimate_calls = 0

    def fake_estimate(*_args, **_kwargs):
        nonlocal estimate_calls
        estimate_calls += 1
        return image_preprocessing.OrthogonalWarpEstimate(
            y_knots=(180.0, 1092.0),
            angle_knots_deg=(0.25, -0.25),
            x_knots=(180.0, 820.0),
            row_grid_rows=2,
            row_grid_cols=2,
            row_angle_grid_deg=(0.25, 0.25, -0.25, -0.25),
            row_displacement_grid_px=(0.0, 2.0, 0.0, -2.0),
            reference_x=500.0,
            row_count=40,
            valid_column_count=2,
            pixel_angle_sample_count=18,
            pixel_angle_used_count=18,
            pixel_angle_confidence=0.30,
            max_row_angle_deg=0.25,
            row_angle_span_deg=0.50,
            max_vertical_shift_px=2.0,
            max_scale_deviation=0.01,
            confidence=0.95,
            active=True,
        )

    monkeypatch.setattr(
        image_preprocessing,
        "estimate_orthogonal_warp",
        fake_estimate,
    )
    monkeypatch.setattr(
        image_preprocessing,
        "apply_orthogonal_warp_image",
        lambda source, *_args, **_kwargs: source.copy(),
    )

    class ScaleAudit:
        verdict = "same"

    monkeypatch.setattr(
        image_preprocessing,
        "audit_text_scale_stability",
        lambda *_args, **_kwargs: ScaleAudit(),
    )

    pixel_metrics = iter(
        [
            (5.0, 6.0),  # pass 1 baseline
            (2.0, 3.0),  # pass 1 accepted but improved_review
            (2.0, 3.0),  # pass 2 baseline
            (1.0, 1.5),  # pass 2 passed -> stop
        ]
    )

    def fake_pixel_audit(*_args, **_kwargs):
        p90, worst = next(pixel_metrics)
        return type(
            "PixelAudit",
            (),
            {
                "sample_count": 24,
                "valid_column_count": 2,
                "p90_shift_px": p90,
                "worst_shift_px": worst,
                "passed": p90 <= 1.5 and worst <= 2.5,
            },
        )()

    monkeypatch.setattr(
        image_preprocessing,
        "audit_pixel_row_profiles",
        fake_pixel_audit,
    )

    analysis = analyze_preprocess_page(
        image,
        AppSettings(layout_columns_policy="fixed", columns=2),
        geometry_mode="auto",
    )

    assert estimate_calls == 2
    assert analysis.orthogonal_applied is True
    assert analysis.orthogonal_passes == 2
    assert len(analysis.orthogonal_steps) == 2
    assert analysis.orthogonal_pixel_row_verdict == "passed"
    assert "orthogonal_residual_pass" in analysis.method
