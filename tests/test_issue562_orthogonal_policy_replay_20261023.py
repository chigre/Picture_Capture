"""Orthogonal policy ownership, saved-geometry replay and live facade wiring."""
from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import pickle
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from picture_capture.preprocess import pipeline as facade
from picture_capture.models import AppSettings
from picture_capture.preprocess import orthogonal_policy, replay
from picture_capture.preprocess.geometry import HorizontalAlignmentAudit
from picture_capture.preprocess.orthogonal_dewarp import OrthogonalWarpEstimate

PURE_NAMES = (
    "_absolute_horizontal_quality", "_separator_vertical_span", "_orthogonal_safe_gain_cap",
    "_orthogonal_step_payload", "_orthogonal_estimate_from_step",
)


@pytest.mark.parametrize("name", PURE_NAMES)
def test_pure_functions_have_one_body_and_historical_pickle_identity(name):
    fn = getattr(orthogonal_policy, name)
    assert getattr(facade, name) is fn
    assert fn.__module__ == "picture_capture.preprocess.pipeline"
    assert pickle.loads(pickle.dumps(fn)) is fn
    assert Path(fn.__code__.co_filename).resolve() == Path(orthogonal_policy.__file__).resolve()


def test_root_adapters_remain_thin_and_pickle_compatible():
    defs = {n.name: n for n in ast.parse(Path(facade.__file__).read_text(encoding="utf-8")).body
            if isinstance(n, ast.FunctionDef)}
    assert not set(PURE_NAMES) & defs.keys()
    for name in ("_choose_orthogonal_candidate", "geometry_corrected_image"):
        statements = [s for s in defs[name].body if not isinstance(s, ast.Expr)]
        assert len(statements) == 1 and isinstance(statements[0], ast.Return)
        assert pickle.loads(pickle.dumps(getattr(facade, name))) is getattr(facade, name)


@pytest.mark.parametrize("module", ("orthogonal_policy", "replay"))
def test_leaf_first_import_does_not_initialize_facade_gui_or_paddle(module):
    script = f"""
import importlib, sys
importlib.import_module('picture_capture.preprocess.{module}')
for name in ('picture_capture.preprocess.pipeline', 'picture_capture.app', 'paddle', 'paddleocr'):
    assert name not in sys.modules, name
"""
    subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)


@pytest.mark.parametrize("changes,expected", [
    ({}, "passed"),
    ({"after_column_trends_deg": (0.2,)}, "failed"),
    ({"row_count": 7}, "insufficient"),
    ({"after_bottom_edge_p90_abs_deg": 0.3}, "failed"),
])
def test_absolute_quality_keeps_count_and_worst_column_guards(changes, expected):
    audit = HorizontalAlignmentAudit(row_count=8, edge_pair_count=8, valid_column_count=1)
    verdict, score = facade._absolute_horizontal_quality(replace(audit, **changes))
    assert verdict == expected
    assert score >= 0


@pytest.mark.parametrize("deviation,expected", [(0.0, 1.15), (0.065, 0.95), (0.13, 0.475), (1.0, 0.06175)])
def test_gain_cap_keeps_scale_safety_budget(deviation, expected):
    assert facade._orthogonal_safe_gain_cap(OrthogonalWarpEstimate(max_scale_deviation=deviation)) == pytest.approx(expected)


def test_separator_spread_uses_y_x_order_and_minimum_samples():
    points = [(100 + i, i) for i in range(10)]
    assert facade._separator_vertical_span(points[:6]) == (6, 0.0)
    count, span = facade._separator_vertical_span(points)
    assert count == 10 and span == pytest.approx(7.2)


def _estimate():
    return OrthogonalWarpEstimate(
        y_knots=(0.0, 20.0), angle_knots_deg=(0.1, -0.2), x_knots=(0.0, 20.0),
        row_grid_rows=2, row_grid_cols=2, row_angle_grid_deg=(0.1, 0.2, 0.3, 0.4),
        row_displacement_grid_px=(0.5, 1.0, 1.5, 2.0), separator_y_knots=(0.0, 20.0),
        separator_shift_knots_px=(0.25, -0.25), reference_x=10.0, active=True,
    )


@pytest.mark.parametrize("stored_gain,expected", [(-0.5, 0.0), (0.0, 1.0), (None, 1.0), (0.55, 0.55), ("0.85", 0.85)])
def test_step_payload_roundtrip_preserves_existing_gain_defaults(stored_gain, expected):
    original = _estimate()
    payload = facade._orthogonal_step_payload(original, 0.7)
    assert set(payload) == {"row_gain", "reference_x", "y_knots", "angle_knots_deg", "x_knots",
                            "row_grid_rows", "row_grid_cols", "row_angle_grid_deg",
                            "row_displacement_grid_px", "separator_y_knots", "separator_shift_knots_px"}
    payload["row_gain"] = stored_gain
    decoded, gain = facade._orthogonal_estimate_from_step(payload)
    assert decoded == original
    assert gain == expected


def _candidate_ops(monkeypatch, reject_scale=False):
    calls = []

    def transform(polygons, estimate, *, row_gain, separator_gain):
        assert separator_gain == 1.0
        calls.append(row_gain)
        return [poly + row_gain for poly in polygons]

    def horizontal(before, after, **kwargs):
        gain = float(after[0][0, 0] - before[0][0, 0])
        return SimpleNamespace(verdict="passed", score=abs(1.0 - gain))

    def scale(before, after, size, *, writing_mode):
        assert writing_mode == "vertical-rl" and size == (20, 20)
        return SimpleNamespace(verdict="worse" if reject_scale else "passed")

    monkeypatch.setattr(facade, "transform_polygons_orthogonal", transform)
    monkeypatch.setattr(facade, "audit_horizontal_alignment", horizontal)
    monkeypatch.setattr(facade, "audit_text_scale_stability", scale)
    monkeypatch.setattr(facade, "_absolute_horizontal_quality", lambda audit: (audit.verdict, audit.score))
    return calls


def test_candidate_adapter_uses_live_ops_and_includes_fractional_cap(monkeypatch):
    source = np.asarray([[0, 0], [10, 0], [10, 5], [0, 5]], dtype=float)
    before = source.copy()
    calls = _candidate_ops(monkeypatch)
    args = ([source], _estimate(), (20, 20), AppSettings(layout_writing_mode="vertical-rl"))
    gain, mapped, verdict, baseline_score, score = facade._choose_orthogonal_candidate(*args, max_gain=0.6)
    assert calls == [0.55, 0.6]
    assert gain == 0.6 and verdict == "passed" and baseline_score == 1.0
    assert score == pytest.approx(0.4)
    np.testing.assert_array_equal(mapped[0], source + 0.6)
    np.testing.assert_array_equal(source, before)
    _candidate_ops(monkeypatch, reject_scale=True)
    gain, mapped, verdict, _, score = facade._choose_orthogonal_candidate(*args, max_gain=0.6)
    assert gain == 0 and verdict == "insufficient" and score == 1.0
    np.testing.assert_array_equal(mapped[0], source)


def test_candidate_below_safe_gain_does_not_transform(monkeypatch):
    calls = _candidate_ops(monkeypatch)
    poly = np.asarray([[0, 0], [10, 0], [10, 5], [0, 5]], dtype=float)
    result = facade._choose_orthogonal_candidate([poly], _estimate(), (20, 20),
                                                AppSettings(layout_writing_mode="vertical-rl"), max_gain=0.4)
    assert calls == []
    assert result[0] == 0 and result[2:] == ("insufficient", 1.0, 1.0)


def _analysis(**kwargs):
    data = dict(source_width=20, source_height=20, correction_angle_deg=1.25, applied_angle_deg=1.25,
                crop_box=(0, 0, 20, 20), raw_content_box=(0, 0, 20, 20), text_box=None,
                source_boxes=0, angle_samples=0, angle_mad_deg=0.0, retained_ratio=1.0,
                confidence=0.0, status="review", method="synthetic")
    data.update(kwargs)
    return facade.PreprocessAnalysis(**data)


def _replay_ops(monkeypatch):
    calls = []

    def stage(name):
        def operation(image, *args, **kwargs):
            calls.append((name, args, kwargs))
            copied = image.copy()
            copied.putpixel((0, 0), (image.getpixel((0, 0))[0] + 1, 0, 0))
            return copied
        return operation

    for name, field in (("deskew", "deskew_image"), ("homography", "apply_homography_image"),
                        ("uvdoc", "unwarp_document_image"), ("orthogonal", "apply_orthogonal_warp_image")):
        monkeypatch.setattr(facade, field, stage(name))
    return calls


@pytest.mark.parametrize("mode", ("deskew", "uvdoc"))
def test_saved_steps_replay_in_order_after_save_reopen(tmp_path, monkeypatch, mode):
    steps = tuple(facade._orthogonal_step_payload(_estimate(), gain) for gain in (0.55, 0.85))
    analysis = _analysis(geometry_mode=mode, perspective_matrix=(1., 0., 0., 0., 1., 0., 0., 0., 1.),
                         orthogonal_applied=True, orthogonal_steps=steps,
                         orthogonal_y_knots=(0., 20.), orthogonal_angle_knots_deg=(0.1, -0.2))
    page = tmp_path / "page.png"
    source = Image.new("RGB", (20, 20), "black")
    source.save(page)
    facade.save_analysis(tmp_path, page, analysis)
    reopened = facade.load_analysis(tmp_path, page)
    assert reopened is not None
    calls = _replay_ops(monkeypatch)
    result = facade.geometry_corrected_image(source, reopened)
    expected = ["deskew", "homography"] + (["uvdoc"] if mode == "uvdoc" else []) + ["orthogonal", "orthogonal"]
    assert [name for name, _, _ in calls] == expected
    assert calls[0][1] == (1.25,)
    assert [kwargs for name, _, kwargs in calls if name == "orthogonal"] == [
        {"row_gain": 0.55, "separator_gain": 1.0}, {"row_gain": 0.85, "separator_gain": 1.0}]
    assert calls[-1][1][0] == _estimate()
    assert result.getpixel((0, 0))[0] == len(expected)
    assert source.getpixel((0, 0)) == (0, 0, 0)


def test_legacy_replay_fields_and_disabled_orthogonal_branch(monkeypatch):
    source = Image.new("RGB", (20, 20), "black")
    analysis = _analysis(orthogonal_applied=True, orthogonal_y_knots=(0., 20.),
                         orthogonal_angle_knots_deg=(0.1, -0.2), orthogonal_reference_x=10.,
                         orthogonal_row_gain=0.7)
    calls = _replay_ops(monkeypatch)
    facade.geometry_corrected_image(source, analysis)
    assert [name for name, _, _ in calls] == ["deskew", "orthogonal"]
    assert calls[-1][1][0].reference_x == 10.0
    assert calls[-1][2] == {"row_gain": 0.7, "separator_gain": 1.0}
    calls.clear()
    facade.geometry_corrected_image(source, replace(analysis, orthogonal_applied=False))
    assert [name for name, _, _ in calls] == ["deskew"]
