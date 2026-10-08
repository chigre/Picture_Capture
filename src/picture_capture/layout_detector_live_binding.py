from __future__ import annotations

"""Backward-compatible import path for the retired Layout detector installer.

Page Layout now resolves layout_detection.detect_layout_parameters through a
static call-time forwarder owned by dictionary_page_layout_policy. The
historical installer name remains importable for diagnostics/plugins that may
still reference it, but it no longer mutates another module.
"""


def install_live_layout_detector_binding() -> None:
    """Compatibility no-op; the live binding is now static in Page Layout."""
    return None


__all__ = ["install_live_layout_detector_binding"]
