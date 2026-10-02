from __future__ import annotations

"""Prevent long projection bands from disappearing during Layout row recovery.

The physical-indent runtime first tries to split tall active projection runs at
real horizontal valleys.  When no sufficiently deep valley is found it falls
back to ``_logical_slots_for_oversized_run``.  Historically that fallback capped
one continuous run at four logical slots.  A run taller than roughly 7.6 line
heights therefore produced four still-oversized slots, all of which were then
rejected by ``projection_line_runs``.  Dense dictionary columns could lose an
entire stretch of rows before indent measurement even started.

This adapter changes only that last-resort fallback.  Normal runs and successful
valley splits are untouched.  The fallback now chooses enough slots to keep each
logical row near the configured/reference line height, with a generous hard cap
solely to guard corrupt geometry.
"""

import math
from typing import Any

import numpy as np


def logical_slots_without_loss(
    y0: int,
    y1: int,
    reference: float,
) -> list[tuple[int, int]]:
    """Split one unresolved tall band without silently discarding long spans."""
    start = int(y0)
    stop = int(y1)
    height = max(0, stop - start)
    ref = max(6.0, float(reference))
    if height < ref * 1.55:
        return [(start, stop)] if stop > start else []

    # The downstream acceptance window is <= 1.90 * ref.  Ensure the fallback
    # creates enough slots to satisfy that contract even for a very long band.
    by_reference = max(2, int(round(height / ref)))
    by_maximum_height = max(2, int(math.ceil(height / (ref * 1.90))))
    count = max(by_reference, by_maximum_height)

    # A normal 4600px dictionary page with ~35-60px text height stays well below
    # this.  The cap prevents pathological/corrupt inputs from allocating an
    # unbounded number of slots while still allowing whole-page dense bands.
    count = min(256, count)

    # If the hard cap was ever reached, make sure the produced slot height still
    # honours the downstream maximum; otherwise retain the original band rather
    # than manufacture slots that would immediately be discarded again.
    if height / float(count) > ref * 1.90:
        return [(start, stop)]

    edges = np.linspace(float(start), float(stop), count + 1)
    slots: list[tuple[int, int]] = []
    for index in range(count):
        a = int(round(edges[index]))
        b = int(round(edges[index + 1]))
        if b > a:
            slots.append((a, b))
    return slots or ([(start, stop)] if stop > start else [])


def install_layout_row_recovery_runtime() -> None:
    """Patch the physical-indent fallback before Layout Core analyses a page."""
    from . import layout_physical_indent as physical

    if bool(getattr(physical, "_long_band_row_recovery_installed", False)):
        return
    physical._logical_slots_for_oversized_run = logical_slots_without_loss
    physical._long_band_row_recovery_installed = True


__all__ = [
    "install_layout_row_recovery_runtime",
    "logical_slots_without_loss",
]
