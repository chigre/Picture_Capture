from __future__ import annotations

"""Compatibility seam between the shared OCR channel and the mature parser core.

New OCR consumers use :mod:`picture_capture.ocr_channel` directly. The mature
headword parser still expects historical ``paddle_*`` execution fields and its
own OCR-record class, so this module performs the two remaining compatibility
jobs in one place:

1. translate one neutral :class:`OcrChannelPlan` into the old execution fields;
2. route the legacy core's engine runner call sites through ``OcrChannelSession``
   while leaving parser/filter/alignment/arbitration code untouched.

The old runner implementations may remain in ``paddle_headwords_core.py`` for
source/backward compatibility, but the normal OCR-boundary consumer no longer
uses them to execute Paddle, Tesseract, or Lens.
"""

from contextlib import contextmanager
from dataclasses import replace
import threading
from typing import Any, Iterator

from . import paddle_headwords_core as _legacy_core
from .models import AppSettings
from .ocr_channel import (
    OcrChannelCandidate,
    OcrChannelPlan,
    OcrChannelSession,
    resolve_ocr_channel_plan,
)


_LEGACY_RUNNER_LOCK = threading.RLock()
_NATIVE_GET_PADDLE_ENGINE = _legacy_core.get_paddle_engine
_NATIVE_RUN_PADDLE_BAND = _legacy_core.run_paddle_band
_NATIVE_RUN_TESSERACT_BAND = _legacy_core.run_tesseract_band_records
_NATIVE_RUN_GOOGLE_LENS = _legacy_core.run_google_lens


def apply_channel_plan_to_legacy_boundary_settings(
    settings: AppSettings,
    plan: OcrChannelPlan | None = None,
) -> AppSettings:
    """Return a copy whose legacy OCR flags mirror one resolved channel plan.

    This is deliberately a one-way compatibility translation. The historical
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
            # neutral channel fallback. The legacy parser needs one of its
            # historical switches enabled in order to request that source.
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


def _legacy_record(record: Any):
    """Convert one neutral channel record to the mature core record type."""

    return _legacy_core.OCRRecord(
        str(getattr(record, "text", "") or ""),
        float(getattr(record, "confidence", 0.0) or 0.0),
        tuple(int(value) for value in getattr(record, "box")),
    )


def _raise_candidate_error(candidate: OcrChannelCandidate, engine: str) -> None:
    if candidate.error:
        raise RuntimeError(candidate.error)
    if candidate.engine != engine:
        raise RuntimeError(
            f"OCR channel runner mismatch: expected {engine}, got {candidate.engine}"
        )


def _channel_paddle_band_runner(
    session: OcrChannelSession,
    band,
    settings: AppSettings,
    engine: Any | None = None,
):
    """Preserve legacy preprocessing/record normalization around channel inference.

    The mature parser's preprocessing and Paddle-result normalization are stable
    parser-adjacent compatibility helpers. Engine construction/inference itself
    is now owned by ``OcrChannelSession``.
    """

    prepared, input_scale = _legacy_core.prepare_ocr_band(
        band,
        max_long_side=getattr(settings, "paddle_max_input_side", 2800),
        mode=getattr(settings, "paddle_preprocessing", "original"),
    )
    results = session.run_paddle_raw(prepared, engine=engine)
    if not results:
        return []
    records = list(_legacy_core.extract_ocr_records(results[0]))
    if not records or abs(float(input_scale) - 1.0) < 1e-9:
        return records

    inverse = 1.0 / max(1e-9, float(input_scale))
    return [
        _legacy_core.OCRRecord(
            str(row.text),
            float(row.confidence),
            tuple(round(float(value) * inverse) for value in row.box),
            recovery=str(getattr(row, "recovery", "") or ""),
            recovery_source_text=str(
                getattr(row, "recovery_source_text", "") or ""
            ),
            parent_box=(
                tuple(
                    round(float(value) * inverse)
                    for value in getattr(row, "parent_box")
                )
                if getattr(row, "parent_box", None) is not None
                else None
            ),
        )
        for row in records
    ]


def _channel_tesseract_band_runner(
    session: OcrChannelSession,
    band,
    settings: AppSettings,
    psm_override: int | None = None,
):
    psm = int(
        psm_override
        if psm_override is not None
        else (getattr(settings, "paddle_tesseract_psm", 6) or 6)
    )
    candidate = session.run_tesseract_records(band, psm)
    _raise_candidate_error(candidate, "tesseract")
    records = [_legacy_record(record) for record in candidate.records]
    return records, str(candidate.text or "")


def _channel_lens_runner(
    session: OcrChannelSession,
    image,
    *,
    language: str = "es",
    timeout: int = 60,
    default_confidence: float = 0.82,
):
    candidate = session.run_lens_records(
        image,
        language=language,
        timeout=timeout,
        default_confidence=default_confidence,
    )
    _raise_candidate_error(candidate, "lens")
    records = [
        (
            str(getattr(record, "text", "") or ""),
            float(getattr(record, "confidence", 0.0) or 0.0),
            tuple(int(value) for value in getattr(record, "box")),
        )
        for record in candidate.records
    ]
    return (
        records,
        str(candidate.text or ""),
        str(candidate.metadata.get("version", "") or ""),
    )


@contextmanager
def route_legacy_boundary_ocr_through_channel(
    settings: AppSettings,
    plan: OcrChannelPlan | None = None,
) -> Iterator[OcrChannelSession]:
    """Route mature boundary backend engine calls through the shared channel.

    The core is intentionally not rewritten: its parser, record filtering,
    Tesseract PSM comparison, Lens conflict timing, alignment and arbitration all
    remain in place. Only the four low-level engine call sites are replaced for
    the duration of one boundary-detection call.

    The routing is protected by a process-local lock because the legacy core
    resolves runner names from module globals. Existing external/test monkeypatch
    hooks are respected: a runner that has already been replaced by a caller is
    not overwritten by this bridge.
    """

    resolved = plan or resolve_ocr_channel_plan(settings)
    session = OcrChannelSession(settings, plan=resolved)

    with _LEGACY_RUNNER_LOCK:
        originals = {
            "get_paddle_engine": _legacy_core.get_paddle_engine,
            "run_paddle_band": _legacy_core.run_paddle_band,
            "run_tesseract_band_records": _legacy_core.run_tesseract_band_records,
            "run_google_lens": _legacy_core.run_google_lens,
        }

        if _legacy_core.get_paddle_engine is _NATIVE_GET_PADDLE_ENGINE:
            _legacy_core.get_paddle_engine = lambda _settings: session.get_paddle_engine()
        if _legacy_core.run_paddle_band is _NATIVE_RUN_PADDLE_BAND:
            _legacy_core.run_paddle_band = (
                lambda band, run_settings, engine=None: _channel_paddle_band_runner(
                    session, band, run_settings, engine=engine
                )
            )
        if _legacy_core.run_tesseract_band_records is _NATIVE_RUN_TESSERACT_BAND:
            _legacy_core.run_tesseract_band_records = (
                lambda band, run_settings, psm_override=None: _channel_tesseract_band_runner(
                    session, band, run_settings, psm_override=psm_override
                )
            )
        if _legacy_core.run_google_lens is _NATIVE_RUN_GOOGLE_LENS:
            _legacy_core.run_google_lens = (
                lambda image, *, language="es", timeout=60, default_confidence=0.82:
                _channel_lens_runner(
                    session,
                    image,
                    language=language,
                    timeout=timeout,
                    default_confidence=default_confidence,
                )
            )

        try:
            yield session
        finally:
            for name, original in originals.items():
                setattr(_legacy_core, name, original)


__all__ = [
    "apply_channel_plan_to_legacy_boundary_settings",
    "route_legacy_boundary_ocr_through_channel",
]
