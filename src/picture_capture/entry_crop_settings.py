from __future__ import annotations

"""Neutral crop-height settings shared by OCR and proofreading.

Historical review-only names remain compatibility storage slots.  Runtime code
uses ``entry_regular_crop_height`` and ``entry_oversized_crop_height`` so crop
semantics follow entry classification rather than language or UI surface.
"""

from pathlib import Path
from typing import Any
import json
import tempfile

from .models import AppSettings

LEGACY_TO_CANONICAL = {
    "review_regular_crop_height": "entry_regular_crop_height",
    "review_single_cjk_line_height": "entry_oversized_crop_height",
}
CANONICAL_TO_LEGACY = {canonical: legacy for legacy, canonical in LEGACY_TO_CANONICAL.items()}
_INSTALLED = False


def install_entry_crop_settings() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_init = AppSettings.__init__
    original_to_json = AppSettings.to_json
    original_from_json = AppSettings.from_json.__func__

    def init(self: AppSettings, *args: Any, **kwargs: Any) -> None:
        translated = dict(kwargs)
        for canonical, legacy in CANONICAL_TO_LEGACY.items():
            if canonical in translated:
                translated[legacy] = translated.pop(canonical)
        original_init(self, *args, **translated)

    AppSettings.__init__ = init  # type: ignore[method-assign]

    for legacy, canonical in LEGACY_TO_CANONICAL.items():
        if hasattr(AppSettings, canonical):
            continue

        def getter(self: AppSettings, _legacy: str = legacy) -> Any:
            return getattr(self, _legacy)

        def setter(self: AppSettings, value: Any, _legacy: str = legacy) -> None:
            setattr(self, _legacy, value)

        setattr(AppSettings, canonical, property(getter, setter))

    def to_json(self: AppSettings, path: Path) -> None:
        # Let earlier migration layers (e.g. separator_y_*) serialize first,
        # then rewrite only these two legacy crop keys to their canonical names.
        original_to_json(self, path)
        target = Path(path)
        raw = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return
        for legacy, canonical in LEGACY_TO_CANONICAL.items():
            if legacy in raw:
                raw[canonical] = raw.pop(legacy)
        target.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

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
                translated[legacy] = translated.pop(canonical)
                changed = True
        if not changed:
            return original_from_json(cls, source)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", encoding="utf-8", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(translated, handle, ensure_ascii=False)
        try:
            return original_from_json(cls, temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    AppSettings.to_json = to_json  # type: ignore[method-assign]
    AppSettings.from_json = from_json  # type: ignore[method-assign]
    _INSTALLED = True


__all__ = [
    "CANONICAL_TO_LEGACY",
    "LEGACY_TO_CANONICAL",
    "install_entry_crop_settings",
]
