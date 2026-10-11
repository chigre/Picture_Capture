"""Stable order-preserving one-to-one alignment of dictionary entry markers.

All callers provide *reading-order-sorted* sequences (column then canonical V).
Use maximum cardinality first, then minimum total positional displacement;
nearest-first greedy matching can lose valid entries on dense dictionary pages.
No OCR dependency, no scipy dependency, no mutation of entry objects.
"""
from __future__ import annotations

from collections.abc import Iterable


def match_ordered_markers(
    left_count: int,
    right_count: int,
    edges: Iterable[tuple[int | float, int, int]],
) -> list[tuple[int, int]]:
    """Return (left_index, right_index) pairs in monotonically increasing order.

    Edges carry (absolute_distance, left_index, right_index), and should only
    include same-column pairs within the caller's explicit tolerance. This
    permits mode-specific CJK/regular matching windows without hidden policy.

    The dynamic program optimizes (number of pairs, -sum(distance)). If both
    values tie, skipping the later right-hand observation is preferred, giving
    a stable result without depending on dictionary iteration order.
    """
    n, m = int(left_count), int(right_count)
    if n < 0 or m < 0:
        raise ValueError("Marker counts must be nonnegative")
    if not n or not m:
        return []

    allowed: dict[tuple[int, int], float] = {}
    for cost, left, right in edges:
        left, right = int(left), int(right)
        if not (0 <= left < n and 0 <= right < m):
            raise ValueError("Marker edge index outside its sequence")
        cost = float(cost)
        if not 0 <= cost < float("inf"):
            raise ValueError("Marker distance must be finite and nonnegative")
        key = (left, right)
        allowed[key] = min(cost, allowed.get(key, float("inf")))

    # Full DP, but memory stays bounded by the number of marker candidates per
    # page (usually tens, not tens of thousands). No recursion or float scores
    # that conflate one extra true match with shorter distances.
    best: list[list[tuple[int, float]]] = [
        [(0, 0.0) for _ in range(m + 1)] for _ in range(n + 1)
    ]
    moves = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            # 1=skip left; 2=skip right; 3=match.
            chosen = best[i - 1][j]
            move = 1
            if best[i][j - 1] > chosen:
                chosen, move = best[i][j - 1], 2
            distance = allowed.get((i - 1, j - 1))
            if distance is not None:
                candidate = (
                    best[i - 1][j - 1][0] + 1,
                    best[i - 1][j - 1][1] - distance,
                )
                if candidate > chosen:
                    chosen, move = candidate, 3
            best[i][j], moves[i][j] = chosen, move

    result: list[tuple[int, int]] = []
    i, j = n, m
    while i and j:
        move = moves[i][j]
        if move == 3:
            result.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif move == 1:
            i -= 1
        else:
            j -= 1
    result.reverse()
    return result
