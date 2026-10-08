from __future__ import annotations

import numpy as np

from picture_capture.dictionary_page_design import LayoutLine, _shape_consensus
from picture_capture.ordinary_visual import _patch_similarity


def _line(patch: np.ndarray, index: int) -> LayoutLine:
    return LayoutLine(
        column=0,
        y0=index,
        y1=index + 1,
        first_x=0,
        anchor_x=0,
        anchor_width=1,
        anchor_height=1,
        gap_before=0,
        patch=np.asarray(patch, dtype=bool),
        has_small_prefix=False,
    )


def _historical_shape_consensus(lines: list[LayoutLine]) -> float:
    usable = [line for line in lines if line.patch.size]
    if len(usable) < 2:
        return 0.0
    return max(
        sum(
            _patch_similarity(prototype.patch, line.patch) >= 0.52
            for line in usable
        ) / float(len(usable))
        for prototype in usable
    )


def test_shape_consensus_matches_historical_pairwise_similarity_exactly() -> None:
    rng = np.random.default_rng(20261008)

    for count in (0, 1, 2, 3, 8, 25):
        for _case in range(20):
            lines: list[LayoutLine] = []
            for index in range(count):
                height = int(rng.integers(1, 80))
                width = int(rng.integers(1, 100))
                probability = float(rng.uniform(0.01, 0.8))
                patch = rng.random((height, width)) < probability
                lines.append(_line(patch, index))

            assert _shape_consensus(lines) == _historical_shape_consensus(lines)


def test_shape_consensus_matches_historical_degenerate_patches() -> None:
    cases = [
        [np.zeros((8, 8), dtype=bool), np.zeros((8, 8), dtype=bool)],
        [np.ones((8, 8), dtype=bool), np.ones((8, 8), dtype=bool)],
        [np.zeros((8, 8), dtype=bool), np.ones((8, 8), dtype=bool)],
        [
            np.eye(16, dtype=bool),
            np.fliplr(np.eye(16, dtype=bool)),
            np.eye(16, dtype=bool),
        ],
    ]

    for patches in cases:
        lines = [_line(patch, index) for index, patch in enumerate(patches)]
        assert _shape_consensus(lines) == _historical_shape_consensus(lines)
