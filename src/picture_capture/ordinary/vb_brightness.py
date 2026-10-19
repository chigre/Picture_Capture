from __future__ import annotations

import numpy as np


def legacy_row_brightness_scores_1000(
    rgb_sum: np.ndarray,
    xs: np.ndarray,
    top: int,
    candidate_y: int,
    upward: int,
    span: int,
) -> dict[int, int]:
    """Return historical VB brightness scores for rows probed by fallback search."""
    score_top = max(int(top), int(candidate_y) - int(upward))
    score_bottom = min(int(rgb_sum.shape[0]), int(candidate_y))
    if score_bottom <= score_top:
        return {}
    region = rgb_sum[score_top:score_bottom, xs].astype(np.float64)
    denominator = float(765 * max(1, int(span)))
    return {
        score_top + index: int(round(float(total) / denominator * 1000.0))
        for index, total in enumerate(region.sum(axis=1))
    }
