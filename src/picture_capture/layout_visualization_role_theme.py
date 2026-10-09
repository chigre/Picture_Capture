from __future__ import annotations

"""Compatibility entry point for the now-static Layout role theme."""

from .layout_visualization_summary import BODY_ROLE_COLOR, ENTRY_ROLE_COLOR


def install_layout_role_theme() -> None:
    """Compatibility no-op; the red/blue role theme is statically owned."""
    return None


__all__ = ["ENTRY_ROLE_COLOR", "BODY_ROLE_COLOR", "install_layout_role_theme"]
