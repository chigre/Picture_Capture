from __future__ import annotations

"""Literal-pixel per-column nudges and stable physical column ordering.

Historical core entrypoints retain override hooks and Geometry/pickle owners;
no persisted settings schema, ColumnPath, or Geometry class moves here.
"""

from collections.abc import Callable
from ..models import AppSettings


def column_start_offsets_canonical(
    settings: AppSettings, count: int, canonical_width: int, *,
    source_px_fn: Callable[[float], int],
) -> list[int]:
    """Resolve persisted per-column nudges into current-page canonical pixels."""
    raw = list(getattr(settings, "column_start_offsets", []) or [])
    resolved: list[int] = []
    for index in range(max(0, int(count))):
        try:
            value = float(raw[index]) if index < len(raw) else 0.0
        except (TypeError, ValueError):
            value = 0.0
        resolved.append(
            source_px_fn(value)
        )
    return resolved


def apply_column_start_offsets(
    base_starts: list[int], offsets: list[int], *, gutter: int, max_x: int,
) -> list[int]:
    """Apply independent column-left nudges while preserving usable column order."""
    if not base_starts:
        return []
    limit = max(0, int(max_x))
    starts = [
        max(0, min(limit, int(base) + (int(offsets[i]) if i < len(offsets) else 0)))
        for i, base in enumerate(base_starts)
    ]
    # Keep enough room for the configured gutter plus a minimal usable body band.
    # Normal small corrections are unchanged; only pathological/corrupt offsets
    # are clipped so columns can never cross each other.
    min_step = max(11, max(0, int(gutter)) + 10)
    for _ in range(2):
        for index in range(1, len(starts)):
            starts[index] = max(starts[index], starts[index - 1] + min_step)
        starts[-1] = min(limit, starts[-1])
        for index in range(len(starts) - 2, -1, -1):
            starts[index] = min(starts[index], starts[index + 1] - min_step)
        starts[0] = max(0, starts[0])
    return [max(0, min(limit, int(value))) for value in starts]
