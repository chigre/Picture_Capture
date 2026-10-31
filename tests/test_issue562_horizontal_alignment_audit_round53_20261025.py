"""Issue #562 Round 53: horizontal alignment safety math has one no-GUI owner."""
from __future__ import annotations

import ast
from dataclasses import fields
import inspect
from pathlib import Path
import pickle
import subprocess
import sys

import numpy as np
import pytest

from picture_capture.preprocess import geometry
from picture_capture.preprocess import horizontal_alignment_audit as owner


ROOT = Path(__file__).resolve().parents[1]


def _rows(angles: list[float], *, x: float = 20.0):
    return [(x, 20.0 + i * 30.0, angle, 24.0) for i, angle in enumerate(angles)]


def test_owner_is_independent_and_legacy_result_class_remains_pickle_visible():
    root = ROOT / "src/picture_capture/preprocess"
    source = (root / "horizontal_alignment_audit.py").read_text(encoding="utf-8")
    original = (root / "geometry.py").read_text(encoding="utf-8")
    nodes = {
        node.name: node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
    }
    assert {
        "horizontal_row_stats", "horizontal_region_angles",
        "horizontal_tail_p90_abs", "horizontal_metric", "audit_horizontal_alignment",
    } <= nodes.keys()
    assert "np.polyfit" in source
    assert "after_edge_pair_delta_p90" in source
    assert "HORIZONTAL_ALIGNMENT_MAX_AFTER_EDGE_DEG = ops.max_after_edge_deg" in source
    assert "from .geometry" not in source
    assert "picture_capture.app" not in source
    assert "import tkinter" not in source
    assert original.count("def audit_horizontal_alignment(") == 1
    assert "_horizontal_alignment_audit.audit_horizontal_alignment(" in original
    for name in (
        "_horizontal_row_stats", "_horizontal_region_angles",
        "_horizontal_tail_p90_abs", "_horizontal_metric", "audit_horizontal_alignment",
    ):
        fn = getattr(geometry, name)
        assert Path(fn.__code__.co_filename).resolve() == root / "geometry.py"
        assert callable(fn)
    assert geometry.HorizontalAlignmentAudit.__module__ == "picture_capture.preprocess.geometry"
    assert pickle.loads(pickle.dumps(geometry.HorizontalAlignmentAudit)) is geometry.HorizontalAlignmentAudit
    assert "verdict" in {f.name for f in fields(geometry.HorizontalAlignmentAudit)}


def test_leaf_first_import_does_not_pull_geometry_or_tk_shell():
    script = """
import importlib, sys
importlib.import_module('picture_capture.preprocess.horizontal_alignment_audit')
assert 'picture_capture.app' not in sys.modules
assert 'picture_capture.preprocess.geometry' not in sys.modules
assert 'tkinter' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, capture_output=True,
        text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_row_fitter_handles_missing_and_nontrivial_y_angle_trend():
    with pytest.raises(RuntimeError, match="有效文本行不足"):
        geometry._horizontal_row_stats(_rows([0.1] * 4))
    vals = _rows([-0.2 + i * 0.04 for i in range(10)])
    middle, top, bottom, trend, mad, span = geometry._horizontal_row_stats(vals)
    assert abs(middle) < 0.05
    assert top < 0 < bottom
    assert trend > 0.3
    assert mad < 1e-6
    assert span > 250


def test_region_and_tail_callbacks_preserve_live_legacy_patchpoints(monkeypatch):
    rows = _rows([
        0.5, 0.45, 0.4, 0.3, 0.2, 0.1, 0.05, 0.0, 0.0, 0.0,
        0.0, -0.05, -0.1, -0.2, -0.3, -0.4, -0.45, -0.5, -0.5, -0.5,
    ])
    median_calls = []
    percentile_calls = []
    old_median = geometry._weighted_median_pairs
    old_pct = geometry._weighted_percentile_pairs

    def spy_median(values):
        median_calls.append(len(values))
        return old_median(values)

    def spy_percentile(values, percentile):
        percentile_calls.append((len(values), percentile))
        return old_pct(values, percentile)

    monkeypatch.setattr(geometry, "_weighted_median_pairs", spy_median)
    monkeypatch.setattr(geometry, "_weighted_percentile_pairs", spy_percentile)
    top, middle, bottom = geometry._horizontal_region_angles(
        rows, fallback=(0, 0, 0),
    )
    assert top > middle > bottom
    assert len(median_calls) == 3
    tail_top, tail_bottom = geometry._horizontal_tail_p90_abs(rows)
    assert tail_top == pytest.approx(0.5)
    assert tail_bottom == pytest.approx(0.5)
    assert len(percentile_calls) == 2
    assert all(percentile == 90.0 for _, percentile in percentile_calls)
    assert geometry._horizontal_metric(0.1, 0.2, -0.4, 0.2, 0.1) == pytest.approx(
        0.4 + 0.45 * 0.2 + 0.35 * 0.1
    )


def test_full_audit_uses_original_column_owner_and_live_safety_thresholds(monkeypatch):
    values = [-0.26 + i * 0.052 for i in range(10)]
    columns_before = [_rows(values, x=20), _rows(values, x=300)]
    columns_after = [_rows([0.0] * 10, x=20), _rows([0.0] * 10, x=300)]
    calls = []

    def grouped(polygons, size, settings, *, fixed_groups=None):
        calls.append((size, settings, fixed_groups))
        if fixed_groups is None:
            return columns_before, [list(range(10)), list(range(10, 20))]
        assert fixed_groups == [list(range(10)), list(range(10, 20))]
        return columns_after, fixed_groups

    monkeypatch.setattr(geometry, "_horizontal_column_rows", grouped)
    monkeypatch.setattr(
        geometry, "_horizontal_polygon_edge_metrics",
        lambda *_: (0, 0.0, 0.0, 0.0, 0.0),
    )
    polys = [np.asarray([[0, 0], [10, 0], [10, 5], [0, 5]], dtype=float)] * 20
    report = geometry.audit_horizontal_alignment(polys, polys, (600, 500))
    assert type(report) is geometry.HorizontalAlignmentAudit
    assert report.column_count == 2
    assert report.valid_column_count == 2
    assert report.row_count == 20
    assert report.verdict == "improved"
    assert report.improvement_ratio > 0.5
    assert len(calls) == 2
    assert calls[0][2] is None and calls[1][2] is not None

    monkeypatch.setattr(geometry, "HORIZONTAL_ALIGNMENT_MIN_IMPROVEMENT", 1.1)
    denied = geometry.audit_horizontal_alignment(polys, polys, (600, 500))
    assert denied.verdict == "stable"


def test_short_audit_keeps_insufficient_class_and_unchanged_signatures():
    polys = [np.asarray([[0, 0], [20, 0], [20, 8], [0, 8]], dtype=float)] * 3
    report = geometry.audit_horizontal_alignment(polys, polys)
    assert type(report) is geometry.HorizontalAlignmentAudit
    assert report.verdict == "insufficient" and report.row_count == 3
    assert list(inspect.signature(geometry.audit_horizontal_alignment).parameters) == [
        "before_polygons", "after_polygons", "size", "settings",
    ]
    assert list(inspect.signature(geometry._horizontal_tail_p90_abs).parameters) == [
        "rows", "fraction",
    ]
    assert pickle.loads(pickle.dumps(report)) == report
