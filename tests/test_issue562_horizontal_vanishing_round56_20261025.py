"""Issue #562 Round 56: common horizontal vanishing-point fitting and homography."""
from __future__ import annotations

import ast
import inspect
import math
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from picture_capture.preprocess import geometry, horizontal_vanishing


ROOT = Path(__file__).resolve().parents[1]


def _vp_columns(vp=(9000.0, 500.0), count=16):
    columns = []
    for x in (120.0, 610.0):
        rows = []
        for i in range(count):
            y = 80.0 + i * 38.0
            angle = math.degrees(math.atan2(vp[1] - y, vp[0] - x))
            rows.append((x, y, angle, 250.0))
        columns.append(rows)
    return columns


def test_math_has_new_physical_leaf_owner_and_old_signatures_remain():
    source_path = ROOT / "src/picture_capture/preprocess/horizontal_vanishing.py"
    compat_path = ROOT / "src/picture_capture/preprocess/geometry.py"
    source = source_path.read_text(encoding="utf-8")
    compat = compat_path.read_text(encoding="utf-8")
    names = {
        x.name for x in ast.parse(source).body if isinstance(x, ast.FunctionDef)
    }
    assert names == {
        "fit_horizontal_vanishing_point",
        "horizontal_vp_column_spread_deg",
        "estimate_horizontal_perspective_from_polygons",
    }
    assert "np.linalg.lstsq" in source
    assert "from_center @ align @ projective @ to_center" in source
    assert "from .geometry" not in source
    assert "picture_capture.app" not in source
    assert "import tkinter" not in source
    assert "_horizontal_vanishing.estimate_horizontal_perspective_from_polygons(" in compat
    assert "HORIZONTAL_VP_MIN_ROWS = ops.vp_min_rows" in source
    assert "HORIZONTAL_VP_MIN_TREND_DEG = ops.vp_min_trend_deg" in source
    for func in ("_fit_horizontal_vanishing_point", "_horizontal_vp_column_spread_deg",
                 "estimate_horizontal_perspective_from_polygons"):
        original = getattr(geometry, func)
        assert Path(original.__code__.co_filename).resolve() == compat_path.resolve()
        assert pickle.loads(pickle.dumps(original)) is original
    assert list(inspect.signature(geometry.estimate_horizontal_perspective_from_polygons).parameters) == [
        "polygons", "size", "settings",
    ]


def test_leaf_first_import_does_not_initialize_geometry_tk_or_ocr():
    script = """
import importlib, sys
importlib.import_module('picture_capture.preprocess.horizontal_vanishing')
for name in ('picture_capture.preprocess.geometry', 'picture_capture.app', 'tkinter', 'paddleocr'):
    assert name not in sys.modules, name
"""
    proc = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT,
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_common_vp_fit_balances_columns_and_rejects_insufficient_or_flat_lines(monkeypatch):
    source_columns = _vp_columns()
    x, y = geometry._fit_horizontal_vanishing_point(source_columns)
    assert x == pytest.approx(9000.0, abs=0.01)
    assert y == pytest.approx(500.0, abs=0.01)
    assert geometry._horizontal_vp_column_spread_deg(source_columns, (x, y)) < 0.001

    with pytest.raises(RuntimeError, match="有效文本行不足"):
        geometry._fit_horizontal_vanishing_point([source_columns[0][:4]])
    flat = [[(100.0, i * 28.0, 0.0, 100.0) for i in range(15)]]
    with pytest.raises(RuntimeError, match="角度变化过小"):
        geometry._fit_horizontal_vanishing_point(flat)

    monkeypatch.setattr(geometry, "HORIZONTAL_VP_MIN_ROWS", 100)
    with pytest.raises(RuntimeError, match="有效文本行不足"):
        geometry._fit_horizontal_vanishing_point(source_columns)


def test_column_spread_uses_current_angle_and_weighted_median_hooks(monkeypatch):
    cols = _vp_columns()
    normal = geometry._normalize_text_angle
    median = geometry._weighted_median_pairs
    seen = {"normal": 0, "median": 0}

    def spy_normal(angle):
        seen["normal"] += 1
        return normal(angle)

    def spy_median(values):
        seen["median"] += 1
        return median(values)

    monkeypatch.setattr(geometry, "_normalize_text_angle", spy_normal)
    monkeypatch.setattr(geometry, "_weighted_median_pairs", spy_median)
    value = geometry._horizontal_vp_column_spread_deg(cols, (9000, 500))
    assert value < 0.001
    assert seen["normal"] == 2 * 2 * 16
    assert seen["median"] == 2


def test_estimation_uses_existing_column_geometry_and_returns_pickle_visible_result(monkeypatch):
    rows = _vp_columns()
    fake_polygons = [
        np.asarray([[1, 1], [30, 1], [30, 10], [1, 10]], dtype=float)
    ] * 32
    calls = {"grouped": 0, "mapper": 0, "fit": 0}
    original_fit = geometry._fit_horizontal_vanishing_point
    original_mapper = geometry.transform_points_homography

    def column_rows(polygons, size, settings):
        calls["grouped"] += 1
        assert size == (900, 1000)
        return rows, [list(range(16)), list(range(16, 32))]

    def spy_fit(columns):
        calls["fit"] += 1
        return original_fit(columns)

    def spy_mapper(points, matrix):
        calls["mapper"] += 1
        return original_mapper(points, matrix)

    monkeypatch.setattr(geometry, "_horizontal_column_rows", column_rows)
    monkeypatch.setattr(geometry, "_fit_horizontal_vanishing_point", spy_fit)
    monkeypatch.setattr(geometry, "transform_points_homography", spy_mapper)
    estimate = geometry.estimate_horizontal_perspective_from_polygons(
        fake_polygons, (900, 1000),
    )
    assert type(estimate) is geometry.PerspectiveEstimate
    assert estimate.classification == "horizontal_vp"
    assert estimate.horizontal_row_count == 32
    assert estimate.horizontal_column_count == 2
    assert estimate.horizontal_vanishing_x == pytest.approx(9000, abs=0.01)
    assert estimate.horizontal_vanishing_y == pytest.approx(500, abs=0.01)
    assert len(estimate.matrix) == 9 and len(estimate.source_quad) == 8
    assert all(np.isfinite(estimate.matrix))
    assert calls == {"grouped": 1, "mapper": 1, "fit": 1}
    assert pickle.loads(pickle.dumps(estimate)) == estimate


def test_near_vp_and_insufficient_rows_gate_remain_strict(monkeypatch):
    polys = [np.asarray([[1, 1], [30, 1], [30, 10], [1, 10]], dtype=float)] * 32
    rows = _vp_columns()
    monkeypatch.setattr(
        geometry, "_horizontal_column_rows",
        lambda *_a, **_kw: (rows, [list(range(16)), list(range(16, 32))]),
    )
    monkeypatch.setattr(
        geometry, "_fit_horizontal_vanishing_point",
        lambda columns: (800.0, 500.0),
    )
    with pytest.raises(RuntimeError, match="过近"):
        geometry.estimate_horizontal_perspective_from_polygons(polys, (900, 1000))

    monkeypatch.setattr(
        geometry, "_horizontal_column_rows",
        lambda *_a, **_kw: ([rows[0][:3], rows[1][:3]], [list(range(3)), list(range(3, 6))]),
    )
    with pytest.raises(RuntimeError, match="有效文本行不足"):
        geometry.estimate_horizontal_perspective_from_polygons(polys, (900, 1000))
