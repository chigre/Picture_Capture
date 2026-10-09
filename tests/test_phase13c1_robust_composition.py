"""Phase 13C1: explicit robust wrapper and legacy installer share one implementation."""
from types import SimpleNamespace

import numpy as np

from picture_capture import layout_line_start_refinement as robust


def test_explicit_robust_composition_uses_supplied_inner_callable(monkeypatch):
    calls = []
    line = SimpleNamespace(first_x=12, anchor_x=18)
    def inner(column, ink, y0, y1, reference, previous_end):
        calls.append((column, y0, y1, reference, previous_end))
        return line
    monkeypatch.setattr(robust, "credible_first_text_x", lambda *args: 6)
    composed = robust.compose_robust_line_feature(inner)
    result = composed(2, np.ones((12, 24), dtype=bool), 2, 9, 10., 0)
    assert calls == [(2, 2, 9, 10., 0)]
    assert result.first_x == 6
    assert line.first_x == 12


def test_explicit_robust_composition_preserves_no_line_result():
    fn = robust.compose_robust_line_feature(lambda *args: None)
    assert fn(0, np.zeros((10, 20), dtype=bool), 0, 3, 8., 0) is None


def test_explicit_robust_composition_preserves_identity_when_unchanged(monkeypatch):
    line = SimpleNamespace(first_x=7, anchor_x=None)
    monkeypatch.setattr(robust, "credible_first_text_x", lambda *args: 7)
    fn = robust.compose_robust_line_feature(lambda *args: line)
    assert fn(0, np.ones((10, 20), dtype=bool), 0, 8, 8., 0) is line
