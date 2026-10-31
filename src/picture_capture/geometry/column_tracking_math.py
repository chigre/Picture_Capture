from __future__ import annotations

"""Column tracking math. Retains old core callables as forwarding patch points."""

from ..models import AppSettings


def _smooth_track(
    values: list[int], max_step: int, *, nominal_x: int | None = None,
) -> list[int]:
    """Robustly smooth one column-left track without walking into body text.

    A dictionary block can contain only indented definition lines. In that
    case its first-ink estimate is to the right of the true column edge. The
    old implementation clipped a large jump to max_step and therefore walked
    toward that false edge over several blocks. A five-block median suppresses
    short runs of indentation, and a jump beyond the allowed step is rejected
    instead of accumulated.
    """
    if not values:
        return []
    max_step = max(1, int(max_step))
    if len(values) == 1:
        value = int(values[0])
        if nominal_x is not None and abs(value - int(nominal_x)) > max_step:
            return [int(nominal_x)]
        return [value]

    median_filtered: list[int] = []
    for index, raw_candidate in enumerate(values):
        left = max(0, index - 2)
        right = min(len(values), index + 3)
        window = sorted(int(value) for value in values[left:right])
        # Preserve a genuine monotonic slope. The local median is used only to
        # replace a block that is an actual outlier; substituting the median for
        # every block would flatten the top/bottom of a real slanted column.
        local_median = window[(len(window) - 1) // 2]
        candidate = int(raw_candidate)
        if abs(candidate - local_median) > max_step:
            candidate = int(local_median)
        median_filtered.append(candidate)

    # Seed from the actual first block rather than its forward-looking median;
    # this preserves a genuine gradual slope at the top of the page. The
    # nominal start still rejects a first block that is already an implausible
    # rightward indentation.
    start = int(values[0])
    if nominal_x is not None and abs(start - int(nominal_x)) > max_step:
        start = int(nominal_x)

    stable = [start]
    for candidate in median_filtered[1:]:
        previous = stable[-1]
        if abs(int(candidate) - previous) <= max_step:
            stable.append(int(candidate))
        else:
            # Holding is deliberate: clipping toward an implausible candidate
            # lets several body-only blocks accumulate into a fake curve.
            stable.append(previous)
    return stable


def _column_tracking_dimensions(
    column_width: int,
    body_height: int,
    settings: AppSettings,
) -> tuple[int, int, int]:
    """Resolve relative column-following controls to current-page pixels.

    Returns (search_radius, block_height, max_step) in the same analysis
    coordinate space as the supplied dimensions.
    """
    radius_percent = max(
        0.1, min(50.0, float(getattr(settings, "column_track_radius", 5.0) or 5.0))
    )
    block_height_percent = max(
        0.1, min(25.0, float(getattr(settings, "column_track_block_height", 3.0) or 3.0))
    )
    max_slope_percent = max(
        0.1, min(50.0, float(getattr(settings, "column_track_max_step", 8.0) or 8.0))
    )
    radius = max(8, round(max(1, int(column_width)) * radius_percent / 100.0))
    block_height = max(
        30, round(max(1, int(body_height)) * block_height_percent / 100.0)
    )
    max_step = max(1, round(block_height * max_slope_percent / 100.0))
    return radius, block_height, max_step

