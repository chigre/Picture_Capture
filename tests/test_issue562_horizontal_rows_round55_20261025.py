"""Issue #562 Round 55: horizontal text rows and structural columns have one owner."""
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

from picture_capture.preprocess import geometry, horizontal_rows
from picture_capture.models import AppSettings


ROOT = Path(__file__).resolve().parents[1]


def _box(cx: float, cy: float, width: float = 48.0, height: float = 12.0):
    return np.asarray([
        [cx-width/2, cy-height/2],
        [cx+width/2, cy-height/2],
        [cx+width/2, cy+height/2],
        [cx-width/2, cy+height/2],
    ], dtype=float)


def test_no_gui_owner_contains_real_column_and_row_algorithms_not_empty_facade():
    canonical = ROOT / "src/picture_capture/preprocess/horizontal_rows.py"
    old_file = ROOT / "src/picture_capture/preprocess/geometry.py"
    source = canonical.read_text(encoding="utf-8")
    old = old_file.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    expected = {
        "normalize_text_angle", "weighted_median_pairs",
        "weighted_percentile_pairs", "horizontal_polygon_edge_angles",
        "horizontal_polygon_sample", "horizontal_polygon_edge_metrics",
        "cluster_horizontal_samples", "horizontal_rows", "horizontal_column_indices",
        "horizontal_column_rows", "public_horizontal_column_rows",
    }
    assert set(functions) == expected
    assert "np.argmax(overlaps)" in source
    assert "box_width > typical_width * 1.35" in source
    assert "median_height * 0.72" in source
    assert "edge_pair = edge_angles(poly)" in source
    assert "picture_capture.app" not in source
    assert "from .geometry" not in source
    assert "import tkinter" not in source
    assert "_horizontal_rows_owner." in old
    for name in expected:
        old_name = ("horizontal_column_rows" if name == "public_horizontal_column_rows"
                    else "_" + name)
        # Every original callable still has its own Python function code object.
        fn = getattr(geometry, old_name)
        assert Path(fn.__code__.co_filename).resolve() == old_file.resolve()
        assert pickle.loads(pickle.dumps(fn)) is fn


def test_leaf_import_does_not_load_geometry_gui_layout_or_ocr():
    script = """
import importlib, sys
importlib.import_module('picture_capture.preprocess.horizontal_rows')
for name in ('picture_capture.preprocess.geometry', 'picture_capture.app',
             'picture_capture.layout.detection', 'tkinter', 'paddleocr'):
    assert name not in sys.modules, name
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT,
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_edge_angles_reject_malformed_and_vertical_glyphs_and_capture_both_edges():
    assert geometry._horizontal_polygon_edge_angles(np.ones((2, 2))) is None
    assert geometry._horizontal_polygon_sample(np.asarray([[1, 2], [2, 3]])) is None
    assert geometry._horizontal_polygon_sample(_box(50, 50, width=6, height=30)) is None
    edge = geometry._horizontal_polygon_edge_angles(_box(50, 50))
    assert edge is not None
    assert edge[0][0] == pytest.approx(0.0)
    assert edge[1][0] == pytest.approx(0.0)
    assert edge[0][1] == pytest.approx(48.0)
    assert edge[1][1] == pytest.approx(48.0)
    assert geometry._normalize_text_angle(91.0) == pytest.approx(-89.0)


def test_weighted_statistics_and_cluster_membership_preserve_semantics():
    assert geometry._weighted_median_pairs([]) == 0.0
    assert geometry._weighted_percentile_pairs([], 90) == 0.0
    assert geometry._weighted_median_pairs([(1, 0), (5, 0), (10, 0)]) == 5.0
    assert geometry._weighted_median_pairs([(1, 8), (10, 1)]) == 1.0
    assert geometry._weighted_percentile_pairs([(1, 8), (10, 1)], 90) == 10.0
    assert geometry._cluster_horizontal_samples([]) == []
    samples = [
        (60, 20, 0.0, 40, 12),
        (90, 22, 0.1, 20, 12),
        (60, 60, -0.3, 40, 12),
        (92, 63, -0.2, 20, 12),
    ]
    rows = geometry._cluster_horizontal_samples(samples)
    assert len(rows) == 2
    assert rows[0][1] == pytest.approx(20)
    assert rows[1][1] == pytest.approx(60)
    assert rows[0][3] == pytest.approx(60)


def test_real_column_assignment_excludes_spanning_header_and_keeps_staggered_rows(monkeypatch):
    polygons = []
    for i in range(8):
        polygons.extend([
            _box(55, 25 + i * 32),
            _box(205, 29 + i * 32),
            _box(355, 33 + i * 32),
        ])
    header = _box(205, 10, width=350)
    polygons.append(header)
    calls = []
    def layout(boxes, size, **kwargs):
        calls.append((boxes, size, kwargs))
        return SimpleNamespace(
            column_starts=(0, 150, 300),
            column_rights=(140, 290, 450),
        )
    monkeypatch.setattr(geometry, "infer_layout_from_boxes", layout)
    settings = AppSettings(layout_columns_policy="fixed", columns=3)
    groups, starts = geometry._horizontal_column_indices(polygons, (450, 310), settings)
    assert starts == (0, 150, 300)
    assert [len(g) for g in groups] == [8, 8, 8]
    assert all(24 not in g for g in groups)
    rows = geometry.horizontal_column_rows(polygons, (450, 310), settings)
    assert [len(col) for col in rows] == [8, 8, 8]
    assert calls and all(call[2]["columns_policy"] == "fixed" for call in calls)


def test_fallback_to_single_column_and_fixed_groups_bypass_layout(monkeypatch):
    polygons = [_box(60, 20+i*32) for i in range(7)]
    monkeypatch.setattr(
        geometry, "infer_layout_from_boxes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("no layout")),
    )
    groups, starts = geometry._horizontal_column_indices(polygons, (200, 280))
    assert groups == [list(range(7))] and starts == (0,)
    rows, indices = geometry._horizontal_column_rows(
        polygons, (200, 280), fixed_groups=[[0, 1, 2], [3, 4, 5, 6]],
    )
    assert indices == [[0, 1, 2], [3, 4, 5, 6]]
    assert len(rows) == 2 and [len(r) for r in rows] == [3, 4]


def test_original_callback_patchpoints_are_live_after_extraction(monkeypatch):
    fake = np.asarray([[0, 0], [40, 0], [40, 8], [0, 8]], dtype=float)
    points = [fake] * 6
    calls = []
    def sample(polygon):
        calls.append(polygon.shape)
        return (20.0, float(10 + 30 * len(calls)), 0.0, 40.0, 8.0)
    monkeypatch.setattr(geometry, "_horizontal_polygon_sample", sample)
    monkeypatch.setattr(geometry, "_horizontal_column_indices",
                        lambda *_a, **_kw: ([list(range(6))], (0,)))
    rows, groups = geometry._horizontal_column_rows(points, (200, 300))
    assert len(groups) == 1 and len(rows[0]) == 6
    assert len(calls) == 6
    assert list(inspect.signature(geometry._horizontal_column_rows).parameters) == [
        "polygons", "size", "settings", "fixed_groups",
    ]
    assert list(inspect.signature(geometry.horizontal_column_rows).parameters) == [
        "polygons", "size", "settings",
    ]
