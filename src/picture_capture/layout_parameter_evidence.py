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
    # All accepted Paddle-based paths use actual source text boxes. It does
    # not mean the value is *correct*, only that it was not fabricated.
    return "paddle" in method
