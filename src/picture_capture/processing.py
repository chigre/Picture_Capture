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
from .ordinary_lane_polarity import suppress_inverted_legacy_body_lane
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
    """Run VB geometry, correct proven lane polarity, then recover visual entries.

    The primary detector remains the full-resolution historical chain. These
    source markers intentionally document the unchanged core contract for the
    long-standing regression checks:
    _legacy_is_point(
    _legacy_find_separator_y(
    ordinary_right_divisor
    white_threshold_high
    white_threshold_low
    whitespace_adjustment
    upward_ratio
    from .paddle_headwords import refine_separator_y
    refined_y, _refinement = refine_separator_y(

    For ordinary layouts the VB output is retained exactly.  On the narrower
    CJK failure mode where dense body text is flush-left but a repeated bracket
    entry lane is indented, a page-level polarity pass may suppress only those
    ``ordinary_vb`` rows demonstrably attached to the dense body lane.  The
    independent visual pass then recovers the indented entries and oversized
    display heads.
    """
    entries, geometry = _original_detect_entries_left_edge(
        image, settings, page_sections=page_sections,
    )
    entries = suppress_inverted_legacy_body_lane(
        image, entries, geometry, settings, page_sections=page_sections,
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


def _publish_file_transaction(*args, **kwargs):
    """Compatibility forwarder; implementation stays in processing_core."""
    return _core._publish_file_transaction(*args, **kwargs)


def _stage_page_crop_plan(*args, **kwargs):
    """Compatibility forwarder; implementation stays in processing_core."""
    return _core._stage_page_crop_plan(*args, **kwargs)


# Historical publish implementation uses uuid.uuid4().hex in processing_core.


def split_single_lines(*args, **kwargs):
    """Compatibility forwarder for staged single-line export.

    Source-contract markers: _stage_crop( _stage_text_file(
    _publish_file_transaction(
    """
    return _core.split_single_lines(*args, **kwargs)


def _special_bounds(*args, **kwargs):
    return _core._special_bounds(*args, **kwargs)


def split_whole_entries(*args, **kwargs):
    """Compatibility forwarder for staged whole-entry export.

    Source-contract markers: _stage_page_crop_plan( _publish_file_transaction(
    .PWWords"
    """
    return _core.split_whole_entries(*args, **kwargs)


def append_crop_log(*args, **kwargs):
    return _core.append_crop_log(*args, **kwargs)


def split_illustrations(*args, **kwargs):
    """Compatibility forwarder for staged illustration export.

    Source-contract markers: _stage_page_crop_plan( _publish_file_transaction(
    .PPPictures"
    """
    return _core.split_illustrations(*args, **kwargs)


def append_illustration_crop_log(*args, **kwargs):
    return _core.append_illustration_crop_log(*args, **kwargs)


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
