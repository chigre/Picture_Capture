"""Issue #562 Round 57: structural perspective and four-corner entrypoint ownership."""
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

from picture_capture.preprocess import geometry, structural_perspective
from picture_capture.models import AppSettings


ROOT = Path(__file__).resolve().parents[1]


def test_single_structural_math_owner_with_original_functions_and_pickle_identity():
    path = ROOT / "src/picture_capture/preprocess/structural_perspective.py"
    geometry_path = ROOT / "src/picture_capture/preprocess/geometry.py"
    code = path.read_text(encoding="utf-8")
    surface = geometry_path.read_text(encoding="utf-8")
    definitions = {n.name for n in ast.parse(code).body if isinstance(n, ast.FunctionDef)}
    assert definitions == {
        "layout", "column_pitch", "column_left_samples", "robust_line",
        "estimate_perspective_from_polygons", "perspective_from_quad",
    }
    assert "np.polyfit" in code
    assert 'classification = "keystone"' in code
    assert "四角顺序发生交叉" in code
    assert "picture_capture.app" not in code
    assert "from .geometry" not in code
    assert "tkinter" not in code
    assert "from ..layout" not in code
    for name in ("_layout", "_column_pitch", "_column_left_samples",
                 "_robust_line", "estimate_perspective_from_polygons",
                 "perspective_from_quad"):
        fn = getattr(geometry, name)
        assert Path(fn.__code__.co_filename).resolve() == geometry_path.resolve()
        assert pickle.loads(pickle.dumps(fn)) is fn
        assert f"def {name}(" in surface


def test_leaf_first_import_does_not_initialize_geometry_or_gui():
    code = """
import importlib, sys
importlib.import_module('picture_capture.preprocess.structural_perspective')
for name in ('picture_capture.preprocess.geometry', 'picture_capture.app',
             'picture_capture.layout.detection', 'tkinter', 'paddleocr'):
    assert name not in sys.modules, name
"""
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT,
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_robust_boundary_line_and_pitch_preserve_legacy_rejections():
    assert geometry._column_pitch((50,), 0, 400) == 200
    assert geometry._column_pitch((50, 200), 0, 400) == 150
    assert geometry._column_pitch((50, 200, 340), 1, 400) == 140
    with pytest.raises(RuntimeError, match="栏左轨迹样本不足"):
        geometry._robust_line([(1, 5), (2, 5), (3, 5), (4, 5)])
    samples = [(float(y), 50 + 0.10 * y) for y in range(0, 450, 30)]
    samples.append((180.0, 400.0))
    slope, intercept = geometry._robust_line(samples)
    assert slope == pytest.approx(0.10, abs=0.02)
    assert intercept == pytest.approx(50.0, abs=4.0)


def test_column_layout_requires_valid_text_boxes_and_two_columns(monkeypatch):
    settings = AppSettings()
    tiny = [(5, 10, 40, 20)] * 7
    monkeypatch.setattr(geometry, "polygon_boxes", lambda *_: tiny)
    with pytest.raises(RuntimeError, match="需要更多有效文本框"):
        geometry._layout([], (600, 500), settings)
    monkeypatch.setattr(geometry, "polygon_boxes", lambda *_: tiny + tiny)
    seen = []
    def infer(boxes, size, **kwargs):
        seen.append(kwargs)
        return SimpleNamespace(column_starts=(50,))
    monkeypatch.setattr(geometry, "infer_layout_from_boxes", infer)
    with pytest.raises(RuntimeError, match="至少需要两栏"):
        geometry._layout([], (600, 500), settings)
    monkeypatch.setattr(
        geometry, "infer_layout_from_boxes",
        lambda *_a, **_kw: SimpleNamespace(column_starts=(50, 400)),
    )
    boxes, result = geometry._layout([], (600, 500), settings)
    assert len(boxes) == 14 and result.column_starts == (50, 400)
    assert seen[0]["display_scale"] == 1.0 and seen[0]["ink_mask"] is None


def test_column_left_sampling_keeps_only_anchor_boxes_inside_body_roi():
    estimate = SimpleNamespace(
        column_starts=(60, 300), character_height=12, start_y=30,
        bottom_y=280, column_width=180,
    )
    boxes = []
    for y in (40, 80, 120, 160, 200, 240):
        boxes.extend([(60, y, 100, y+12), (300, y, 340, y+12)])
    boxes.extend([(130, 120, 180, 132), (370, 120, 420, 132), (60, 400, 100, 412)])
    samples = geometry._column_left_samples(boxes, estimate, 600)
    assert [len(column) for column in samples] == [6, 6]


def test_structural_estimate_preserves_original_keystone_classification_and_callbacks(monkeypatch):
    fake = SimpleNamespace(
        column_starts=(50, 450), start_y=40, bottom_y=450,
        character_height=12, column_width=280,
    )
    calls = {"layout": 0, "samples": 0, "solve": 0}
    def layout(polygons, size, settings):
        calls["layout"] += 1
        return [], fake
    def samples(boxes, estimate, width):
        calls["samples"] += 1
        y = [float(v) for v in range(60, 421, 40)]
        return [
            [(v, 50 + 0.08 * v) for v in y],
            [(v, 450 - 0.06 * v) for v in y],
        ]
    old_solve = geometry._homography
    def solve(src, dst):
        calls["solve"] += 1
        return old_solve(src, dst)
    monkeypatch.setattr(geometry, "_layout", layout)
    monkeypatch.setattr(geometry, "_column_left_samples", samples)
    monkeypatch.setattr(geometry, "_homography", solve)
    result = geometry.estimate_perspective_from_polygons([], (600, 500), AppSettings())
    assert type(result) is geometry.PerspectiveEstimate
    assert result.classification == "keystone"
    assert result.candidate_source == "structural"
    assert result.width_change_ratio > 0.003
    assert len(result.matrix) == 9
    assert calls == {"layout": 1, "samples": 1, "solve": 1}
    assert pickle.loads(pickle.dumps(result)) == result


def test_manual_quad_validates_order_bounds_and_original_source_canvas():
    valid = (50, 40, 250, 40, 220, 260, 60, 260)
    estimate = geometry.perspective_from_quad(valid, (300, 300))
    assert type(estimate) is geometry.PerspectiveEstimate
    assert estimate.classification == "manual"
    assert estimate.source_quad == tuple(float(v) for v in valid)
    mapped = geometry.transform_points_homography(
        np.asarray(valid, dtype=float).reshape(4, 2), estimate.matrix,
    )
    np.testing.assert_allclose(
        mapped,
        np.asarray(estimate.target_quad).reshape(4, 2),
        atol=1e-8,
    )
    with pytest.raises(ValueError, match="4 个二维坐标"):
        geometry.perspective_from_quad((1, 2, 3), (300, 300))
    with pytest.raises(ValueError, match="页面宽度过小"):
        geometry.perspective_from_quad((0, 40, 10, 40, 10, 260, 0, 260), (300, 300))
    with pytest.raises(ValueError, match="顺序发生交叉"):
        geometry.perspective_from_quad((50, 40, 250, 40, 60, 260, 220, 260), (300, 300))
    with pytest.raises(ValueError, match="无效坐标"):
        geometry.perspective_from_quad((float("nan"), 40, 250, 40, 220, 260, 60, 260), (300, 300))
    assert list(inspect.signature(geometry.perspective_from_quad).parameters) == ["quad", "size"]
