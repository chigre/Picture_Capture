from __future__ import annotations

"""OCR-assisted headword-boundary consumer.

OCR recognition is a shared channel (:mod:`picture_capture.ocr_channel`).  This
module is the *consumer* that borrows those OCR sources to infer dictionary
headword boundaries.  Keeping the consumer separate is important: running OCR
on existing markers must not implicitly run, depend on, or mutate boundary
placement logic.

The mature parser/arbitration implementation still lives behind
``evidence_fusion.detect_paddle_headwords``.  Historical ``paddle_*`` setting
translation is isolated in :mod:`picture_capture.ocr_channel_legacy`; this
consumer therefore depends only on the shared OCR-channel contract plus the
stable parser backend.
"""

from pathlib import Path
from typing import Any

from PIL import Image

from .models import AppSettings
from .ocr_channel_legacy import apply_channel_plan_to_legacy_boundary_settings


def detect_ocr_headword_boundaries(
    image: Image.Image,
    geometry: Any,
    settings: AppSettings,
    *,
    cache_path: Path | None = None,
    force_refresh: bool = False,
    filter_rules_path: Path | None = None,
    page_sections=None,
):
    """Borrow shared OCR-channel evidence to infer separator positions.

    OCR engine selection belongs to the channel.  This consumer owns only the
    meaning of those OCR results for headword parsing and separator generation.
    It intentionally returns the established ``Entry`` output of the mature OCR
    drawing pipeline while the compatibility adapter keeps legacy fields out of
    this module.
    """

    from .evidence_fusion import detect_paddle_headwords as legacy_detect

    return legacy_detect(
        image,
        geometry,
        apply_channel_plan_to_legacy_boundary_settings(settings),
        cache_path=cache_path,
        force_refresh=force_refresh,
        filter_rules_path=filter_rules_path,
        page_sections=page_sections,
    )


__all__ = ["detect_ocr_headword_boundaries"]
