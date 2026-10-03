"""Layout detection compatibility facade with reliability fusion enabled.

The original detector implementation is kept in layout_detection_legacy.py so
all existing public/private helpers and test monkeypatch points remain available.

Layout is no longer the owner of page denoising.  It consumes the same
full-resolution, coordinate-identical analysis image as ordinary drawing and
Page Understanding.  The reliability layer may still apply its stricter
layout-specific speck guard afterwards, but every detector now starts from one
shared cleaned page.
"""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import sys
from typing import Any

from . import layout_detection_legacy as _legacy
from .image_utils import build_analysis_image

for _name in dir(_legacy):
    if _name.startswith("__") or _name == "detect_layout_parameters":
        continue
    globals()[_name] = getattr(_legacy, _name)

_legacy_detect_layout_parameters = _legacy.detect_layout_parameters

_LAYOUT_ESTIMATE_CACHE_LIMIT = 8
_LAYOUT_ESTIMATE_CACHE: "OrderedDict[tuple[Any, ...], Any]" = OrderedDict()


def _layout_estimate_cache_key(image, settings) -> tuple[Any, ...]:
    digest = hashlib.blake2b(image.tobytes(), digest_size=16).digest()
    return (str(image.mode), tuple(image.size), digest, repr(settings))


def clear_layout_estimate_cache() -> None:
    _LAYOUT_ESTIMATE_CACHE.clear()


def detect_layout_parameters(image, settings):
    from .layout_reliability import detect_layout_parameters_reliable

    analysis_image = build_analysis_image(image, settings)
    key = _layout_estimate_cache_key(analysis_image, settings)
    cached = _LAYOUT_ESTIMATE_CACHE.get(key)
    if cached is not None:
        _LAYOUT_ESTIMATE_CACHE.move_to_end(key)
        return cached

    result = detect_layout_parameters_reliable(
        analysis_image, settings, sys.modules[__name__]
    )
    _LAYOUT_ESTIMATE_CACHE[key] = result
    _LAYOUT_ESTIMATE_CACHE.move_to_end(key)
    while len(_LAYOUT_ESTIMATE_CACHE) > _LAYOUT_ESTIMATE_CACHE_LIMIT:
        _LAYOUT_ESTIMATE_CACHE.popitem(last=False)
    return result


# Historical source-contract markers retained for compatibility tests/tools.
# Executable implementations live in layout_detection_legacy.py and are
# re-exported by this facade; the current reliable detector still starts from
# alpha-safe normalized RGB and configures Windows NVIDIA DLLs in that backend.
# source = normalize_page_rgb(image)
# configure_windows_nvidia_dlls()
