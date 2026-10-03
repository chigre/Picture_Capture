from __future__ import annotations

import numpy as np

from picture_capture.layout_physical_indent import _credible_first_ink_x


def test_thin_horizontal_leading_glyph_counts_as_text_start() -> None:
    line = np.zeros((40, 120), dtype=bool)
    line[20:22, 8:30] = True  # thin horizontal glyph such as 一
    line[8:34, 48:66] = True  # later full-height glyph

    assert _credible_first_ink_x(line, 40.0) == 8


def test_isolated_speck_does_not_count_as_text_start() -> None:
    line = np.zeros((40, 120), dtype=bool)
    line[5, 3] = True  # isolated noise
    line[8:34, 42:60] = True

    assert _credible_first_ink_x(line, 40.0) == 42


def test_short_noise_cluster_before_thin_glyph_is_ignored() -> None:
    line = np.zeros((40, 120), dtype=bool)
    line[2:4, 2:4] = True
    line[19:21, 12:38] = True
    line[7:34, 50:68] = True

    assert _credible_first_ink_x(line, 40.0) == 12
