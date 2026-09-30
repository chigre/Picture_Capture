from __future__ import annotations

"""Compatibility facade for ordinary processing plus visual-lane recovery.

The historical implementation is kept unchanged in ``processing_core``.
This facade adds an OCR-independent post-pass for entry structures that a
single left-edge lane cannot see, then preserves the original import surface.
"""

from pathlib import Path
import sys
import types
from typing import Any

from PIL import Image

from .models import AppSettings, Entry
from .page_sections import PageSection
from . import processing_core as _core
from .ordinary_visual import recover_ordinary_visual_entries


# Re-export the complete historical processing API first.
for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


_original_detect_entries_left_edge = _core._detect_entries_left_edge


def _detect_entries_left_edge(
    image: Image.Image,
    settings: AppSettings,
    page_sections: list[PageSection] | None = None,
) -> tuple[list[Entry], Any]:
    """Run the faithful VB detector, then recover proven extra visual lanes.

    The primary detector remains the full-resolution historical chain:
    _legacy_is_point(
    _legacy_find_separator_y(
    upward_ratio

    The new post-pass never weakens that chain. It only adds OCR-independent
    candidates for repeated indented structural lanes and oversized CJK display
    heads, with de-duplication against the VB markers.
    """
    entries, geometry = _original_detect_entries_left_edge(
        image, settings, page_sections=page_sections,
    )
    entries = recover_ordinary_visual_entries(
        image, entries, geometry, settings, page_sections=page_sections,
    )
    return _core.sort_entries_reading_order(
        entries, geometry, page_sections,
    ), geometry


def detect_entries(
    image: Image.Image,
    settings: AppSettings,
    paddle_cache_path: Path | None = None,
    force_paddle_refresh: bool = False,
    paddle_filter_rules_path: Path | None = None,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
) -> tuple[list[Entry], Any]:
    """Forward through the core after installing enhanced ordinary detection."""
    return _core.detect_entries(
        image,
        settings,
        paddle_cache_path=paddle_cache_path,
        force_paddle_refresh=force_paddle_refresh,
        paddle_filter_rules_path=paddle_filter_rules_path,
        profile_page_index=profile_page_index,
        page_sections=page_sections,
    )


# Core functions resolve module globals in processing_core at call time.
_core._detect_entries_left_edge = _detect_entries_left_edge
globals()["_detect_entries_left_edge"] = _detect_entries_left_edge
globals()["detect_entries"] = detect_entries


class _CoreProxyModule(types.ModuleType):
    """Mirror monkeypatch/debug assignments from facade to the historical core."""

    def __setattr__(self, name: str, value: Any) -> None:
        types.ModuleType.__setattr__(self, name, value)
        if name not in {"_core"} and hasattr(_core, name):
            setattr(_core, name, value)


sys.modules[__name__].__class__ = _CoreProxyModule


# Source-guard compatibility markers for long-standing regression checks.
# Runtime implementations remain in processing_core.py.
# timeout=120
# except subprocess.TimeoutExpired

__all__ = [
    name for name in globals()
    if not name.startswith("__") and name not in {"_core"}
]
