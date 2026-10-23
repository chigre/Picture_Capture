"""Final retained bounds, diagnostic evidence and public-model compatibility."""
from __future__ import annotations

from dataclasses import asdict
import pickle
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from picture_capture.preprocess import pipeline as api
from picture_capture.models import AppSettings
from picture_capture.preprocess.finalization import finalize_preprocess_page


def fail(message):
    def operation(*args, **kwargs):
        raise RuntimeError(message)
    return operation


@pytest.fixture
def finalize():
    boxes = [np.array([[10, y], [90, y], [90, y + 8], [10, y + 8]], dtype=float)
             for y in range(30, 150, 15)]
    audit = SimpleNamespace(
        row_count=20, valid_column_count=2, edge_pair_count=40,
        after_top_edge_p90_abs_deg=.12, after_bottom_edge_p90_abs_deg=.13,
        after_edge_pair_delta_p90_deg=.02, after_worst_edge_deg=.14,
        after_worst_region_deg=.15, after_worst_tail_p90_abs_deg=.16,
        after_column_top_tail_p90_abs_deg=(.11, .12),
        after_column_bottom_tail_p90_abs_deg=(.13, .14),
        after_trend_deg=-.1, after_column_trends_deg=(.2, -.3),
    )
    def run(**overrides):
        kwargs = dict(
            source_size=(100, 200), polygons=boxes, working_polygons=boxes,
            actual_geometry_mode="deskew", advanced_redetected=False,
            safety_margin_px=0, angle_samples=16, angle_mad=0., correction=0.,
            warnings=[], method_parts=["paddle_layout_roi"],
            text_detector=fail("unexpected detection"),
            horizontal_auditor=lambda *a, **kw: audit,
            quality_evaluator=lambda a: ("passed", .25),
            layout_bounds=lambda *a: ((10, 20, 90, 180), SimpleNamespace(source_boxes=40)),
            projection_bounds=lambda *a: (20, 30, 80, 170),
            box_expander=api._expand_box_px, text_bounds=api._rotated_text_box,
        )
        kwargs.update(overrides)
        image = kwargs.pop("working", Image.new("RGB", (100, 200), "white"))
        settings = kwargs.pop("settings", AppSettings())
        return finalize_preprocess_page(image, settings, **kwargs)
    run.boxes = boxes
    run.audit = audit
    return run


def test_leaf_first_import_does_not_initialize_facade_gui_or_paddle():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.preprocess.finalization import FinalPreprocessResult
assert 'picture_capture.preprocess.pipeline' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_maps_final_audit_and_crops_in_source_coordinates(finalize):
    result = finalize()
    assert result.crop_box == result.raw_content_box == (10, 20, 90, 180)
    assert result.text_box == (10, 30, 91, 144)
    assert result.retained_ratio == .64 and result.evidence_boxes == 40
    assert result.confidence == 1. and result.status == "normal"
    assert result.final_alignment_row_count == 20
    assert result.final_alignment_valid_column_count == 2
    assert result.final_alignment_edge_pair_count == 40
    assert result.final_alignment_top_edge_p90_abs_deg == .12
    assert result.final_alignment_bottom_edge_p90_abs_deg == .13
    assert result.final_alignment_edge_pair_delta_p90_deg == .02
    assert result.final_alignment_worst_edge_deg == .14
    assert result.final_alignment_worst_region_deg == .15
    assert result.final_alignment_worst_tail_p90_abs_deg == .16
    assert result.final_alignment_column_top_tail_p90_abs_deg == (.11, .12)
    assert result.final_alignment_column_bottom_tail_p90_abs_deg == (.13, .14)
    assert result.final_alignment_trend_deg == -.1
    assert result.final_alignment_worst_column_trend_deg == .3
    assert result.final_alignment_verdict == "passed" and result.final_alignment_quality_score == .25


@pytest.mark.parametrize("mode,already_redetected,original_present,detects", [
    ("deskew", False, True, False), ("orthogonal", False, True, False),
    ("manual_perspective", False, True, True), ("perspective", False, True, True),
    ("uvdoc", False, True, True), ("uvdoc", True, True, False),
    ("perspective", False, False, False),
])
def test_redetection_gate_and_current_polygon_identity(finalize, mode, already_redetected, original_present, detects):
    redetected = [np.zeros((4, 2)) for _ in range(12)]
    original = finalize.boxes if original_present else []
    calls = []
    methods = ["paddle_layout_roi"]
    def detector(*args):
        calls.append("detect")
        return redetected
    def layout(boxes, width, height, settings):
        assert boxes is (redetected if detects else finalize.boxes)
        assert (width, height) == (100, 200)
        return (10, 20, 90, 180), SimpleNamespace(source_boxes=0)
    result = finalize(polygons=original, actual_geometry_mode=mode,
        advanced_redetected=already_redetected, text_detector=detector,
        layout_bounds=layout, method_parts=methods)
    assert calls == (["detect"] if detects else [])
    assert ("redetect" in methods) is detects
    assert result.evidence_boxes == (12 if detects else 8)


@pytest.mark.parametrize("detector", [lambda *a: [0, 1, 2], fail("detector-error")])
def test_failed_redetection_keeps_transformed_boxes_and_warns(finalize, detector):
    warnings = []
    calls = []
    def layout(boxes, *args):
        assert boxes is finalize.boxes
        calls.append("layout")
        return (10, 20, 90, 180), SimpleNamespace(source_boxes=40)
    result = finalize(actual_geometry_mode="perspective", text_detector=detector,
        layout_bounds=layout, warnings=warnings)
    assert calls == ["layout"] and result.crop_box == (10, 20, 90, 180)
    assert len(warnings) == 1 and "沿用变换后的原检测框" in warnings[0]
    assert result.status == "review"


@pytest.mark.parametrize("mode", ["vertical-rl", "vertical-lr"])
def test_vertical_layout_skips_horizontal_audit(finalize, mode):
    result = finalize(settings=AppSettings(layout_writing_mode=mode),
                      horizontal_auditor=fail("must not run"))
    assert result.final_alignment_verdict == "insufficient"
    assert result.final_alignment_row_count == 0 and result.status == "normal"


def test_failed_alignment_warning_keeps_tail_and_column_diagnostics(finalize):
    warnings = []
    result = finalize(warnings=warnings, quality_evaluator=lambda a: ("failed", 9.))
    assert warnings == ["成品双边缘水平验收未通过：上缘P90 0.12°，下缘P90 0.13°，上下缘差P90 0.02°，最差区域 0.15°，页首/页尾最差P90 0.16°，最差栏趋势 0.30°。"]
    assert result.status == "review" and result.final_alignment_quality_score == 9.


@pytest.mark.parametrize("mode,warns", [("deskew", False), ("uvdoc", True)])
@pytest.mark.parametrize("failure", ["raise", "partial", "insufficient"])
def test_uvdoc_insufficient_or_unavailable_warning_policy(finalize, mode, warns, failure):
    warnings = []
    audit = finalize.audit
    if failure == "raise":
        auditor = fail("audit-error")
    elif failure == "partial":
        auditor = lambda *a, **kw: SimpleNamespace(row_count=22)
    else:
        auditor = lambda *a, **kw: audit
    result = finalize(actual_geometry_mode=mode, advanced_redetected=True, warnings=warnings,
        horizontal_auditor=auditor, quality_evaluator=lambda a: ("insufficient", 0.))
    assert bool(warnings) is warns
    assert result.final_alignment_verdict == "insufficient"
    if failure == "partial":
        assert result.final_alignment_row_count == 22
        assert result.final_alignment_valid_column_count == 0


def test_older_audits_without_optional_tail_fields_keep_defaults(finalize):
    audit = SimpleNamespace(**{key: value for key, value in vars(finalize.audit).items()
                              if "tail" not in key})
    result = finalize(horizontal_auditor=lambda *a, **kw: audit)
    assert result.final_alignment_worst_tail_p90_abs_deg == 0.
    assert result.final_alignment_column_top_tail_p90_abs_deg == ()
    assert result.final_alignment_column_bottom_tail_p90_abs_deg == ()
    assert result.final_alignment_verdict == "passed"


def test_structure_failure_falls_back_to_projection_in_warning_order(finalize):
    warnings, methods = ["earlier-warning"], ["paddle_layout_roi"]
    result = finalize(warnings=warnings, method_parts=methods,
        layout_bounds=fail("layout-error"), safety_margin_px=10)
    assert result.raw_content_box == (20, 30, 80, 170)
    assert result.crop_box == (10, 20, 90, 180)
    assert methods == ["projection_fallback", "paddle_layout_roi"]
    assert warnings == ["earlier-warning", "纠正后结构裁边失败，已使用投影回退：layout-error"]
    assert result.evidence_boxes == 8 and result.confidence == pytest.approx(.11)


def test_no_boxes_projection_is_single_fallback_and_has_no_text_box(finalize):
    methods = ["projection_fallback"]
    result = finalize(polygons=[], working_polygons=[], method_parts=methods,
        layout_bounds=fail("must not run"), horizontal_auditor=fail("must not run"))
    assert methods == ["projection_fallback"]
    assert result.text_box is None and result.evidence_boxes == 0 and result.confidence == 0
    assert result.status == "review"


def test_projection_error_propagates_instead_of_inventing_crop(finalize):
    with pytest.raises(RuntimeError, match="projection-error"):
        finalize(polygons=[], working_polygons=[], projection_bounds=fail("projection-error"))


@pytest.mark.parametrize("samples,mad,fallback,expected", [
    (8, 0., False, 1.), (8, .6, False, .6), (8, 1.5, False, .25),
    (0, 0., False, .45), (0, 0., True, .2475), (8, 0., True, .55),
])
def test_confidence_penalties_are_preserved(finalize, samples, mad, fallback, expected):
    result = finalize(angle_samples=samples, angle_mad=mad,
        method_parts=["projection_fallback"] if fallback else ["paddle_layout_roi"])
    assert result.confidence == pytest.approx(expected)


@pytest.mark.parametrize("count,expected", [(17, "review"), (18, "normal")])
def test_confidence_review_threshold_is_strict(finalize, count, expected):
    result = finalize(layout_bounds=lambda *a: ((10, 20, 90, 180), SimpleNamespace(source_boxes=count)))
    assert result.status == expected


@pytest.mark.parametrize("box,warning", [((0, 0, 40, 200), "裁剪幅度较大"),
    ((0, 0, 100, 200), "几乎未裁边"), ((0, 0, 45, 200), None)])
def test_retained_area_review_limits(finalize, box, warning):
    warnings = []
    result = finalize(warnings=warnings,
        layout_bounds=lambda *a: (box, SimpleNamespace(source_boxes=40)))
    assert any(warning in w for w in warnings) if warning else warnings == []
    assert result.retained_ratio == box[2] / 100.


def test_final_warning_order_and_nonmutation_of_pixels(finalize):
    source = Image.new("RGB", (100, 200), (10, 20, 30))
    before = source.tobytes()
    warnings = ["earlier"]
    finalize(working=source, warnings=warnings, polygons=finalize.boxes[:4],
        angle_mad=.8, correction=4.,
        layout_bounds=lambda *a: ((0, 0, 40, 200), SimpleNamespace(source_boxes=40)))
    assert [w.split("（")[0] for w in warnings[1:]] == [
        "文本框倾斜角离散较大", "页面倾斜较大", "有效文本框仅 4 个，建议人工确认裁边。", "仅保留页面 40.0% 面积，裁剪幅度较大。"]
    assert source.tobytes() == before


def test_public_composition_uses_current_bounds_and_roundtrips(monkeypatch, tmp_path):
    source = Image.new("RGB", (100, 200), "white")
    source.paste("black", (10, 30, 90, 170))
    monkeypatch.setattr(api, "detect_text_polygons", lambda *a: [])
    monkeypatch.setattr(api, "_projection_skew_fallback", lambda *a, **kw: 0.)
    monkeypatch.setattr(api, "_projection_content_box", lambda *a: (20, 40, 80, 160))
    result = api.analyze_preprocess_page(source, AppSettings(), geometry_mode="deskew", safety_margin_px=5)
    assert result.raw_content_box == (20, 40, 80, 160) and result.crop_box == (15, 35, 85, 165)
    path = tmp_path / "scan.png"
    api.save_analysis(tmp_path, path, result)
    assert asdict(api.load_analysis(tmp_path, path)) == asdict(result)
    assert pickle.loads(pickle.dumps(result)) == result
