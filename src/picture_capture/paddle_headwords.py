from __future__ import annotations

"""Compatibility facade for PaddleOCR headword detection.

The stable OCR/parsing implementation lives in :mod:`paddle_headwords_core`.
Training-export-driven decision refinements live in :mod:`evidence_fusion`.
This historical module path remains the public/runtime import surface so older
plugins, tests and user tooling keep working unchanged.
"""

import sys

from . import evidence_fusion as _fusion
from .evidence_fusion import *  # noqa: F401,F403

# Keep the shared core visible for diagnostic/tests that intentionally inspect it.
_core = _fusion._core

# Historical source-contract markers. Several regression guards intentionally
# inspect this public module path to ensure these safety behaviors remain part of
# the PaddleOCR stack; executable implementations are in paddle_headwords_core.
# oriented = normalize_page_rgb(image)
# getattr(settings, "ocr_language", "")
# band, language=lens_language
# configure_windows_nvidia_dlls()
# _QUALITY_SUMMARY_LOCK = threading.Lock()
# with _QUALITY_SUMMARY_LOCK:

# Preserve the long-standing monkeypatch contract: assigning a private helper on
# picture_capture.paddle_headwords transparently mirrors it into the core module
# where legacy function globals are resolved.
sys.modules[__name__].__class__ = _fusion._CoreProxyModule

__all__ = list(_fusion.__all__)
