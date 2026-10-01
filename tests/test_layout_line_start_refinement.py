from __future__ import annotations

import numpy as np

from picture_capture.layout_line_start_refinement import credible_first_text_x


def _block(mask: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> None:
    mask[y0:y1, x0:x1] = True


def test_distant_residual_speck_does_not_cancel_visible_indent() -> None:
    line = np.zeros((32, 140), dtype=bool)
    # Connected residual near the column edge: enough to survive a simple
    # first-ink-column rule, but far too small to be text.
    _block(line, 2, 4, 12, 15)
    # Real first word starts much farther right.
    _block(line, 34, 42, 5, 29)
    _block(line, 45, 54, 6, 28)

    assert credible_first_text_x(line, reference=32.0, fallback=2) == 34


def test_nearby_meaningful_small_prefix_is_preserved() -> None:
    line = np.zeros((32, 140), dtype=bool)
    # Small tilde/number-like prefix immediately before the main text.
    _block(line, 24, 28, 13, 19)
    _block(line, 33, 41, 5, 29)
    _block(line, 44, 53, 6, 28)

    assert credible_first_text_x(line, reference=32.0, fallback=24) == 24


def test_distant_small_mark_is_not_treated_as_prefix() -> None:
    line = np.zeros((32, 180), dtype=bool)
    _block(line, 5, 8, 13, 19)
    _block(line, 50, 59, 5, 29)

    assert credible_first_text_x(line, reference=32.0, fallback=5) == 50
