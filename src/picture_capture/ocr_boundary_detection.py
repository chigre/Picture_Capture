from __future__ import annotations

"""OCR-assisted headword-boundary consumer.

OCR recognition is a shared channel (:mod:`picture_capture.ocr_channel`).  This
module is the *consumer* that borrows those OCR sources to infer dictionary
headword boundaries.  Keeping the consumer separate is important: running OCR
on existing markers must not implicitly run, depend on, or mutate boundary
placement logic.

The mature parser/arbitration implementation still lives behind
``evidence_fusion.detect_paddle_headwords``.  This adapter makes the shared OCR
channel plan authoritative before entering that stable implementation and gives
new callers a neutral function name.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any

from PIL import Image

from .models import AppSettings
from .ocr_channel import resolve_ocr_channel_plan


def _settings_for_boundary_consumer(settings: AppSettings) -> AppSettings:
    """Translate the shared channel plan into legacy core compatibility fields."""

    routed = replace(settings)
    plan = resolve_ocr_channel_plan(settings)

    routed.paddle_use_paddleocr = plan.enabled("paddle")
    if not plan.enabled("tesseract"):
        routed.paddle_compare_tesseract = False
        routed.paddle_tesseract_rescue = False
        routed.paddle_dual_ocr_arbitration = False
    elif not (
        bool(getattr(routed, "paddle_compare_tesseract", False))
        or bool(getattr(routed, "paddle_tesseract_rescue", False))
    ):
        # Channel selection says Tesseract is enabled, but an older/non-GUI
        # caller may not have populated the historical mode flags.
        routed.paddle_compare_tesseract = True

    routed.paddle_enable_lens = plan.enabled("lens")
    routed.paddle_lens_mode = plan.lens_mode if plan.enabled("lens") else "off"
    return routed


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
    """Use shared OCR-channel evidence to infer headword separator positions.

    This function intentionally returns the established ``Entry`` output of the
    mature OCR drawing pipeline.  The recognition channel itself is reusable and
    has no dependency on separator placement.
    """

    from .evidence_fusion import detect_paddle_headwords as legacy_detect

    return legacy_detect(
        image,
        geometry,
        _settings_for_boundary_consumer(settings),
        cache_path=cache_path,
        force_refresh=force_refresh,
        filter_rules_path=filter_rules_path,
        page_sections=page_sections,
    )


__all__ = [
    "detect_ocr_headword_boundaries",
]
