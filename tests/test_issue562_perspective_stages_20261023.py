"""Issue #562: manual and automatic projective stage ownership boundaries."""
from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace
import subprocess
import sys

import numpy as np
from PIL import Image
import pytest

from picture_capture.preprocess import perspective_stages as owner


QUAD = (1., 2., 31., 2., 31., 38., 1., 38.)


@pytest.fixture
def page():
    return Image.new("RGB", (40, 50), (20, 30, 40))


def fail(*args, **kwargs):
    raise AssertionError("unexpected callback")


def manual_estimate(rotated, size, *, strength=2.5):
    assert rotated == list(QUAD) and size == (40, 50)
    return SimpleNamespace(
        matrix=(1., 0., 0., 0., 1., 0., 0., 0., 1.),
        source_quad=QUAD, target_quad=QUAD, classification="manual",
        strength_px=strength, left_drift_px=2., right_drift_px=1.,
        common_drift_px=3., width_delta_px=4.,
        width_change_ratio=.02, scale_top=1.05, scale_bottom=.98,
        scale_delta_ratio=.07)


def run_manual(page, polygons=None, quad=QUAD, estimator=manual_estimate,
               warper=fail, transformer=fail, state=None, strength=0.1):
    state = state if state is not None else owner.PerspectiveState()
    polygons = [] if polygons is None else polygons
    warnings, methods, calls = ["older"], ["deskew"], []
    def rotate(x, y, w, h, angle):
        calls.append((x, y, w, h, angle))
        return x, y
    result = owner.apply_manual_perspective(
        page, polygons, quad, 40, 50, .3, SimpleNamespace(layout_writing_mode="horizontal-tb"),
        state, strength, methods, warnings, point_rotator=rotate,
        manual_estimator=estimator, polygon_transformer=transformer,
        distortion_auditor=fail, text_scale_auditor=fail, row_auditor=fail,
        homography_warper=warper)
    return result, state, warnings, methods, calls


def selection_for(candidate=None, entry=None, **changes):
    d=dict(selected_entry=entry, selected_candidate=candidate,
        selected_horizontal_strength=0., diagnostic_entry=None,
        diagnostic_candidate=None, diagnostic_horizontal_strength=0.,
        perspective_structural_applied=False, perspective_structural_safe=False,
        structural_auto_safe=False, horizontal_auto_safe=False,
        structural_candidate=None, structural_entry=None,
        line_supports_perspective=False, horizontal_total_candidate=None,
        horizontal_full=None, horizontal_row_audit=None, horizontal_strength=0.)
    d.update(changes)
    return SimpleNamespace(**d)


def run_selected(page, selection, *, mode="auto", state=None, warper=fail):
    state = state if state is not None else owner.PerspectiveState()
    original_polygons = [np.zeros((4, 2), dtype=float)]
    methods, warnings = ["deskew"], ["earlier"]
    result = owner.apply_selected_perspective(
        selection, page, original_polygons, "deskew", .4, state,
        requested_geometry_mode=mode,
        line_geometry=SimpleNamespace(separator_curve_reliable=False),
        method_parts=methods, warnings=warnings,
        homography_warper=warper,
        horizontal_scale_span_max=.2, vertical_scale_span_max=.2,
        area_scale_span_max=.2, anisotropy_p95_max=.2)
    return result, state, original_polygons, warnings, methods


def test_leaf_import_does_not_import_public_facade_gui_or_paddle():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.preprocess.perspective_stages import PerspectiveState
assert 'picture_capture.preprocess.pipeline' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_perspective_state_has_one_default_per_current_page():
    one, two = owner.PerspectiveState(), owner.PerspectiveState()
    assert len(fields(owner.PerspectiveState)) == 72
    assert one.perspective_matrix is None and one.perspective_scale_top == 1.0
    assert one.perspective_row_after_column_trends_deg == ()
    one.perspective_classification = "manual"
    assert two.perspective_classification == "none"


def test_no_manual_quad_preserves_identity_without_callback(page):
    polygons = [np.zeros((4, 2))]
    result, state, warnings, methods, calls = run_manual(
        page, polygons=polygons, quad=None)
    assert result.image is page and result.polygons is polygons
    assert result.geometry_mode == "deskew" and result.geometry_strength == .1
    assert calls == [] and warnings == ["older"] and methods == ["deskew"]
    assert state.perspective_matrix is None


def test_manual_source_quad_rotation_order_and_successful_pixel_transform(page):
    corrected = Image.new("RGB", page.size, (50, 60, 70))
    calls = []
    result, state, warnings, methods, rotated = run_manual(
        page, warper=lambda *args: (calls.append(args), corrected)[1])
    assert [(a, b) for a,b,*_ in rotated] == list(zip(QUAD[::2],QUAD[1::2]))
    assert all((w, h, angle) == (40, 50, .3) for _, _, w, h, angle in rotated)
    assert len(calls) == 1 and calls[0] == (page, state.perspective_matrix)
    assert result.image is corrected and result.polygons == []
    assert result.geometry_mode == "manual_perspective"
    assert result.geometry_strength == 2.5
    assert state.perspective_candidate_source == "manual"
    assert state.perspective_source_quad == QUAD
    assert warnings == ["older"] and methods == ["deskew", "manual_perspective"]


def test_manual_estimator_error_keeps_previous_pixels_and_warnings(page):
    def broken(*args):
        raise ValueError("invalid handles")
    result, state, warnings, methods, rotated = run_manual(
        page, estimator=broken)
    assert len(rotated) == 4 and result.image is page
    assert result.geometry_strength == .1 and state.perspective_matrix is None
    assert methods == ["deskew"]
    assert warnings == ["older", "手动四角透视纠正不可用：invalid handles"]


def test_manual_failure_after_diagnostic_assignments_preserves_partial_state(page):
    polygons = [np.zeros((4, 2))]
    def fail_poly(*args):
        raise ValueError("bad polygon")
    result, state, warnings, methods, _ = run_manual(
        page, polygons=polygons, transformer=fail_poly)
    assert result.image is page and result.polygons is polygons
    assert result.geometry_mode == "deskew" and result.geometry_strength == 2.5
    assert state.perspective_candidate_source == "manual"
    assert state.perspective_candidate_strength_px == 2.5
    assert state.perspective_row_alignment_verdict == "insufficient"
    assert warnings[-1] == "手动四角透视纠正不可用：bad polygon"
    assert methods == ["deskew"]


def test_no_selected_candidate_retains_previous_image(page):
    result, state, polygons, warnings, methods = run_selected(page, selection_for())
    assert result.image is page and result.polygons is polygons
    assert result.geometry_mode == "deskew" and result.geometry_strength == .4
    assert not state.perspective_auto_safe
    assert warnings == ["earlier"] and methods == ["deskew"]


@pytest.mark.parametrize("strength,applies", [(0.7499, False), (0.75, True), (0.751, True)])
def test_projective_apply_threshold_is_inclusive(page, strength, applies):
    candidate = SimpleNamespace(matrix=(1.,), strength_px=strength)
    updated = Image.new("RGB", page.size)
    calls = []
    selection = selection_for(candidate, {"polygons": ["corrected"]},
        structural_candidate=candidate, structural_auto_safe=True,
        perspective_structural_applied=True)
    result, state, polygons, warnings, methods = run_selected(
        page, selection,
        warper=lambda *args: (calls.append(args), updated)[1])
    assert state.perspective_auto_safe
    assert result.image is (updated if applies else page)
    assert result.polygons == (["corrected"] if applies else polygons)
    assert calls == ([(page, candidate.matrix)] if applies else [])
    assert ("perspective" in methods) is applies
    assert ("structural" in methods) is applies
    assert warnings == ["earlier"]


def test_explicit_unsafe_perspective_warns_after_transform(page):
    candidate = SimpleNamespace(matrix=(1.,), strength_px=.8)
    selection = selection_for(candidate, {"polygons": []},
        selected_horizontal_strength=.2)
    result, state, _, warnings, methods = run_selected(
        page, selection, mode="perspective",
        warper=lambda img, mat: img)
    assert result.geometry_mode == "perspective"
    assert result.geometry_strength == .8
    assert not state.perspective_auto_safe
    assert warnings[-1].startswith("已按用户显式选择执行投影矫正；该候选未通过自动安全门。")
    assert "来源=none" in warnings[-1]
    assert methods == ["deskew", "perspective", "horizontal_vp", "horizontal_vp_optimized"]


def test_candidate_without_apply_preserves_full_previous_methods(page):
    candidate = SimpleNamespace(matrix=(1.,), strength_px=.3)
    selection = selection_for(candidate, {"polygons": ["would-be"]},
        structural_candidate=candidate, structural_auto_safe=True,
        perspective_structural_applied=True)
    result, state, polygons, warnings, methods = run_selected(page, selection)
    assert result.image is page and result.polygons is polygons
    assert result.geometry_strength == .4
    assert state.perspective_auto_safe
    assert methods == ["deskew"] and warnings == ["earlier"]
