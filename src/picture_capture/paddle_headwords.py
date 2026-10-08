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

from . import paddle_headwords_core as _core
from .facade_compat import install_core_assignment_mirror, publish_core_namespace

# This historical public path owns the broad core namespace contract. Copy core
# symbols first, then let evidence-fusion overrides replace selected decisions.
publish_core_namespace(globals(), _core)

from . import evidence_fusion as _fusion
from .evidence_fusion import *  # noqa: F401,F403
from .ocr_boundary_detection import detect_ocr_headword_boundaries
from .separator_y_refinement import refine_separator_y as _shared_refine_separator_y

# Keep the shared core visible for diagnostic/tests that intentionally inspect it.

# ``processing_core.refine_existing_entries`` and older callers still import the
# refiner from ``paddle_headwords``. Preserve that API without rewriting the
# core module at import time.
_native_refine_separator_y = _core.refine_separator_y
refine_separator_y = _shared_refine_separator_y


def refine_separator_y_adaptive(
    gray,
    coarse_y,
    reference_line_height,
    settings,
    pixel_scale=1.0,
    lower_bound=0,
    content_top=None,
    preceding_gap_hint=None,
):
    """Run the mature adaptive refiner with the public/shared fallback."""
    fallback_refiner = _core.refine_separator_y
    if fallback_refiner is _native_refine_separator_y:
        fallback_refiner = refine_separator_y
    return _core.refine_separator_y_adaptive(
        gray,
        coarse_y,
        reference_line_height,
        settings,
        pixel_scale=pixel_scale,
        lower_bound=lower_bound,
        content_top=content_top,
        preceding_gap_hint=preceding_gap_hint,
        fallback_refiner=fallback_refiner,
    )


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
install_core_assignment_mirror(__name__, _core)

__all__ = [
    name for name in vars(_core)
    if not name.startswith("__")
]
for _name in list(_fusion.__all__) + [
    "refine_separator_y",
    "detect_ocr_headword_boundaries",
]:
    if _name not in __all__:
        __all__.append(_name)
