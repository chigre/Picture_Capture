"""Projective candidate gates, selection identity and live composition."""
from __future__ import annotations

from dataclasses import asdict
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from picture_capture.preprocess import pipeline as api
from picture_capture.models import AppSettings
from picture_capture.preprocess import projective_selection as owner
from picture_capture.preprocess.text_line_geometry import TextLineGeometryAnalysis


def fail(*args, **kwargs):
    raise RuntimeError("fixture-operation-failure")


@pytest.fixture
def select():
    def candidate(x, source):
        return SimpleNamespace(matrix=(1., 0., x, 0., 1., 0., 0., 0., 1.),
            strength_px=6., classification="keystone", candidate_source=source,
            horizontal_row_count=20, horizontal_vp_column_spread_deg=.1)
    structural = candidate(1., "structural")
    horizontal = candidate(2., "horizontal")
    combined = candidate(3., "combined")
    rows = SimpleNamespace(before_trend_deg=.5, before_column_trends_deg=(.4, -.3),
        before_worst_region_span_deg=.4, before_metric_deg=1., after_metric_deg=.2, verdict="improved")
    jacobian = SimpleNamespace(valid=True, horizontal_scale_span_ratio=.01,
        vertical_scale_span_ratio=.01, area_scale_span_ratio=.01, anisotropy_p95_ratio=.01)
    scale = SimpleNamespace(verdict="stable", anisotropy_p95_ratio=.01)
    polygons = [np.array([[10, y], [90, y], [90, y + 8], [10, y + 8]], float)
                for y in range(20, 140, 15)]
    def run(**overrides):
        kwargs = dict(source_width=1000, line_geometry=TextLineGeometryAnalysis(
                recommendation="perspective", confidence=.9), requested_geometry_mode="auto",
            polygon_transformer=lambda values, matrix: [p + (matrix[2], 0.) for p in values],
            jacobian_auditor=lambda *a, **kw: jacobian, scale_auditor=lambda *a, **kw: scale,
            row_auditor=lambda *a, **kw: SimpleNamespace(marker="combined-audit"),
            structural_estimator=lambda *a: structural, horizontal_estimator=lambda *a: horizontal,
            strength_optimizer=lambda *a: (horizontal, rows, .4), perspective_composer=lambda *a: combined,
            horizontal_scale_span_max=.1, vertical_scale_span_max=.12, area_scale_span_max=.15,
            anisotropy_p95_max=.08, horizontal_min_rows=10, horizontal_min_trend_deg=.1,
            horizontal_column_spread_max_deg=.5)
        kwargs.update(overrides)
        return owner.select_projective_candidate(polygons, (1000, 1400), AppSettings(), **kwargs)
    run.structural, run.horizontal, run.combined = structural, horizontal, combined
    run.rows, run.jacobian, run.scale, run.polygons = rows, jacobian, scale, polygons
    return run


def test_leaf_first_import_does_not_initialize_facade_gui_or_paddle():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.preprocess.projective_selection import ProjectiveSelection
assert 'picture_capture.preprocess.pipeline' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_safe_horizontal_selection_keeps_candidate_and_residual_audit_identity(select):
    result = select()
    assert result.selected_candidate is result.horizontal_total_candidate is select.combined
    assert result.diagnostic_candidate is result.selected_candidate
    assert result.selected_entry is result.diagnostic_entry
    assert result.selected_entry["row"] is select.rows
    assert result.selected_horizontal_strength == result.diagnostic_horizontal_strength == .4
    assert result.perspective_structural_applied and result.perspective_structural_safe
    assert result.structural_auto_safe and result.horizontal_auto_safe


@pytest.mark.parametrize("field,limit", [("horizontal_scale_span_ratio", .1),
    ("vertical_scale_span_ratio", .12), ("area_scale_span_ratio", .15), ("anisotropy_p95_ratio", .08)])
@pytest.mark.parametrize("offset,safe", [(-.00001, True), (0., True), (.00001, False)])
def test_jacobian_safety_bounds_are_inclusive(select, field, limit, offset, safe):
    setattr(select.jacobian, field, limit + offset)
    result = select()
    assert result.structural_auto_safe is safe and result.horizontal_auto_safe is safe
    assert (result.selected_candidate is not None) is safe
    assert result.diagnostic_candidate is not None


@pytest.mark.parametrize("verdict,safe", [("stable", True), ("insufficient", True), ("worse", False)])
def test_text_scale_safety_contract(select, verdict, safe):
    select.scale.verdict = verdict
    result = select()
    assert result.structural_auto_safe is safe and result.horizontal_auto_safe is safe


def test_invalid_jacobian_cannot_be_selected_automatically(select):
    select.jacobian.valid = False
    result = select()
    assert result.selected_candidate is None and result.diagnostic_candidate is not None


@pytest.mark.parametrize("strength,width,confidence,recommendation,curve,classification,safe", [
    (5., 1000, .35, "perspective", False, "keystone", True),
    (4.999, 1000, .9, "perspective", False, "keystone", False),
    (7.999, 4000, .9, "perspective", False, "keystone", False),
    (8., 4000, .9, "perspective", False, "keystone", True),
    (6., 1000, .349, "perspective", False, "keystone", False),
    (6., 1000, .9, "none", False, "keystone", False),
    (6., 1000, .9, "perspective", True, "keystone", False),
    (6., 1000, .9, "perspective", False, "parallel_drift", False),
])
def test_structural_evidence_gate_and_source_width(select, strength, width, confidence, recommendation, curve, classification, safe):
    select.structural.strength_px = strength
    select.structural.classification = classification
    result = select(source_width=width, horizontal_estimator=fail,
        line_geometry=TextLineGeometryAnalysis(confidence=confidence,
            recommendation=recommendation, separator_curve_reliable=curve))
    assert result.structural_auto_safe is safe and result.perspective_structural_safe is safe
    assert result.selected_candidate is (select.structural if safe else None)
    assert result.horizontal_strength == 0. and result.horizontal_total_candidate is None


@pytest.mark.parametrize("rows,spread,trend,column,region,verdict,safe", [
    (10, .5, .1, (), 0., "improved", True),
    (9, .1, .5, (), 0., "improved", False),
    (10, .50001, .5, (), 0., "improved", False),
    (10, 0., .5, (), 0., "improved", True),
    (10, -1., .5, (), 0., "improved", True),
    (10, .1, .0999, (), 0., "improved", False),
    (10, .1, 0., (-.2,), 0., "improved", True),
    (10, .1, 0., (), -.2, "improved", True),
    (10, .1, .5, (), 0., "stable", False),
])
def test_horizontal_row_trend_spread_and_verdict_gate(select, rows, spread, trend, column, region, verdict, safe):
    select.horizontal.horizontal_row_count = rows
    select.horizontal.horizontal_vp_column_spread_deg = spread
    select.rows.before_trend_deg = trend
    select.rows.before_column_trends_deg = column
    select.rows.before_worst_region_span_deg = region
    select.rows.verdict = verdict
    result = select(structural_estimator=fail)
    assert result.horizontal_auto_safe is safe
    assert result.selected_candidate is (select.horizontal if safe else None)


@pytest.mark.parametrize("mode,expected", [("auto", "none"), ("perspective", "horizontal")])
def test_explicit_mode_can_choose_improved_candidate_rejected_by_auto_safety(select, mode, expected):
    select.jacobian.valid = False
    result = select(requested_geometry_mode=mode)
    assert result.selected_candidate is (select.combined if expected == "horizontal" else None)
    assert not result.horizontal_auto_safe and not result.structural_auto_safe


def test_explicit_mode_prefers_structural_when_horizontal_does_not_improve(select):
    select.rows.after_metric_deg = select.rows.before_metric_deg
    result = select(requested_geometry_mode="perspective")
    assert result.selected_candidate is select.structural
    assert result.selected_horizontal_strength == 0.


def test_explicit_mode_can_keep_only_horizontal_candidate_without_improvement(select):
    select.rows.after_metric_deg = 2.
    result = select(requested_geometry_mode="perspective", structural_estimator=fail)
    assert result.selected_candidate is select.horizontal and result.selected_horizontal_strength == .4


@pytest.mark.parametrize("strength,composes", [(.749, False), (.75, True)])
def test_explicit_structural_base_threshold(select, strength, composes):
    select.structural.strength_px = strength
    calls = []
    result = select(requested_geometry_mode="perspective",
        perspective_composer=lambda *a: calls.append(a) or select.combined)
    assert bool(calls) is composes
    assert result.selected_candidate is (select.combined if composes else select.horizontal)


def test_rejected_candidates_remain_diagnostics_and_ties_keep_structural_first(select):
    select.rows.after_metric_deg = 0.
    result = select(line_geometry=TextLineGeometryAnalysis(confidence=0.))
    assert result.selected_candidate is None
    assert result.diagnostic_candidate is select.structural
    assert result.diagnostic_horizontal_strength == 0.


def test_rejected_horizontal_wins_when_its_diagnostic_cost_is_lower(select):
    def jacobian(matrix, *a, **kw):
        return SimpleNamespace(**{**vars(select.jacobian),
            "anisotropy_p95_ratio": .9 if matrix is select.structural.matrix else .01})
    result = select(jacobian_auditor=jacobian,
        line_geometry=TextLineGeometryAnalysis(confidence=0.))
    assert result.selected_candidate is None and result.diagnostic_candidate is select.horizontal
    assert result.diagnostic_horizontal_strength == .4


@pytest.mark.parametrize("operation", ["polygon_transformer", "jacobian_auditor", "scale_auditor", "row_auditor"])
def test_failed_audits_do_not_leave_partially_selected_candidates(select, operation):
    result = select(**{operation: fail})
    assert result.selected_candidate is result.diagnostic_candidate is None
    assert result.horizontal_full is result.horizontal_total_candidate is result.horizontal_row_audit is None
    assert result.horizontal_strength == 0. and not result.horizontal_auto_safe


@pytest.mark.parametrize("operation", ["horizontal_estimator", "strength_optimizer", "perspective_composer"])
def test_failed_horizontal_stage_preserves_safe_structural_candidate(select, operation):
    result = select(**{operation: fail})
    assert result.selected_candidate is select.structural
    assert result.horizontal_full is result.horizontal_total_candidate is result.horizontal_row_audit is None
    assert result.horizontal_strength == 0. and not result.horizontal_auto_safe


def test_callback_order_and_polygon_input_identity_are_preserved(select):
    calls = []
    mapped = []
    def transform(polygons, matrix):
        calls.append("map")
        assert polygons is not select.polygons
        assert all(a is b for a, b in zip(polygons, select.polygons))
        result = [p.copy() for p in polygons]
        mapped.append(result)
        return result
    def rows(before, after, *, size, settings):
        calls.append("row")
        assert after is mapped[-1]
        if len(mapped) == 1:
            assert before is not mapped[0]
            assert all(a is b for a, b in zip(before, select.polygons))
        else:
            assert before is mapped[0]
        return object()
    snapshots = [p.copy() for p in select.polygons]
    result = select(polygon_transformer=transform,
        jacobian_auditor=lambda *a, **kw: calls.append("jacobian") or select.jacobian,
        scale_auditor=lambda *a, **kw: calls.append("scale") or select.scale,
        row_auditor=rows)
    assert calls == ["map", "jacobian", "scale", "row"] * 2
    assert result.selected_entry["row"] is select.rows
    assert all(np.array_equal(a, b) for a, b in zip(snapshots, select.polygons))


def test_public_analysis_passes_current_operations_and_policy_at_call_time(monkeypatch, tmp_path):
    source = Image.new("RGB", (160, 240), "white")
    source.paste("black", (20, 40, 140, 210))
    boxes = [np.array([[20,y],[140,y],[140,y+8],[20,y+8]],float) for y in range(40,200,20)]
    monkeypatch.setattr(api, "detect_text_polygons", lambda *a: boxes)
    monkeypatch.setattr(api, "estimate_perspective_from_polygons", fail)
    monkeypatch.setattr(api, "estimate_horizontal_perspective_from_polygons", fail)
    monkeypatch.setattr(api, "AUTO_HOMOGRAPHY_AREA_SCALE_SPAN_MAX", .123)
    original = owner.select_projective_candidate
    captured = []
    def spy(*args, **kwargs):
        captured.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(owner, "select_projective_candidate", spy)
    result = api.analyze_preprocess_page(source, AppSettings(), geometry_mode="auto")
    assert len(captured) == 1
    assert captured[0]["structural_estimator"] is api.estimate_perspective_from_polygons
    assert captured[0]["row_auditor"] is api.audit_horizontal_alignment
    assert captured[0]["area_scale_span_max"] == .123
    assert captured[0]["source_width"] == 160
    page = tmp_path / "scan.png"
    api.save_analysis(tmp_path, page, result)
    assert asdict(api.load_analysis(tmp_path, page)) == asdict(result)
