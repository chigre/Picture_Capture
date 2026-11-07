"""Issue #562 Round 54: horizontal perspective interpolation and strength ownership."""
from __future__ import annotations

import ast
import inspect
import pickle
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from picture_capture.preprocess import geometry, horizontal_strength


ROOT = Path(__file__).resolve().parents[1]


def _estimate(dx: float = 0.0, dy: float = 0.0):
    matrix = (1.0, 0.0, dx, 0.0, 1.0, dy, 0.0, 0.0, 1.0)
    quad = (0.0, 0.0, 49.0, 0.0, 49.0, 29.0, 0.0, 29.0)
    return geometry.PerspectiveEstimate(
        matrix=matrix,
        source_quad=quad,
        target_quad=quad,
        strength_px=max(abs(dx), abs(dy)),
        classification="horizontal_vp",
        candidate_source="horizontal_vp",
        horizontal_vanishing_x=1000.0,
        horizontal_vanishing_y=800.0,
    )


def test_leaf_owner_and_public_geometry_class_preserve_source_abi():
    root = ROOT / "src/picture_capture/preprocess"
    source = (root / "horizontal_strength.py").read_text(encoding="utf-8")
    geometry_src = (root / "geometry.py").read_text(encoding="utf-8")
    found = {n.name: n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
    assert {
        "interpolate_perspective_estimate",
        "optimize_horizontal_perspective_strength",
        "compose_perspective_estimates",
    } <= found.keys()
    assert "np.linalg.det" in source
    assert "fine_values: set[float]" in source
    assert "from .geometry" not in source
    assert "picture_capture.app" not in source
    assert "tkinter" not in source
    for name in found:
        assert f"def {name}(" in geometry_src
        assert f"_horizontal_strength.{name}(" in geometry_src
        assert Path(getattr(geometry, name).__code__.co_filename).resolve() == root / "geometry.py"
    assert geometry.PerspectiveEstimate.__module__ == "picture_capture.preprocess.geometry"
    assert pickle.loads(pickle.dumps(geometry.PerspectiveEstimate)) is geometry.PerspectiveEstimate


def test_owner_leaf_first_import_has_no_geometry_or_gui_dependency():
    code = """
import importlib, sys
importlib.import_module('picture_capture.preprocess.horizontal_strength')
assert 'picture_capture.preprocess.geometry' not in sys.modules
assert 'picture_capture.app' not in sys.modules
assert 'tkinter' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_interpolation_clamps_strength_keeps_coordinate_space_and_raises_on_degenerate():
    estimate = _estimate(12, -6)
    original = estimate.matrix
    quarter = geometry.interpolate_perspective_estimate(
        estimate, (50, 30), 0.25, candidate_source="diagnostic",
    )
    assert isinstance(quarter, geometry.PerspectiveEstimate)
    assert quarter.matrix == pytest.approx((1, 0, 3, 0, 1, -1.5, 0, 0, 1))
    assert quarter.candidate_source == "diagnostic"
    assert quarter.classification == "horizontal_vp"
    assert quarter.horizontal_vanishing_x == estimate.horizontal_vanishing_x
    assert geometry.interpolate_perspective_estimate(estimate, (50, 30), -9).matrix == pytest.approx(
        (1, 0, 0, 0, 1, 0, 0, 0, 1)
    )
    assert geometry.interpolate_perspective_estimate(estimate, (50, 30), 9).matrix == pytest.approx(
        original
    )
    assert estimate.matrix == original

    bad = geometry.PerspectiveEstimate(
        matrix=(0,) * 9, source_quad=estimate.source_quad,
        target_quad=estimate.target_quad, strength_px=0.0,
    )
    with pytest.raises(RuntimeError, match="退化"):
        geometry.interpolate_perspective_estimate(bad, (50, 30), 1.0)


def test_composition_is_correct_and_preserves_live_point_mapper(monkeypatch):
    first, second = _estimate(3, 0), _estimate(0, -4)
    original = geometry.transform_points_homography
    calls = []
    def spy(points, matrix):
        calls.append(tuple(matrix))
        return original(points, matrix)
    monkeypatch.setattr(geometry, "transform_points_homography", spy)
    composed = geometry.compose_perspective_estimates(first, second, (50, 30))
    assert type(composed) is geometry.PerspectiveEstimate
    assert composed.matrix == pytest.approx((1, 0, 3, 0, 1, -4, 0, 0, 1))
    assert composed.classification == "combined"
    assert composed.candidate_source == "structural+horizontal_vp"
    assert composed.horizontal_vanishing_x == second.horizontal_vanishing_x
    assert len(calls) == 1
    assert pickle.loads(pickle.dumps(composed)) == composed


def test_strength_optimizer_captures_live_geometry_callbacks_and_search_policy(monkeypatch):
    polys = [np.asarray([[0, 0], [20, 0], [20, 8], [0, 8]], dtype=float)] * 12
    calls = {"transform": 0, "audit": 0, "interpolate": []}
    original_interp = geometry.interpolate_perspective_estimate

    def interpolate(estimate, size, strength, *, candidate_source=None):
        calls["interpolate"].append(strength)
        return original_interp(
            estimate, size, strength, candidate_source=candidate_source,
        )

    def transform(polygons, matrix):
        calls["transform"] += 1
        return list(polygons)

    def audit(_before, _after, *, size=None, settings=None):
        calls["audit"] += 1
        return SimpleNamespace(
            before_trend_deg=0.4,
            before_column_trends_deg=(),
            after_trend_deg=0.1,
            after_column_trends_deg=(),
            after_worst_edge_deg=0.0,
            after_edge_pair_delta_p90_deg=0.0,
            edge_pair_count=0,
            after_metric_deg=0.0,
            after_worst_region_deg=0.0,
            after_worst_column_metric_deg=0.0,
        )

    monkeypatch.setattr(geometry, "interpolate_perspective_estimate", interpolate)
    monkeypatch.setattr(geometry, "transform_polygons_homography", transform)
    monkeypatch.setattr(geometry, "audit_horizontal_alignment", audit)
    candidate, scored, strength = geometry.optimize_horizontal_perspective_strength(
        polys, (50, 30), _estimate(5, 0),
    )
    assert type(candidate) is geometry.PerspectiveEstimate
    assert strength == pytest.approx(geometry.HORIZONTAL_STRENGTH_MIN)
    assert scored.after_metric_deg == 0.0
    assert calls["audit"] > 5
    assert calls["transform"] == calls["audit"]
    assert len(calls["interpolate"]) == calls["audit"] - 1
    assert min(calls["interpolate"]) >= geometry.HORIZONTAL_STRENGTH_MIN


def test_optimizer_rejects_insufficient_polygons_before_callback_execution(monkeypatch):
    monkeypatch.setattr(
        geometry, "audit_horizontal_alignment",
        lambda *_args, **_kwargs: pytest.fail("called on inadequate samples"),
    )
    with pytest.raises(RuntimeError, match="有效文本框不足"):
        geometry.optimize_horizontal_perspective_strength([], (50, 30), _estimate())


def test_public_signatures_preserved():
    assert list(inspect.signature(geometry.interpolate_perspective_estimate).parameters) == [
        "estimate", "size", "strength", "candidate_source",
    ]
    assert list(inspect.signature(geometry.optimize_horizontal_perspective_strength).parameters) == [
        "polygons", "size", "full_estimate", "settings",
    ]
    assert list(inspect.signature(geometry.compose_perspective_estimates).parameters) == [
        "first", "second", "size",
    ]
