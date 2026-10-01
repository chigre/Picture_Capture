from __future__ import annotations

"""Canonical settings names for the shared separator-Y refinement feature.

Y refinement is shared by ordinary Layout drawing, OCR drawing and the manual
PDIC Y-refine action.  The historical ``paddle_*`` names are therefore legacy
storage/runtime implementation details only.  This module exposes neutral
``separator_y_*`` names while keeping old projects loadable without changing
refinement behaviour.
"""

from dataclasses import asdict
import json
from pathlib import Path
import tempfile
from typing import Any

from .models import AppSettings


LEGACY_TO_CANONICAL: dict[str, str] = {
    "paddle_refine_separator_y": "separator_y_refine_enabled",
    "paddle_separator_search_ratio": "separator_y_search_ratio",
    "paddle_separator_band_radius": "separator_y_band_radius",
    "paddle_separator_safety_px": "separator_y_safety_px",
    "paddle_separator_roi_width_ratio": "separator_y_roi_width_ratio",
    "paddle_separator_column_margin": "separator_y_column_margin",
}

_INSTALLED = False
_ORIGINAL_FROM_JSON: Any | None = None


def _install_alias_properties() -> None:
    """Expose canonical runtime attributes backed by legacy dataclass slots."""
    for legacy, canonical in LEGACY_TO_CANONICAL.items():
        if hasattr(AppSettings, canonical):
            continue

        def getter(self: AppSettings, _legacy: str = legacy) -> Any:
            return getattr(self, _legacy)

        def setter(self: AppSettings, value: Any, _legacy: str = legacy) -> None:
            setattr(self, _legacy, value)

        setattr(AppSettings, canonical, property(getter, setter))


def _canonical_payload(settings: AppSettings) -> dict[str, Any]:
    payload = asdict(settings)
    for legacy, canonical in LEGACY_TO_CANONICAL.items():
        if legacy in payload:
            payload[canonical] = payload.pop(legacy)
    return payload


def _install_json_migration() -> None:
    """Write canonical keys and transparently read both old and new projects."""
    global _ORIGINAL_FROM_JSON
    if _ORIGINAL_FROM_JSON is not None:
        return

    original_from_json = AppSettings.from_json.__func__
    _ORIGINAL_FROM_JSON = original_from_json

    def to_json(self: AppSettings, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_canonical_payload(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def from_json(cls: type[AppSettings], path: Path) -> AppSettings:
        source = Path(path)
        raw = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return original_from_json(cls, source)

        translated = dict(raw)
        changed = False
        for legacy, canonical in LEGACY_TO_CANONICAL.items():
            if canonical in translated:
                # New canonical value wins if a hand-edited file contains both.
                translated[legacy] = translated[canonical]
                translated.pop(canonical, None)
                changed = True

        if not changed:
            return original_from_json(cls, source)

        # Reuse the mature AppSettings migration logic instead of duplicating
        # every historical project-version migration here.
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            encoding="utf-8",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(translated, handle, ensure_ascii=False)
        try:
            return original_from_json(cls, temp_path)
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass

    AppSettings.to_json = to_json  # type: ignore[method-assign]
    AppSettings.from_json = from_json  # type: ignore[method-assign]


def install_separator_y_settings() -> None:
    """Install the neutral public names exactly once."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_alias_properties()
    _install_json_migration()
    _INSTALLED = True


def canonical_separator_y_values(settings: AppSettings) -> dict[str, Any]:
    """Return the public separator-Y settings without legacy field names."""
    install_separator_y_settings()
    return {
        canonical: getattr(settings, canonical)
        for canonical in LEGACY_TO_CANONICAL.values()
    }


__all__ = [
    "LEGACY_TO_CANONICAL",
    "canonical_separator_y_values",
    "install_separator_y_settings",
]
