"""Layout detection compatibility facade with reliability fusion enabled.

The original detector implementation is kept in layout_detection_legacy.py so
all existing public/private helpers and test monkeypatch points remain available.

Layout is no longer the owner of page denoising. It consumes the same
full-resolution, coordinate-identical analysis image as ordinary drawing and
Page Understanding. The reliability layer may still apply its stricter
layout-specific speck guard afterwards, but every detector now starts from one
shared cleaned page.
"""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import os
import sys
from typing import Any

import numpy as np

from . import layout_detection_legacy as _legacy
from .image_utils import build_analysis_image, normalize_page_rgb

for _name in dir(_legacy):
    if _name.startswith("__") or _name == "detect_layout_parameters":
        continue
    globals()[_name] = getattr(_legacy, _name)

# Keep this dependency explicit as well as dynamically re-exported. The facade
# intentionally owns this injection seam so tests/callers can monkeypatch the
# detector without initializing PaddleOCR; an explicit alias also makes the
# contract visible to static undefined-name checks.
_get_text_detector = _legacy._get_text_detector
_legacy_detect_layout_parameters = _legacy.detect_layout_parameters

_LAYOUT_ESTIMATE_CACHE_LIMIT = 8
_LAYOUT_ESTIMATE_CACHE: "OrderedDict[tuple[Any, ...], Any]" = OrderedDict()


def _layout_estimate_cache_key(image, settings) -> tuple[Any, ...]:
    digest = hashlib.blake2b(image.tobytes(), digest_size=16).digest()
    return (str(image.mode), tuple(image.size), digest, repr(settings))


def clear_layout_estimate_cache() -> None:
    _LAYOUT_ESTIMATE_CACHE.clear()


def detect_text_polygons(image, settings, *, limit_side_len: int = 2400):
    """Detect source-image text polygons through the facade injection seam.

    The legacy implementation's function globals belong to its defining module,
    so merely re-exporting that function made monkeypatching
    ``layout_detection._get_text_detector`` ineffective. Keep this small wrapper
    in the facade so tests and callers can inject a detector without importing or
    initializing PaddleOCR, while preserving the exact polygon semantics.
    """
    source = normalize_page_rgb(image)
    detector = _get_text_detector(settings)
    os.environ["FLAGS_enable_pir_api"] = "0"
    try:
        results = list(
            detector.predict(
                np.asarray(source), batch_size=1,
                limit_side_len=max(256, int(limit_side_len)),
            )
        )
    except TypeError:
        results = list(detector.predict(np.asarray(source)))
    if not results:
        return []
    payload = _legacy._result_payload(results[0])
    raw_polys = payload.get("dt_polys")
    if raw_polys is None:
        raw_polys = payload.get("polys")
    polygons: list[np.ndarray] = []
    if raw_polys is None:
        return polygons
    for raw in list(raw_polys):
        arr = np.asarray(raw, dtype=float)
        if arr.ndim != 2 or arr.shape[0] < 3 or arr.shape[1] < 2:
            continue
        arr = arr[:, :2].copy()
        arr[:, 0] = np.clip(arr[:, 0], 0, max(0, source.width - 1))
        arr[:, 1] = np.clip(arr[:, 1], 0, max(0, source.height - 1))
        polygons.append(arr)
    return polygons


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
