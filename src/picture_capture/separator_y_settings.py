from __future__ import annotations

"""Canonical separator-Y names backed statically by AppSettings legacy slots."""

from typing import Any

from .app_settings_migrations import SEPARATOR_Y_LEGACY_TO_CANONICAL
from .models import AppSettings


LEGACY_TO_CANONICAL: dict[str, str] = dict(SEPARATOR_Y_LEGACY_TO_CANONICAL)
CANONICAL_TO_LEGACY: dict[str, str] = {
    canonical: legacy for legacy, canonical in LEGACY_TO_CANONICAL.items()
}


def install_separator_y_settings() -> None:
    """Compatibility no-op; AppSettings owns aliases and migration statically."""
    return None


def canonical_separator_y_values(settings: AppSettings) -> dict[str, Any]:
    """Return the public separator-Y settings without legacy field names."""
    return {
        canonical: getattr(settings, canonical)
        for canonical in LEGACY_TO_CANONICAL.values()
    }


__all__ = [
    "CANONICAL_TO_LEGACY",
    "LEGACY_TO_CANONICAL",
    "canonical_separator_y_values",
    "install_separator_y_settings",
]
