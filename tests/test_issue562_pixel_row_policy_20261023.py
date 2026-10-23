"""Candidate retention, final convergence and retained-image diagnostics."""
from __future__ import annotations

from dataclasses import asdict, replace
import pickle
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from picture_capture import image_preprocessing as api
from picture_capture.models import AppSettings
from picture_capture.preprocess import pixel_row_policy as policy
from picture_capture.preprocess.orthogonal_dewarp import PixelRowProfileAudit

LIMITS = dict(row_p90_max_px=1.5, row_worst_max_px=2.5,
              tail_p90_max_px=1.5, tail_worst_max_px=2.5,
              tail_progress_ratio=.7, tail_max_regression_px=.25)
BASELINE = PixelRowProfileAudit(sample_count=24, valid_column_count=2,
    p90_shift_px=5., worst_shift_px=6., bottom_tail_sample_count=8,
    bottom_tail_valid_column_count=2, bottom_tail_p90_shift_px=6., bottom_tail_worst_shift_px=6.)


def candidate(**values):
    return replace(BASELINE, p90_shift_px=1., worst_shift_px=1., **values)


@pytest.fixture
def current():
    return policy.RetainedPixelDiagnostics(row_sample_count=30,
        before_row_p90_px=11., after_row_p90_px=2., before_row_worst_px=12., after_row_worst_px=3.,
        row_verdict="improved_review", tail_sample_count=9,
        before_tail_p90_px=13., after_tail_p90_px=4., before_tail_worst_px=14., after_tail_worst_px=5.,
        tail_verdict="failed", alignment_verdict="failed")


@pytest.fixture
def reaudit(current):
    image = Image.new("RGB", (50, 80), (10, 20, 30))
    polygons = [np.zeros((4, 2))]
    settings = AppSettings()
    def run(audit=None, **changes):
        options = dict(applied=True, current=current, warnings=[],
            pixel_auditor=lambda *a: audit if audit is not None else candidate(),
            initial_row_available=True, initial_row_p90_px=5., initial_row_worst_px=6.,
            initial_tail_available=True, initial_tail_p90_px=6., initial_tail_worst_px=6., **LIMITS)
        options.update(changes)
        return policy.reaudit_retained_pixels(image, polygons, settings, **options)
    run.image, run.polygons, run.settings = image, polygons, settings
    return run


def test_leaf_first_import_does_not_initialize_facade_gui_or_paddle():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.preprocess.pixel_row_policy import CandidatePixelAssessment
assert 'picture_capture.image_preprocessing' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


@pytest.mark.parametrize("samples,columns,available", [(7, 1, False), (8, 0, False), (8, 1, True)])
def test_candidate_row_evidence_bounds(samples, columns, available):
    value = candidate(sample_count=samples, valid_column_count=columns)
    result = policy.assess_candidate_pixels(value, BASELINE, **LIMITS)
    assert result.row_available is available
    assert result.row_verdict == ("passed" if available else "insufficient")


@pytest.mark.parametrize("p90,worst,verdict", [(1.5, 2.5, "passed"),
    (1.5001, 2.5, "failed"), (1.5, 2.5001, "failed")])
def test_candidate_absolute_limits_are_inclusive(p90, worst, verdict):
    value = replace(BASELINE, p90_shift_px=p90, worst_shift_px=worst)
    result = policy.assess_candidate_pixels(value, replace(BASELINE, sample_count=7), **LIMITS)
    assert result.row_verdict == verdict


@pytest.mark.parametrize("p90,worst,improved", [(3.5, 4.8, True),
    (3.5001, 4.8, False), (3.5, 4.8001, False)])
def test_candidate_relative_improvement_is_inclusive(p90, worst, improved):
    value = replace(BASELINE, p90_shift_px=p90, worst_shift_px=worst)
    result = policy.assess_candidate_pixels(value, BASELINE, **LIMITS)
    assert result.row_improved is improved
    assert result.row_verdict == ("improved_review" if improved else "failed")


@pytest.mark.parametrize("baseline_p90,improved", [(1e-6, False), (1.0001e-6, True)])
def test_baseline_epsilon_is_strict(baseline_p90, improved):
    # A zero candidate shift isolates the baseline epsilon from the absolute pass gate.
    result = policy.assess_candidate_pixels(replace(candidate(), p90_shift_px=0.),
        replace(BASELINE, p90_shift_px=baseline_p90), **LIMITS)
    assert result.row_improved is improved and result.row_verdict == "passed"


@pytest.mark.parametrize("samples,columns,available", [(1, 1, False), (2, 0, False), (2, 1, True)])
def test_candidate_tail_evidence_bounds(samples, columns, available):
    value = candidate(bottom_tail_sample_count=samples, bottom_tail_valid_column_count=columns)
    result = policy.assess_candidate_pixels(value, BASELINE, **LIMITS)
    assert result.tail_available is available
    assert result.tail_verdict == ("failed" if available else "insufficient")
    assert result.tail_retainable


@pytest.mark.parametrize("p90,worst,verdict,retainable", [
    (1.5, 2.5, "passed", True), (6. * .7, 6.25, "improved_review", True),
    (4.2001, 6.25, "failed", True), (6.25, 6.25, "failed", True),
    (6.2501, 6.25, "failed", False), (6.25, 6.2501, "failed", False),
])
def test_tail_retention_and_pass_remain_separate(p90, worst, verdict, retainable):
    value = candidate(bottom_tail_p90_shift_px=p90, bottom_tail_worst_shift_px=worst)
    result = policy.assess_candidate_pixels(value, BASELINE, **LIMITS)
    assert result.row_verdict == "passed"
    assert result.tail_verdict == verdict and result.tail_retainable is retainable


def test_missing_baseline_tail_cannot_justify_failed_tail_retention():
    result = policy.assess_candidate_pixels(candidate(), replace(BASELINE, bottom_tail_sample_count=1), **LIMITS)
    assert result.tail_verdict == "failed" and not result.tail_retainable


@pytest.mark.parametrize("applied,boxes,samples", [(False, True, 24), (True, False, 24), (True, True, 7)])
def test_skip_or_insufficient_final_audit_preserves_prior_values(reaudit, current, applied, boxes, samples):
    calls = []
    def auditor(*args):
        calls.append(args)
        return replace(candidate(), sample_count=samples)
    if not boxes:
        result = policy.reaudit_retained_pixels(reaudit.image, [], reaudit.settings,
            applied=applied, current=current, warnings=[], pixel_auditor=auditor,
            initial_row_available=True, initial_row_p90_px=5., initial_row_worst_px=6.,
            initial_tail_available=True, initial_tail_p90_px=6., initial_tail_worst_px=6., **LIMITS)
    else:
        result = reaudit(applied=applied, pixel_auditor=auditor)
    assert result == current
    assert bool(calls) is (applied and boxes)


def test_final_row_measurement_preserves_legacy_sample_only_gate(reaudit):
    measured = replace(candidate(), valid_column_count=0,
        bottom_tail_p90_shift_px=1., bottom_tail_worst_shift_px=1.)
    assert policy.assess_candidate_pixels(measured, BASELINE, **LIMITS).row_verdict == "insufficient"
    final = reaudit(measured)
    assert final.row_verdict == final.tail_verdict == final.alignment_verdict == "passed"


@pytest.mark.parametrize("row,tail,expected", [
    ("passed", "passed", "passed"), ("passed", "improved_review", "improved_review"),
    ("passed", "failed", "failed"), ("passed", "insufficient", "passed"),
    ("improved_review", "passed", "improved_review"),
    ("improved_review", "improved_review", "improved_review"),
    ("improved_review", "failed", "failed"),
    ("improved_review", "insufficient", "improved_review"),
    ("failed", "passed", "failed"), ("failed", "improved_review", "failed"),
    ("failed", "failed", "failed"), ("failed", "insufficient", "failed"),
])
def test_final_combined_verdict_table(reaudit, row, tail, expected):
    p90, worst = {"passed": (1., 1.), "improved_review": (3., 4.), "failed": (5., 7.)}[row]
    tail_p90, tail_worst = {"passed": (1., 1.), "improved_review": (4., 5.),
                            "failed": (6., 7.), "insufficient": (6., 7.)}[tail]
    result = reaudit(replace(BASELINE, p90_shift_px=p90, worst_shift_px=worst,
        bottom_tail_p90_shift_px=tail_p90, bottom_tail_worst_shift_px=tail_worst,
        bottom_tail_sample_count=1 if tail == "insufficient" else 8))
    assert result.row_verdict == row and result.tail_verdict == tail
    assert result.alignment_verdict == expected
    assert (result.before_row_p90_px, result.before_row_worst_px) == (5., 6.)
    assert (result.after_row_p90_px, result.after_row_worst_px) == (p90, worst)
    assert (result.before_tail_p90_px, result.before_tail_worst_px) == (6., 6.)
    assert (result.after_tail_p90_px, result.after_tail_worst_px) == (tail_p90, tail_worst)


def test_unavailable_initial_evidence_keeps_prior_before_metrics(reaudit, current):
    result = reaudit(initial_row_available=False, initial_tail_available=False)
    assert result.before_row_p90_px == current.before_row_p90_px
    assert result.before_row_worst_px == current.before_row_worst_px
    assert result.before_tail_p90_px == current.before_tail_p90_px
    assert result.before_tail_worst_px == current.before_tail_worst_px
    assert result.tail_verdict == "failed"


def test_audit_failure_preserves_prior_diagnostics_and_appends_warning(reaudit, current):
    warnings = ["earlier"]
    def fail(*args):
        raise RuntimeError("audit-failure")
    result = reaudit(pixel_auditor=fail, warnings=warnings)
    assert result == current
    assert warnings == ["earlier", "最终正交像素行复检不可用：audit-failure"]


def test_partial_audit_failure_preserves_updates_already_made(reaudit, current):
    warnings = []
    result = reaudit(SimpleNamespace(sample_count=8), warnings=warnings)
    assert result.row_sample_count == 8
    assert result.before_row_p90_px == 5. and result.before_row_worst_px == 6.
    assert result.after_row_p90_px == current.after_row_p90_px
    assert result.tail_sample_count == current.tail_sample_count
    assert result.alignment_verdict == current.alignment_verdict
    assert len(warnings) == 1 and warnings[0].startswith("最终正交像素行复检不可用：")


def test_final_callback_receives_retained_image_and_inputs_without_mutation(reaudit):
    before = reaudit.image.tobytes()
    calls = []
    def auditor(image, polygons, settings):
        assert image is reaudit.image and polygons is reaudit.polygons and settings is reaudit.settings
        calls.append(1)
        return replace(candidate(), bottom_tail_p90_shift_px=1., bottom_tail_worst_shift_px=1.)
    result = reaudit(pixel_auditor=auditor)
    assert calls == [1] and result.alignment_verdict == "passed"
    assert reaudit.image.tobytes() == before


def test_public_composition_keeps_live_auditor_policy_and_saved_model(monkeypatch, tmp_path):
    image = Image.new("RGB", (100, 200), "white")
    image.paste("black", (20, 40, 80, 160))
    monkeypatch.setattr(api, "detect_text_polygons", lambda *args: [])
    monkeypatch.setattr(api, "_projection_skew_fallback", lambda *args, **kwargs: 0.)
    monkeypatch.setattr(api, "PIXEL_ROW_PROFILE_P90_MAX_PX", .123)
    original = policy.reaudit_retained_pixels
    captured = []
    def spy(*args, **kwargs):
        captured.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(policy, "reaudit_retained_pixels", spy)
    result = api.analyze_preprocess_page(image, AppSettings(), geometry_mode="deskew")
    assert captured[0]["pixel_auditor"] is api.audit_pixel_row_profiles
    assert captured[0]["row_p90_max_px"] == .123
    assert captured[0]["applied"] is False
    page = tmp_path / "scan.png"
    api.save_analysis(tmp_path, page, result)
    assert asdict(api.load_analysis(tmp_path, page)) == asdict(result)
    assert pickle.loads(pickle.dumps(result)) == result
