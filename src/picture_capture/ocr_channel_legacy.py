from __future__ import annotations

"""Compatibility adapter between the shared OCR channel and the legacy parser core.

New OCR consumers must use :mod:`picture_capture.ocr_channel` directly.  The
mature headword parser still persists a number of historical ``paddle_*`` flags;
this module is the only place where the neutral channel plan is translated back
into those fields for that legacy backend.

Keeping this translation isolated prevents 【仅OCR】, future proofreading OCR,
and the OCR-assisted boundary consumer from each re-implementing engine
selection rules.
"""

from dataclasses import replace

from .models import AppSettings
from .ocr_channel import OcrChannelPlan, resolve_ocr_channel_plan


def apply_channel_plan_to_legacy_boundary_settings(
    settings: AppSettings,
    plan: OcrChannelPlan | None = None,
) -> AppSettings:
    """Return a copy whose legacy OCR flags mirror one resolved channel plan.

    This is deliberately a one-way compatibility translation.  The historical
    flags are not authoritative here; :func:`resolve_ocr_channel_plan` remains
    the single runtime selection policy.
    """

    routed = replace(settings)
    resolved = plan or resolve_ocr_channel_plan(settings)

    routed.paddle_use_paddleocr = resolved.enabled("paddle")

    if resolved.enabled("tesseract"):
        if not (
            bool(getattr(routed, "paddle_compare_tesseract", False))
            or bool(getattr(routed, "paddle_tesseract_rescue", False))
        ):
            # Older/non-GUI callers may select Tesseract only through the
            # neutral channel fallback.  The legacy parser needs one of its
            # historical switches enabled in order to execute that source.
            routed.paddle_compare_tesseract = True
    else:
        routed.paddle_compare_tesseract = False
        routed.paddle_tesseract_rescue = False
        routed.paddle_dual_ocr_arbitration = False

    routed.paddle_enable_lens = resolved.enabled("lens")
    routed.paddle_lens_mode = (
        resolved.lens_mode if resolved.enabled("lens") else "off"
    )
    return routed


__all__ = ["apply_channel_plan_to_legacy_boundary_settings"]
