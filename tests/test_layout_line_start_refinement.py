from __future__ import annotations

import numpy as np

from picture_capture.layout_line_start_refinement import credible_first_text_x


def _block(mask: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> None:
    mask[y0:y1, x0:x1] = True


def test_distant_residual_speck_does_not_cancel_visible_indent() -> None:
    line = np.zeros((32, 140), dtype=bool)
    _block(line, 2, 4, 12, 15)
    _block(line, 34, 42, 5, 29)
    _block(line, 45, 54, 6, 28)

    assert credible_first_text_x(line, reference=32.0, fallback=2) == 34


def test_nearby_meaningful_small_prefix_is_preserved() -> None:
    line = np.zeros((32, 140), dtype=bool)
    _block(line, 24, 28, 13, 19)
    _block(line, 33, 41, 5, 29)
    _block(line, 44, 53, 6, 28)

    assert credible_first_text_x(
        line, reference=32.0, fallback=24, anchor_x=33
    ) == 24


def test_distant_small_mark_is_not_treated_as_prefix() -> None:
    line = np.zeros((32, 180), dtype=bool)
    _block(line, 5, 8, 13, 19)
    _block(line, 50, 59, 5, 29)

    assert credible_first_text_x(
        line, reference=32.0, fallback=5, anchor_x=50
    ) == 50


def test_large_connected_residual_far_left_cannot_override_anchor() -> None:
    line = np.zeros((48, 220), dtype=bool)
    # A scan blemish large enough to pass the old component-size test.
    _block(line, 3, 8, 12, 27)
    _block(line, 74, 86, 5, 43)
    _block(line, 91, 104, 6, 42)

    assert credible_first_text_x(
        line, reference=48.0, fallback=3, anchor_x=74
    ) == 74


def test_prefix_chain_must_be_contiguous_back_from_anchor() -> None:
    line = np.zeros((40, 220), dtype=bool)
    # Distant dust must not bridge into a valid nearby tilde-like prefix.
    _block(line, 4, 8, 14, 25)
    _block(line, 55, 61, 15, 23)
    _block(line, 69, 80, 5, 36)

    assert credible_first_text_x(
        line, reference=40.0, fallback=4, anchor_x=69
    ) == 55
