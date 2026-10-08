from __future__ import annotations

import numpy as np

from picture_capture.adaptive_denoise import _box_sum, _box_sums


def test_shared_box_sums_match_individual_zero_padded_sums() -> None:
    rng = np.random.default_rng(20261008)
    radii = ((2, 2), (5, 5), (6, 0), (0, 6), (8, 8))

    for shape, probability in (
        ((1, 1), 1.0),
        ((7, 11), 0.2),
        ((31, 37), 0.05),
        ((64, 48), 0.65),
    ):
        mask = rng.random(shape) < probability
        shared = _box_sums(mask, radii)

        assert len(shared) == len(radii)
        for actual, (radius_y, radius_x) in zip(shared, radii):
            expected = _box_sum(mask, radius_y, radius_x)
            np.testing.assert_array_equal(actual, expected)


def test_shared_box_sums_accepts_empty_radius_list() -> None:
    mask = np.zeros((5, 7), dtype=bool)
    assert _box_sums(mask, ()) == ()
