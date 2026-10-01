from __future__ import annotations

"""Robust per-line visual start estimation for Page Understanding.

Shared denoising removes isolated scan specks, but a few-pixel connected remnant
can still survive near a column edge.  The historical ``LayoutLine.first_x``
used the first X column with minimal ink support, so one such remnant could make
a visibly indented continuation line appear unindented.

This module keeps semantic ``anchor_x`` unchanged.  It refines ``first_x`` by
anchoring on the first full-height structural glyph whenever one exists, then
only admits nearby small prefixes (tilde, number, bullet-like mark) as the true
visual start.  Distant residual specks therefore cannot redefine the indent.
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


def _prefix_start_before_anchor(
    components: list[tuple[int, int, int, int]],
    anchor_x: int,
    reference: float,
) -> int:
    """Walk left from a trusted structural anchor through nearby real prefixes."""
    ref = max(6.0, float(reference))
    current_left = int(anchor_x)
    first_x = int(anchor_x)
    prefix_gap_limit = max(3, round(ref * 0.62))
    prefix_area_min = max(2, round(ref * ref * 0.0025))

    candidates = [item for item in components if int(item[1]) <= int(anchor_x)]
    for item in reversed(candidates):
        x0, x1, h, area = item
        # Ignore the structural anchor itself if component grouping reaches it.
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
    """Return the first visually meaningful text start in a line.

    ``anchor_x`` is the preferred trusted structural glyph reported by Page
    Design.  Residual specks far to its left are ignored.  Only nearby small
    components may extend the visual start leftward.  If no structural anchor
    exists, fall back to a stricter component-size search.
    """
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
