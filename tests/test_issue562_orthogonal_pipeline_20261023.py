"""Issue #562: closed-loop orthogonal pipeline with live callbacks and safeguards."""
from __future__ import annotations

from dataclasses import fields
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from picture_capture.models import AppSettings
from picture_capture.preprocess import orthogonal_pipeline as pipeline
from picture_capture.preprocess.orthogonal_dewarp import PixelRowProfileAudit


def _unexpected(*args, **kwargs):
    raise AssertionError("skipped branch called an unrelated operation")


OPS = (
    "estimate_orthogonal_warp", "_orthogonal_safe_gain_cap",
    "transform_polygons_orthogonal", "audit_text_scale_stability",
    "audit_horizontal_alignment", "_absolute_horizontal_quality",
    "_choose_orthogonal_candidate", "apply_orthogonal_warp_image",
    "detect_text_polygons", "audit_pixel_row_profiles",
    "separator_track_points", "_separator_vertical_span",
    "horizontal_rule_metrics", "_orthogonal_step_payload",
)


def make_runtime(**changes):
    values = {f.name: ( _unexpected if f.name in OPS else 1.0)
              for f in fields(pipeline.OrthogonalRuntime)}
    values.update(
        ORTHOGONAL_MAX_AUTO_PASSES=3,
        ORTHOGONAL_AUTO_MIN_CONFIDENCE=.3,
        ORTHOGONAL_MIN_SAFE_GAIN=.1,
        ORTHOGONAL_AUTO_MIN_SCORE_IMPROVEMENT=.1,
        HORIZONTAL_ALIGNMENT_MAX_TAIL_DEG=1.5,
        PIXEL_ROW_PROFILE_P90_MAX_PX=1.5,
        PIXEL_ROW_PROFILE_WORST_MAX_PX=2.5,
        PIXEL_ROW_BOTTOM_TAIL_P90_MAX_PX=1.5,
        PIXEL_ROW_BOTTOM_TAIL_WORST_MAX_PX=2.5,
        ORTHOGONAL_TAIL_PROGRESS_RATIO=.7,
        ORTHOGONAL_TAIL_MAX_REGRESSION_PX=.5,
    )
    values.update(changes)
    return pipeline.OrthogonalRuntime(**values)


@pytest.fixture
def page():
    return Image.new("RGB", (40, 60), (15, 25, 35))


@pytest.fixture
def polygons():
    return [np.zeros((4, 2), dtype=float)]


def execute(page, polygons, runtime, *, mode="auto", writing="horizontal-tb",
            line_curve=False):
    warnings, method = ["prior"], ["deskew"]
    settings = AppSettings()
    settings.layout_writing_mode = writing
    out = pipeline.run_orthogonal_pipeline(
        page, polygons, settings, requested_geometry_mode=mode,
        actual_geometry_mode="deskew", geometry_strength=.2,
        advanced_redetected=False,
        line_geometry=SimpleNamespace(separator_curve_reliable=line_curve),
        warnings=warnings, method_parts=method, runtime=runtime)
    return out, warnings, method


def estimate(**changes):
    values=dict(
        active=True, row_count=8, valid_column_count=1,
        separator_point_count=0, horizontal_rule_point_count=0,
        horizontal_rule_y=0., horizontal_rule_angle_deg=0.,
        horizontal_rule_residual_span_px=0.,
        pixel_angle_sample_count=0, pixel_angle_used_count=0,
        pixel_angle_confidence=0., confidence=1., column_spread_deg=0.,
        max_row_angle_deg=1., row_angle_span_deg=1.,
        max_horizontal_shift_px=1., max_vertical_shift_px=2.,
        max_scale_deviation=.01, reference_x=20., y_knots=(0., 60.),
        angle_knots_deg=(.0, .1), x_knots=(0., 40.),
        row_grid_rows=2, row_grid_cols=2,
        row_angle_grid_deg=(0.,)*4,
        row_displacement_grid_px=(0.,)*4,
        separator_y_knots=(), separator_shift_knots_px=(),
    )
    values.update(changes)
    return SimpleNamespace(**values)


def pixel_rows(p90=5., worst=6., tail=5.):
    return PixelRowProfileAudit(
        sample_count=24, valid_column_count=1, p90_shift_px=p90,
        worst_shift_px=worst, bottom_tail_sample_count=4,
        bottom_tail_valid_column_count=1,
        bottom_tail_p90_shift_px=tail, bottom_tail_worst_shift_px=tail,
    )


def test_leaf_first_import_does_not_load_facade_gui_or_paddle():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.preprocess.orthogonal_pipeline import OrthogonalRuntime, OrthogonalRunResult
assert 'picture_capture.preprocess.pipeline' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_runtime_is_explicit_and_result_contains_historical_measurements():
    assert len(fields(pipeline.OrthogonalRuntime)) == 30
    names = {f.name for f in fields(pipeline.OrthogonalRunResult)}
    assert "orthogonal_passes" in names
    assert "orthogonal_before_bottom_tail_p90_px" in names
    assert "orthogonal_initial_pixel_row_available" in names
    assert "retained_pixels" in names and "working" in names
    assert len(names) == 65


@pytest.mark.parametrize("mode,writing,boxes", [
    ("deskew", "horizontal-tb", True),
    ("uvdoc", "horizontal-tb", True),
    ("perspective", "horizontal-tb", True),
    ("auto", "vertical-rl", True),
    ("auto", "horizontal-tb", False),
])
def test_nonautomatic_or_vertical_or_unboxed_skips_every_callback(
    page, polygons, mode, writing, boxes
):
    original = polygons if boxes else []
    out, warnings, method = execute(
        page, original, make_runtime(), mode=mode, writing=writing)
    assert out.working is page and out.working_polygons is original
    assert not out.orthogonal_applied and out.orthogonal_passes == 0
    assert out.orthogonal_steps == []
    assert out.orthogonal_alignment_verdict == "insufficient"
    assert out.retained_pixels.row_verdict == "insufficient"
    assert warnings == ["prior"] and method == ["deskew"]


def test_estimator_failure_keeps_pixels_and_precise_warning_order(page, polygons):
    calls = []
    def fail(img, boxes, settings):
        calls.append((img, boxes, settings))
        raise RuntimeError("no estimate")
    out, warnings, method = execute(
        page, polygons, make_runtime(estimate_orthogonal_warp=fail),
        line_curve=True)
    assert len(calls) == 1 and calls[0][:2] == (page, polygons)
    assert out.working is page and out.working_polygons is polygons
    assert warnings == ["prior", "正交网格几何估计不可用：no estimate",
        "检测到可靠非线性弯曲，但正交网格未能通过闭环验收；已保留前一步结果，可手动选择UVDoc复核。"]
    assert method == ["deskew"]


@pytest.mark.parametrize("cap,confidence,expected", [
    (.05, 1., True), (1., .1, False), (1., 1., False),
])
def test_inactive_low_confidence_and_gain_budget_gate(
    page, polygons, cap, confidence, expected
):
    current = estimate(active=cap == .05 or confidence == .1, confidence=confidence)
    rt = make_runtime(
        estimate_orthogonal_warp=lambda *_: current,
        _orthogonal_safe_gain_cap=lambda _: cap)
    out, warnings, method = execute(page, polygons, rt)
    assert out.orthogonal_passes == 0 and not out.orthogonal_applied
    assert out.orthogonal_row_count == 8
    assert out.orthogonal_safe_gain_cap == cap
    assert any("网格强度超过安全尺度预算" in x for x in warnings) is expected
    assert method == ["deskew"]


def accepted_runtime(page, *, quality_verdict="passed", reject_second=False):
    corrected = Image.new("RGB", page.size, (100, 110, 120))
    boxes = [np.full((4, 2), float(i)) for i in range(8)]
    estimate_calls, warp_calls, audit_images = [], [], []
    base = pixel_rows()
    candidate = pixel_rows(p90=1., worst=1.2, tail=1.)
    def estimator(img, source_boxes, settings):
        estimate_calls.append(img)
        return estimate()
    def warper(img, est, *, row_gain, separator_gain):
        warp_calls.append((img, row_gain, separator_gain))
        return corrected
    def auditor(img, source_boxes, settings):
        audit_images.append(img)
        return base if img is page else candidate
    def quality(audit):
        return (quality_verdict, 1.) if audit.kind == "after" else ("failed", 8.)
    def align(source_boxes, target_boxes, *, size, settings):
        return SimpleNamespace(kind="after" if source_boxes is boxes else "before",
                               after_worst_tail_p90_abs_deg=0.)
    runtime=make_runtime(
        estimate_orthogonal_warp=estimator, _orthogonal_safe_gain_cap=lambda e: 1.,
        _choose_orthogonal_candidate=lambda *a, **k: (
            1., boxes, "passed", 8., 1.),
        apply_orthogonal_warp_image=warper,
        detect_text_polygons=lambda *_: boxes,
        audit_horizontal_alignment=align,
        _absolute_horizontal_quality=quality,
        audit_pixel_row_profiles=auditor,
        _orthogonal_step_payload=lambda e,g: {"row_gain": g},
    )
    return runtime, corrected, boxes, estimate_calls, warp_calls, audit_images


def test_accepted_candidate_updates_pixels_steps_and_final_retained_audit(page, polygons):
    runtime, corrected, boxes, estimates, warps, audits = accepted_runtime(page)
    out, warnings, method = execute(page, polygons, runtime)
    assert out.working is corrected and out.working_polygons is not boxes
    assert len(out.working_polygons) == 8
    assert out.orthogonal_applied and out.orthogonal_passes == 1
    assert out.orthogonal_steps == [{"row_gain": 1.}]
    assert out.orthogonal_row_gain == 1.
    assert out.actual_geometry_mode == "orthogonal"
    assert out.advanced_redetected and out.geometry_strength == 2.
    assert estimates == [page] and warps == [(page, 1., 1.)]
    assert audits == [page, corrected, corrected]
    assert out.retained_pixels.after_row_p90_px == 1.
    assert out.retained_pixels.before_row_p90_px == 5.
    assert out.retained_pixels.row_verdict == "passed"
    assert warnings == ["prior"]
    assert method == ["deskew", "orthogonal_dewarp"]


def test_accepted_review_then_rejected_second_pass_preserves_retained_image(page, polygons):
    runtime, corrected, boxes, estimates, warps, audits = accepted_runtime(
        page, quality_verdict="improved_review")
    def estimator(img, source_boxes, settings):
        estimates.append(img)
        if img is corrected:
            raise RuntimeError("second pass rejected")
        return estimate()
    runtime = pipeline.OrthogonalRuntime(**{
        **{f.name: getattr(runtime, f.name) for f in fields(pipeline.OrthogonalRuntime)},
        "estimate_orthogonal_warp": estimator})
    out, warnings, methods = execute(page, polygons, runtime)
    assert out.working is corrected and len(out.working_polygons) == 8
    assert out.orthogonal_passes == 1 and out.orthogonal_applied
    assert estimates == [page, corrected]
    assert out.retained_pixels.row_verdict == "passed"
    assert out.retained_pixels.before_row_p90_px == 5.
    assert out.retained_pixels.after_row_p90_px == 1.
    assert method_count(methods, "orthogonal_dewarp") == 1
    assert warnings[-1] == "正交网格几何估计不可用：second pass rejected"


def method_count(methods, value):
    return methods.count(value)
