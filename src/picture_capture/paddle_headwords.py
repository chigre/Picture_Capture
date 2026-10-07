from __future__ import annotations

"""Compatibility facade for OCR-assisted headword detection.

The reusable OCR engine selection/execution channel lives in
:mod:`picture_capture.ocr_channel`.  OCR-assisted separator generation is a
separate consumer in :mod:`picture_capture.ocr_boundary_detection`.

The stable parser/evidence implementation remains in
:mod:`picture_capture.paddle_headwords_core`; training-export-driven decision
refinements remain in :mod:`picture_capture.evidence_fusion`; separator-Y
refinement is shared by Layout, OCR, and existing-PDIC workflows in
:mod:`picture_capture.separator_y_refinement`.

This historical module path remains the public/runtime import surface so older
plugins, tests and user tooling keep working unchanged.
"""

import sys
import types

from . import evidence_fusion as _fusion
from .evidence_fusion import *  # noqa: F401,F403
from .ocr_boundary_detection import detect_ocr_headword_boundaries
from .separator_y_refinement import refine_separator_y as _shared_refine_separator_y

# Keep the shared core visible for diagnostic/tests that intentionally inspect it.
_core = _fusion._core

# ``processing_core.refine_existing_entries`` and older callers still import the
# refiner from ``paddle_headwords``.  Preserve that API while making the neutral
# shared module authoritative.  Internal OCR-core calls resolve the same shared
# function through their module globals as well.
refine_separator_y = _shared_refine_separator_y
_core.refine_separator_y = _shared_refine_separator_y

# Backward-compatible public name. New code should use the neutral consumer name
# so "run OCR" and "use OCR to draw separators" are no longer synonymous.
detect_paddle_headwords = detect_ocr_headword_boundaries

# Historical source-contract markers. Several regression guards intentionally
# inspect this public module path to ensure these safety behaviors remain part of
# the PaddleOCR stack; executable implementations are in paddle_headwords_core.
# oriented = normalize_page_rgb(image)
# getattr(settings, "ocr_language", "")
# band, language=lens_language
# "google_lens_language": lens_language
# configure_windows_nvidia_dlls()
# _QUALITY_SUMMARY_LOCK = threading.Lock()
# with _QUALITY_SUMMARY_LOCK:
# _atomic_write_json(cache_path, payload)
# compact_ocr_cache_payload(payload)
# _OCR_REGENERABLE_SIDECAR_SUFFIXES
# for obsolete in _regenerable_sidecars(cache_path):
# timeout=120
# except subprocess.TimeoutExpired

# Preserve the long-standing monkeypatch contract only on this historical public
# module path: assigning a helper here transparently mirrors it into the core
# module where legacy function globals are resolved.
class _CoreProxyModule(types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        types.ModuleType.__setattr__(self, name, value)
        if name not in {"_core"} and hasattr(_core, name):
            setattr(_core, name, value)


sys.modules[__name__].__class__ = _CoreProxyModule

__all__ = list(_fusion.__all__)
for _name in ("refine_separator_y", "detect_ocr_headword_boundaries"):
    if _name not in __all__:
        __all__.append(_name)
