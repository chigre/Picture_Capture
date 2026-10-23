"""Source evidence boundaries and call-time composition before transforms."""
from __future__ import annotations

from dataclasses import asdict
import pickle
import subprocess
import sys

import numpy as np
from PIL import Image
import pytest

from picture_capture import image_preprocessing as api
from picture_capture.models import AppSettings
from picture_capture.preprocess.source_evidence import collect_source_geometry_evidence
from picture_capture.preprocess.text_line_geometry import TextLineGeometryAnalysis


@pytest.fixture
def collect():
    polygons = [np.array([[10, y], [70, y], [70, y + 8], [10, y + 8]], dtype=float)
                for y in (20, 40, 60, 80)]
    def run(*, source=None, settings=None, **overrides):
        kwargs = dict(
            requested_geometry_mode="deskew", auto_deskew=True,
            text_detector=lambda *a: polygons,
            line_analyzer=lambda *a: TextLineGeometryAnalysis(),
            line_geometry_factory=TextLineGeometryAnalysis,
            skew_estimator=lambda *a, **kw: (1.0, 8, .2),
            projection_estimator=lambda *a, **kw: .75,
            rule_metrics=lambda *a: (0, 0., 0., 0.),
            separator_curve_width_ratio=api.SEPARATOR_CURVE_WIDTH_RATIO_THRESHOLD,
            header_residual_min_px=api.HORIZONTAL_RULE_MAX_RESIDUAL_MIN_PX,
            header_residual_width_ratio=api.HORIZONTAL_RULE_MAX_RESIDUAL_WIDTH_RATIO,
            max_auto_deskew_deg=api.DEFAULT_MAX_AUTO_DESKEW_DEG,
            deskew_dead_zone_deg=api.DEFAULT_DESKEW_DEAD_ZONE_DEG,
        )
        kwargs.update(overrides)
        return collect_source_geometry_evidence(
            source if source is not None else Image.new("RGB", (1000, 1400), "white"),
            settings if settings is not None else AppSettings(), **kwargs,
        )
    return run


def fail(message):
    def operation(*args, **kwargs):
        raise RuntimeError(message)
    return operation


def test_leaf_first_import_has_no_facade_gui_or_paddle():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.preprocess.source_evidence import SourceGeometryEvidence
assert 'picture_capture.image_preprocessing' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_evidence_result_is_per_page_not_shared(collect):
    first, second = collect(), collect()
    first.warnings.append("first-only")
    first.method_parts.append("first-only")
    assert second.warnings == [] and "first-only" not in second.method_parts
    assert first.correction == first.applied == first.ocr_correction == 1.
    assert first.deskew_anchor_source == "ocr"


@pytest.mark.parametrize("detector", [fail("detector-error"), lambda *a: [], lambda *a: [0, 1, 2]])
def test_detection_failure_or_too_few_boxes_uses_projection(collect, detector):
    result = collect(text_detector=detector,
        skew_estimator=lambda *a, **kw: (0., 0, 0.))
    assert result.polygons == []
    assert result.method_parts == ["projection_fallback"]
    assert result.correction == result.applied == .75
    assert "版面结构检测不可用" in result.warnings[0]
    assert "倾斜角由投影法" in result.warnings[1]


def test_angle_fallback_failure_preserves_diagnostics(collect):
    result = collect(skew_estimator=lambda *a, **kw: (2., 3, .4),
                     projection_estimator=fail("projection-error"))
    assert result.ocr_correction == result.correction == result.applied == 0
    assert result.angle_samples == 3 and result.angle_mad == .4
    assert result.method_parts == ["paddle_layout_roi", "line_geometry", "projection_angle"]
    assert result.warnings == ["倾斜角回退估计失败：projection-error"]


def test_line_analysis_failure_does_not_cancel_skew(collect):
    result = collect(line_analyzer=fail("line-error"))
    assert result.correction == 1.
    assert result.line_geometry == TextLineGeometryAnalysis()
    assert result.method_parts == ["paddle_layout_roi"]
    assert result.warnings == ["文本行几何分析不可用：line-error"]


@pytest.mark.parametrize("angle,enabled,expected,warnings", [
    (.049, True, 0., False), (.05, True, .05, False),
    (-.05, True, -.05, False), (2., True, 2., False),
    (-2., True, -2., False), (2.001, True, 0., True),
    (-2.001, True, 0., True), (1., False, 0., False), (3., False, 0., False),
])
def test_deskew_dead_zone_limit_and_disable(collect, angle, enabled, expected, warnings):
    result = collect(skew_estimator=lambda *a, **kw: (angle, 8, 0.),
        auto_deskew=enabled, deskew_dead_zone_deg=.05, max_auto_deskew_deg=2.)
    assert result.correction == angle and result.applied == expected
    assert bool(result.warnings) == warnings


@pytest.mark.parametrize("count,angle,residual,anchored", [
    (7, 2., 3., True), (6, 1., 1., False), (7, 2.001, 1., False),
    (7, -2.001, 1., False), (7, 1., 3.001, False), (7, -2., 0., True),
])
def test_header_anchor_reliability_inclusive_boundaries(collect, count, angle, residual, anchored):
    result = collect(rule_metrics=lambda *a: (count, angle, residual, 70.),
        header_residual_min_px=3., header_residual_width_ratio=.001,
        max_auto_deskew_deg=2.)
    assert (result.deskew_anchor_source == "header_rule") is anchored
    assert result.source_header_rule_point_count == count
    assert result.source_header_rule_angle_deg == angle
    assert result.source_header_rule_residual_px == residual
    assert ("header_rule_deskew" in result.method_parts) is anchored
    assert result.correction == (angle if anchored else 1.)


def test_header_residual_uses_page_width_scaled_limit(collect):
    result = collect(source=Image.new("RGB", (4000, 20)),
        rule_metrics=lambda *a: (7, 1.5, 5., 0.),
        header_residual_min_px=3., header_residual_width_ratio=.0015)
    assert result.deskew_anchor_source == "header_rule"
    assert any("正文OCR平均倾角" in w for w in result.warnings)


@pytest.mark.parametrize("mode", ["vertical-rl", "vertical-lr"])
def test_vertical_pages_skip_header_metrics(collect, mode):
    result = collect(settings=AppSettings(layout_writing_mode=mode),
                     rule_metrics=fail("must not run"))
    assert result.deskew_anchor_source == "ocr" and result.warnings == []


def test_header_failure_warns_and_keeps_ocr(collect):
    result = collect(rule_metrics=fail("rule-error"))
    assert result.correction == 1.
    assert result.warnings == ["页眉实体横线全局锚定不可用：rule-error"]


@pytest.mark.parametrize("mode,warns", [("auto", False), ("uvdoc", False), ("deskew", True)])
def test_nonlinear_recommendation_respects_requested_mode(collect, mode, warns):
    result = collect(requested_geometry_mode=mode,
        line_analyzer=lambda *a: TextLineGeometryAnalysis(recommendation="uvdoc_review"))
    assert any("可靠的平滑非线性弯曲" in w for w in result.warnings) is warns


@pytest.mark.parametrize("found,residual,straight", [(True, 2.9, True), (True, 3., False), (False, 0., False)])
def test_manual_review_distinguishes_straight_physical_separator(collect, found, residual, straight):
    result = collect(line_analyzer=lambda *a: TextLineGeometryAnalysis(
        recommendation="manual_review", separator_found=found, separator_residual_px=residual))
    assert any("长直分隔线保持笔直" in w for w in result.warnings) is straight
    assert any("证据不足" in w for w in result.warnings) is (not straight)


@pytest.mark.parametrize("residual,reliable,warns", [(4.49, False, False), (4.5, False, True), (8., True, False)])
def test_unreliable_curve_warning_threshold(collect, residual, reliable, warns):
    result = collect(line_analyzer=lambda *a: TextLineGeometryAnalysis(
        separator_found=True, separator_residual_px=residual, separator_curve_reliable=reliable))
    assert any("不作为 UVDoc" in w for w in result.warnings) is warns


def test_callback_sequence_and_input_identity(collect):
    source = Image.new("RGB", (40, 60))
    settings = AppSettings()
    polygons = [np.zeros((4, 2)) for _ in range(4)]
    calls = []
    def detector(image, options):
        assert image is source and options is settings
        calls.append("detect")
        return polygons
    def lines(image, boxes, options):
        assert image is source and boxes is polygons and options is settings
        calls.append("lines")
        return TextLineGeometryAnalysis()
    def skew(boxes, *, writing_mode):
        assert boxes is polygons and writing_mode == settings.layout_writing_mode
        calls.append("skew")
        return (1., 3, .2)
    def projection(image, options, *, writing_mode):
        assert image is source and options is settings
        calls.append("projection")
        return .75
    def header(*args):
        calls.append("header")
        return (7, .5, 0., 10.)
    result = collect(source=source, settings=settings, text_detector=detector,
        line_analyzer=lines, skew_estimator=skew, projection_estimator=projection, rule_metrics=header)
    assert calls == ["detect", "lines", "skew", "projection", "header"]
    assert result.polygons is polygons and result.ocr_correction == .75
    assert result.correction == result.applied == .5


def test_public_analysis_composes_live_evidence_operations(monkeypatch, tmp_path):
    source = Image.new("RGB", (40, 60), "white")
    source.paste("black", (10, 15, 30, 45))
    calls = []
    monkeypatch.setattr(api, "detect_text_polygons", lambda *a: [])
    monkeypatch.setattr(api, "estimate_skew_from_polygons", lambda *a, **kw: (0., 0, 0.))
    monkeypatch.setattr(api, "_projection_skew_fallback", lambda *a, **kw: calls.append("projection") or .75)
    result = api.analyze_preprocess_page(source, AppSettings(), geometry_mode="deskew")
    assert calls == ["projection"]
    assert result.correction_angle_deg == result.applied_angle_deg == .75
    destination = api.save_analysis(tmp_path, tmp_path / "scan.png", result)
    reopened = api.load_analysis(tmp_path, tmp_path / "scan.png")
    assert destination.exists() and asdict(reopened) == asdict(result)
    assert pickle.loads(pickle.dumps(result)) == result
