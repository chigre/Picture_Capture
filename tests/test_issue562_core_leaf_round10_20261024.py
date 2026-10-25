"""Issue #562: visual-boundary measurement leaf remains monkeypatch-compatible."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from picture_capture import paddle_headwords as public_paddle
from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import boundary_measurements
from picture_capture.ocr.headword_models import OCRLine, OCRRecord

PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def settings(**kw):
    values = dict(
        paddle_separator_column_margin=10,
        paddle_separator_roi_width_ratio=50,
        paddle_auto_header_rule=True,
        paddle_header_search_height=30,
        paddle_header_rule_ink_ratio=0.8,
        paddle_header_rule_margin=3,
    )
    values.update(kw)
    return SimpleNamespace(**values)


def test_leaf_presence_original_signatures_and_model_identity():
    assert len(list(PKG.glob("*.py"))) == 7
    assert (PKG / "ocr/boundary_measurements.py").is_file()
    assert not (PKG / "boundary_measurements.py").exists()
    for fn in (
        core._ink_ratio, core._leading_box, core._true_runs,
        core._separator_analysis_x_bounds, core._header_cutoff,
    ):
        assert fn.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(core._header_cutoff).parameters) == [
        "gray", "settings", "ratio",
    ]
    assert core.OCRLine is OCRLine
    assert OCRLine.__module__ == "picture_capture.paddle_headwords_core"


def test_ink_ratio_clamped_box_and_leading_lemma_rectangle():
    gray = np.full((10, 10), 255, dtype=np.uint8)
    gray[2:5, 3:6] = 0
    for box, want in (
        ((0, 0, 10, 10), 0.09),
        ((3, 2, 6, 5), 1.0),
        ((20, 0, 30, 10), 0.0),
    ):
        assert core._ink_ratio(gray, box) == boundary_measurements.ink_ratio(gray, box) == want
    record = OCRRecord("casablanca", 0.9, (10, 20, 110, 35))
    line = OCRLine("casablanca", 0.9, (10, 20, 110, 35), [record])
    assert core._leading_box(line, 4) == boundary_measurements.leading_box(line, 4)
    assert core._leading_box(line, 4) == (10, 20, 55, 35)
    assert core._leading_box(OCRLine("", 0.0, (1, 1, 5, 5), []), 0) == (1, 1, 5, 5)


def test_true_runs_with_adjacent_tail_and_empty_arrays():
    for seq, want in (
        ([False, True, True, False, True], [(1, 3), (4, 5)]),
        ([True, True], [(0, 2)]),
        ([False, False], []),
        ([], []),
    ):
        values = np.asarray(seq, dtype=bool)
        assert core._true_runs(values) == boundary_measurements.true_runs(values) == want


def test_separator_roi_respects_margin_and_minimum_width():
    cfg = settings()
    for width, scale in ((120, 1.0), (30, 1.0), (120, 0.5)):
        assert core._separator_analysis_x_bounds(width, cfg, scale) == (
            boundary_measurements.separator_analysis_x_bounds(width, cfg, scale)
        )
    assert core._separator_analysis_x_bounds(120, cfg) == (10, 60)


def test_header_cutoff_and_live_runs_monkeypatch(monkeypatch):
    gray = np.full((50, 60), 255, dtype=np.uint8)
    gray[15, :] = 0
    cfg = settings()
    assert core._header_cutoff(gray, cfg, 1.0) == boundary_measurements.header_cutoff(gray, cfg, 1.0) == 19
    cfg.paddle_auto_header_rule = False
    assert core._header_cutoff(gray, cfg, 1.0) == 0
    cfg.paddle_auto_header_rule = True
    original = core._true_runs
    monkeypatch.setattr(public_paddle, "_true_runs", lambda active: [(0, 4)])
    assert core._header_cutoff(gray, cfg, 1.0) == 7
    monkeypatch.setattr(public_paddle, "_true_runs", original)
