from __future__ import annotations

"""Compatibility shim for the retired Settings help post-build repair.

Canonical help wording now lives in ``ui.settings.schema``. The shared
``bind_help_widget`` helper recursively binds child controls, so the historical
SettingsDialog ``__init__`` wrapper is no longer required.
"""

from typing import Any


def install_settings_help_restore(app_module: Any) -> None:
    """Compatibility shim; Settings help ownership is static."""
    _ = app_module


__all__ = ["install_settings_help_restore"]
