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
    export_diagnostic_json,
    export_summary_csv,
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


def test_auto_geometry_uses_line_geometry_only_for_review(monkeypatch) -> None:
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

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: polygons,
    )
    monkeypatch.setattr(
        image_preprocessing,
        "analyze_text_line_geometry",
        lambda *_args, **_kwargs: image_preprocessing.TextLineGeometryAnalysis(
            row_count=20,
            separator_found=True,
            separator_residual_px=9.0,
            separator_span_ratio=0.9,
            recommendation="uvdoc_review",
            confidence=0.9,
        ),
    )

    analysis = analyze_preprocess_page(
        image,
        AppSettings(),
        safety_margin_px=20,
        auto_deskew=True,
        geometry_mode="auto",
    )

    assert analysis.geometry_mode != "uvdoc"
    assert analysis.line_geometry_recommendation == "uvdoc_review"
    assert analysis.line_geometry_separator_residual_px == 9.0
    assert any("UVDoc" in warning for warning in analysis.warnings)


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


def test_0011_style_large_ocr_homography_is_blocked_without_separator(monkeypatch) -> None:
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
    assert any("局部尺度漂移" in warning for warning in analysis.warnings)


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

    summary = tmp_path / "preprocess_summary.csv"
    export_summary_csv([(page, analysis, output, canvas)], summary)
    text = summary.read_text(encoding="utf-8-sig")
    assert "line_geometry_recommendation" in text
    assert "separator_residual_px" in text
    assert "separator_drift_px" in text
    assert "perspective_scale_delta_ratio" in text
    assert "perspective_jacobian_horizontal_scale_span_ratio" in text
    assert "perspective_jacobian_vertical_scale_span_ratio" in text
    assert "perspective_text_scale_verdict" in text
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
        source_size_bytes=stat.st_size,
        source_mtime_ns=stat.st_mtime_ns,
    )

    save_analysis(tmp_path, page, analysis)
    loaded = load_analysis(tmp_path, page)

    assert loaded is not None
    assert loaded.crop_box == analysis.crop_box
    assert loaded.auto_deskew is True
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
    assert '"分析所选范围"' in source
    assert 'text="导出检查小图"' in source
    assert 'text="导出预处理图片"' in source
    assert 'section_keys = ("normal", "aux", "ocr", "actions", "postproduction")' in source
    assert '("review_window", "词条校对")' in source
    assert '("_settings_dialog", "设置中心")' in source
    assert '("_project_profile_wizard", "项目Profile")' in source
    assert "self.project_footer_buttons.append(button)" in source
    assert 'if self._preprocess_mode_active():\n            self.status_var.set("预处理模式中：SECTION 编辑已锁定。")' in source
    assert "if self._preprocess_mode_active():" in source
    assert "self._redraw_preprocess_preview(size)" in source
    assert "普通编辑已锁定" in source
