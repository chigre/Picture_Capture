from __future__ import annotations

"""Canonical entry-crop names backed statically by AppSettings legacy slots."""

from .app_settings_migrations import (
    ENTRY_CROP_LEGACY_TO_CANONICAL,
    TRANSIENT_ENTRY_OCR_RIGHT_RATIO,
)


LEGACY_TO_CANONICAL = dict(ENTRY_CROP_LEGACY_TO_CANONICAL)
CANONICAL_TO_LEGACY = {
    canonical: legacy for legacy, canonical in LEGACY_TO_CANONICAL.items()
}
_TRANSIENT_OCR_RIGHT_RATIO = TRANSIENT_ENTRY_OCR_RIGHT_RATIO


def install_entry_crop_settings() -> None:
    """Compatibility no-op; AppSettings owns aliases and migration statically."""
    return None


__all__ = [
    "CANONICAL_TO_LEGACY",
    "LEGACY_TO_CANONICAL",
    "install_entry_crop_settings",
]
