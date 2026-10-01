from __future__ import annotations

"""Robust per-line physical-indent estimation for Page Understanding.

Shared denoising removes isolated scan specks, but a few-pixel connected remnant
can still survive near a column edge.  The historical ``LayoutLine.first_x``
used the first X column with minimal ink support, so one such remnant could make
a visibly indented continuation line appear unindented.

Physical indent is now measured from the column edge as a *leading whitespace*
quantity.  We scan rightward and end the blank span only when a short horizontal
window contains sustained, multi-column text ink.  Tiny residual marks therefore
do not collapse the indent, while a real printed prefix such as ``~`` or a
numbered marker still counts as the physical beginning of the row.

``anchor_x`` remains available as structural evidence and as a conservative
fallback, but it no longer defines the physical indent lane.
"""

from dataclasses import replace
from typing import Any

import numpy as np


def _component_stats(line: np.ndarray, reference: float) -> list[tuple[int, int, int, int]]:
    """Return (x0, x1, height, ink_area) for horizontal ink groups."""
    if line.ndim != 2 or line.size == 0:
        return []
    height = max(1, int(line.shape[0]))
    support = max(1, round(height * 0.055))
    active = line.sum(axis=0) >= support
    gap = max(1, round(float(reference) * 0.025))
    if gap > 0 and active.size:
        indices = np.flatnonzero(active)
        if indices.size >= 2:
            for left, right in zip(indices, indices[1:]):
                if 0 < int(right - left - 1) <= gap:
                    active[left:right + 1] = True

    runs: list[tuple[int, int, int, int]] = []
    start: int | None = None
    for x, value in enumerate(active.tolist() + [False]):
        if value and start is None:
            start = x
        elif not value and start is not None:
            x0, x1 = int(start), int(x)
            component = line[:, x0:x1]
            ys = np.flatnonzero(component.any(axis=1))
            if ys.size:
                runs.append((
                    x0,
                    x1,
                    int(ys[-1] - ys[0] + 1),
                    int(component.sum()),
                ))
            start = None
    return runs


def leading_whitespace_end(
    line: np.ndarray,
    reference: float,
    *,
    anchor_x: int | None = None,
) -> int | None:
    """Return where the continuous leading blank span ends.

    A candidate start must be supported by a short horizontal window containing
    enough ink area *and* enough active columns.  This is deliberately different
    from taking the first foreground pixel/component: sparse dust may exist in
    the leading blank without terminating it.

    If ``anchor_x`` exists, extremely remote weak marks are additionally guarded
    against: a physical prefix may precede the anchor, but it must still look
    like sustained printed ink rather than an isolated scan blemish.
    """
    if line.ndim != 2 or line.size == 0:
        return None

    ref = max(6.0, float(reference))
    height, width = line.shape
    support = np.asarray(line, dtype=np.uint8).sum(axis=0)

    # A real row start should occupy more than one narrow pixel column.  The
    # window stays small enough for punctuation/tilde prefixes to remain valid.
    window = max(4, round(ref * 0.18))
    window = min(window, max(1, width))
    column_support = max(1, round(max(1, height) * 0.075))
    min_active_columns = max(2, round(window * 0.34))
    min_area = max(5, round(ref * ref * 0.010))

    active = support >= column_support
    area_prefix = np.concatenate(([0], np.cumsum(support, dtype=np.int64)))
    active_prefix = np.concatenate(([0], np.cumsum(active.astype(np.int64))))

    max_x = max(0, width - window)
    for x in range(max_x + 1):
        x1 = min(width, x + window)
        area = int(area_prefix[x1] - area_prefix[x])
        active_columns = int(active_prefix[x1] - active_prefix[x])
        if area < min_area or active_columns < min_active_columns:
            continue

        # Find the first actually supported ink column within the accepted
        # window so the reported indent hugs the printed prefix/glyph itself.
        local = np.flatnonzero(active[x:x1])
        if local.size == 0:
            continue
        onset = int(x + int(local[0]))

        if anchor_x is not None and onset < int(anchor_x):
            distance = int(anchor_x) - onset
            # A very distant candidate before the structural anchor needs a
            # slightly stronger local footprint to be trusted as a true prefix.
            if distance > ref * 1.35:
                strong_area = max(min_area * 2, round(ref * ref * 0.020))
                strong_columns = max(min_active_columns + 1, round(window * 0.48))
                if area < strong_area or active_columns < strong_columns:
                    continue

        return onset

    return None


def _prefix_start_before_anchor(
    components: list[tuple[int, int, int, int]],
    anchor_x: int,
    reference: float,
) -> int:
    """Fallback: walk left from a trusted anchor through nearby real prefixes."""
    ref = max(6.0, float(reference))
    current_left = int(anchor_x)
    first_x = int(anchor_x)
    prefix_gap_limit = max(3, round(ref * 0.62))
    prefix_area_min = max(2, round(ref * ref * 0.0025))

    candidates = [item for item in components if int(item[1]) <= int(anchor_x)]
    for item in reversed(candidates):
        x0, x1, h, area = item
        if int(x0) <= int(anchor_x) < int(x1):
            current_left = int(x0)
            first_x = min(first_x, int(x0))
            continue
        gap = current_left - int(x1)
        meaningful_prefix = bool(
            area >= prefix_area_min
            and (
                h >= ref * 0.10
                or (x1 - x0) >= ref * 0.07
            )
        )
        if gap < 0:
            continue
        if gap > prefix_gap_limit or not meaningful_prefix:
            break
        first_x = int(x0)
        current_left = int(x0)

    return int(first_x)


def credible_first_text_x(
    line: np.ndarray,
    reference: float,
    fallback: int,
    anchor_x: int | None = None,
) -> int:
    """Return the physical row start measured from leading whitespace."""
    onset = leading_whitespace_end(
        line,
        reference,
        anchor_x=anchor_x,
    )
    if onset is not None:
        return int(onset)

    components = _component_stats(line, reference)
    if not components:
        return int(fallback)

    if anchor_x is not None:
        return _prefix_start_before_anchor(
            components, int(anchor_x), float(reference)
        )

    ref = max(6.0, float(reference))

    def substantial(item: tuple[int, int, int, int]) -> bool:
        x0, x1, h, area = item
        width = x1 - x0
        return bool(
            area >= max(6, round(ref * ref * 0.022))
            and (
                h >= ref * 0.40
                or width >= ref * 0.24
            )
        )

    main_index = next((i for i, item in enumerate(components) if substantial(item)), None)
    if main_index is None:
        return int(fallback)

    main = components[main_index]
    return _prefix_start_before_anchor(
        components[:main_index + 1], int(main[0]), float(reference)
    )


def install_robust_line_starts() -> None:
    """Patch Page Design's line-feature builder exactly once."""
    from . import dictionary_page_design as page_design

    if getattr(page_design, "_robust_line_starts_installed", False):
        return

    original = page_design._line_feature

    def refined_line_feature(
        column: int,
        ink: np.ndarray,
        y0: int,
        y1: int,
        reference: float,
        previous_end: int,
    ) -> Any:
        result = original(column, ink, y0, y1, reference, previous_end)
        if result is None:
            return None
        line = ink[y0:y1]
        visual_start = credible_first_text_x(
            line,
            reference,
            int(result.first_x),
            None if result.anchor_x is None else int(result.anchor_x),
        )
        if visual_start == int(result.first_x):
            return result
        return replace(result, first_x=int(visual_start))

    page_design._line_feature = refined_line_feature
    page_design._robust_line_starts_installed = True
