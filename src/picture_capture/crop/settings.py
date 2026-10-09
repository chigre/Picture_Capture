from __future__ import annotations

"""Persistence contract for shared crop settings.

This module is deliberately UI-free. Both the main application and crop dialogs
use the same version/normalization contract without depending on one another.
"""

from ..coordinate_space import SOURCE_COORDINATE_SPACE
from ..models import AppSettings


CROP_SETTINGS_VERSION = 7
SINGLE_LINE_MERGE_KEY = "single_line_crop_merge_by_page"


def normalize_crop_settings_payload(
    raw: dict | None,
    settings: AppSettings,
) -> dict:
    """Read crop settings only when they already use original-image X/Y."""
    default_bottom = int(settings.bottom_y) if settings.crop_to_bottom_y else 0
    defaults = {
        "version": CROP_SETTINGS_VERSION,
        "coordinate_space": SOURCE_COORDINATE_SPACE,
        "general_top_y": int(settings.start_y),
        "general_bottom_y": default_bottom,
        "entry_left_padding_x": 0,
        "entry_right_padding_x": 0,
        "integrate_illustrations": True,
        "polygon_margin": 0,
        "parallel_workers": int(settings.crop_parallel_workers),
        SINGLE_LINE_MERGE_KEY: False,
        "special_pages": {},
    }
    if not isinstance(raw, dict):
        return defaults
    if int(raw.get("version", 0) or 0) != CROP_SETTINGS_VERSION:
        return defaults
    if str(raw.get("coordinate_space") or "") != SOURCE_COORDINATE_SPACE:
        return defaults

    result = dict(defaults)
    for key in (
        "general_top_y", "general_bottom_y",
        "entry_left_padding_x", "entry_right_padding_x",
        "polygon_margin", "parallel_workers",
    ):
        try:
            result[key] = max(0, int(raw.get(key, result[key]) or 0))
        except (TypeError, ValueError):
            pass
    result["integrate_illustrations"] = bool(raw.get("integrate_illustrations", True))
    result[SINGLE_LINE_MERGE_KEY] = bool(raw.get(SINGLE_LINE_MERGE_KEY, False))
    specials = raw.get("special_pages")
    if isinstance(specials, dict):
        cleaned: dict[str, dict[str, int]] = {}
        for page, values in specials.items():
            if not isinstance(values, dict):
                continue
            try:
                top = max(0, int(values.get("top_y", 0) or 0))
                bottom = max(0, int(values.get("bottom_y", 0) or 0))
            except (TypeError, ValueError):
                continue
            cleaned[str(page)] = {"top_y": top, "bottom_y": bottom}
        result["special_pages"] = cleaned
    return result


__all__ = [
    "CROP_SETTINGS_VERSION",
    "SINGLE_LINE_MERGE_KEY",
    "normalize_crop_settings_payload",
]
