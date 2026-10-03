from __future__ import annotations

"""Neutral entry-crop settings shared by OCR and proofreading.

Historical review height names remain compatibility storage slots.  The
user-visible ``right_ratio`` is the canonical width control for existing-entry
boxes and marker OCR crops.  Paddle's ``paddle_band_width_ratio`` remains an
independent OCR-detector setting and must never be repurposed for marker crops.
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
CANONICAL_TO_LEGACY = {
    canonical: legacy for legacy, canonical in LEGACY_TO_CANONICAL.items()
}
_TRANSIENT_OCR_RIGHT_RATIO = "entry_ocr_right_ratio"
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

        # A few intermediate builds persisted this temporary name.  Preserve its
        # value for compatibility, but the established visible ``right_ratio``
        # wins whenever both are supplied.
        transient_ratio = translated.pop(_TRANSIENT_OCR_RIGHT_RATIO, None)
        if transient_ratio is not None and "right_ratio" not in translated:
            translated["right_ratio"] = transient_ratio

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

    # Compatibility-only API for code/configuration produced by the short-lived
    # split setting. Runtime code must read ``right_ratio`` directly.
    if not hasattr(AppSettings, _TRANSIENT_OCR_RIGHT_RATIO):
        def get_transient_ratio(self: AppSettings) -> Any:
            return getattr(self, "right_ratio")

        def set_transient_ratio(self: AppSettings, value: Any) -> None:
            setattr(self, "right_ratio", value)

        setattr(
            AppSettings,
            _TRANSIENT_OCR_RIGHT_RATIO,
            property(get_transient_ratio, set_transient_ratio),
        )

    def to_json(self: AppSettings, path: Path) -> None:
        # Let earlier migration layers serialize first, then expose neutral height
        # names. Width persists under the long-established ``right_ratio`` key;
        # Paddle's band ratio is deliberately left untouched.
        original_to_json(self, path)
        target = Path(path)
        raw = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return
        for legacy, canonical in LEGACY_TO_CANONICAL.items():
            if legacy in raw:
                raw[canonical] = raw.pop(legacy)
        raw.pop(_TRANSIENT_OCR_RIGHT_RATIO, None)
        target.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
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

        # Migrate only the temporary marker-crop width key.  Never interpret
        # paddle_band_width_ratio as the visible marker-crop right ratio.
        if _TRANSIENT_OCR_RIGHT_RATIO in translated:
            transient_ratio = translated.pop(_TRANSIENT_OCR_RIGHT_RATIO)
            translated.setdefault("right_ratio", transient_ratio)
            changed = True

        for legacy, canonical in LEGACY_TO_CANONICAL.items():
            if canonical in translated:
                translated[legacy] = translated.pop(canonical)
                changed = True

        if not changed:
            return original_from_json(cls, source)

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
            temp_path.unlink(missing_ok=True)

    AppSettings.to_json = to_json  # type: ignore[method-assign]
    AppSettings.from_json = from_json  # type: ignore[method-assign]
    _INSTALLED = True


__all__ = [
    "CANONICAL_TO_LEGACY",
    "LEGACY_TO_CANONICAL",
    "install_entry_crop_settings",
]
