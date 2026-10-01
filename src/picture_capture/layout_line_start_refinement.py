from __future__ import annotations

"""Robust per-line visual start estimation for Page Understanding.

Shared denoising removes isolated scan specks, but a few-pixel connected remnant
can still survive near a column edge.  The historical ``LayoutLine.first_x``
used the first X column with minimal ink support, so one such remnant could make
a visibly indented continuation line appear unindented.

This module keeps semantic ``anchor_x`` unchanged.  It only refines ``first_x``
into the first credible visual text component, while preserving a genuine small
prefix (tilde, number, bullet-like mark) when it sits immediately before a
substantial text component.
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
        # Inline equivalent of the short-gap fill used by Page Design.  Keeping
        # it local avoids importing private helpers into startup patch code.
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


def credible_first_text_x(line: np.ndarray, reference: float, fallback: int) -> int:
    """Return the first visually meaningful text component in a line."""
    components = _component_stats(line, reference)
    if not components:
        return int(fallback)

    ref = max(6.0, float(reference))

    def substantial(item: tuple[int, int, int, int]) -> bool:
        x0, x1, h, area = item
        width = x1 - x0
        return bool(
            area >= max(4, round(ref * ref * 0.012))
            and (
                h >= ref * 0.28
                or width >= ref * 0.16
            )
        )

    main_index = next((i for i, item in enumerate(components) if substantial(item)), None)
    if main_index is None:
        return int(fallback)

    main = components[main_index]
    first_x = int(main[0])

    # Preserve one or more real small prefixes only when they are close to the
    # first substantial glyph.  Distant dust remains excluded.
    prefix_gap_limit = max(3, round(ref * 0.62))
    prefix_area_min = max(2, round(ref * ref * 0.0025))
    current_left = first_x
    for item in reversed(components[:main_index]):
        x0, x1, h, area = item
        gap = current_left - int(x1)
        meaningful_prefix = bool(
            area >= prefix_area_min
            and (
                h >= ref * 0.10
                or (x1 - x0) >= ref * 0.07
            )
        )
        if gap < 0 or gap > prefix_gap_limit or not meaningful_prefix:
            break
        first_x = int(x0)
        current_left = int(x0)

    return int(first_x)


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
        visual_start = credible_first_text_x(line, reference, int(result.first_x))
        if visual_start == int(result.first_x):
            return result
        return replace(result, first_x=int(visual_start))

    page_design._line_feature = refined_line_feature
    page_design._robust_line_starts_installed = True
