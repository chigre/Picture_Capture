from __future__ import annotations

import numpy as np


def legacy_row_brightness_scores_1000(
    rgb_sum: np.ndarray,
    xs: np.ndarray,
    score_top: int,
    score_bottom: int,
    span: int,
) -> tuple[int, ...]:
    """Return historical VB row-brightness scores for one fixed horizontal span."""
    top = max(0, int(score_top))
    bottom = min(int(rgb_sum.shape[0]), int(score_bottom))
    if bottom <= top:
        return ()
    region = rgb_sum[top:bottom, xs].astype(np.float64)
    denominator = float(765 * max(1, int(span)))
    return tuple(
        int(round(float(total) / denominator * 1000.0))
        for total in region.sum(axis=1)
    )
