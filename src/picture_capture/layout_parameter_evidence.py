"""Provenance gates for geometry fields returned by the Layout estimator.

The OCR-free projection backend provides useful page/column geometry but its
row_padding is a literal one-pixel placeholder, not an observation of leading.
A successful estimation API call must not make that placeholder authoritative.
"""
from __future__ import annotations

from typing import Any


def row_padding_is_measured(estimate: Any) -> bool:
    """Return whether an estimate has actual text-box row-spacing evidence."""
    method = str(getattr(estimate, "method", "") or "").lower()
    # The projected path hardcodes row_padding=1 and estimates character
    # height from page size. A multi-page median of these numbers is still not
    # measurement evidence.
    if method.startswith("profile_bootstrap+"):
        return False
    if method.startswith("reliable_fusion+projection_only"):
        return False
    if method == "projection_fallback":
        return False
    # Merely executing Paddle is insufficient: interleaved columns or sparse
    # pages can leave this field unmeasured. Require explicit per-column pitch
    # provenance from the fixed text-box estimator. The bare method below is
    # retained only for older test/adaptor contracts.
    if "+unverified_row_padding" in method:
        return False
    return "+observed_row_padding=" in method or method == "reliable_fusion"


def verified_multi_page_row_padding(estimates: list[Any]) -> tuple[int | None, int]:
    """Median over genuinely measured text-box spacing, with coverage gate."""
    import statistics

    measured = [
        max(1, int(item.row_padding))
        for item in estimates
        if row_padding_is_measured(item)
    ]
    required = max(1, (len(estimates) + 1) // 2)
    if len(measured) < required:
        return None, len(measured)
    return round(statistics.median(measured)), len(measured)
