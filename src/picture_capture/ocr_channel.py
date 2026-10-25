from __future__ import annotations

"""Shared OCR channel independent from how OCR results are consumed.

The channel owns OCR-engine selection and execution. Consumers decide what the
recognized text/boxes *mean*: existing-marker text fill, OCR-assisted headword
boundary drawing, proofreading diagnostics, and future OCR features can all use
the same engine plan without coupling OCR itself to separator generation.

Historical ``paddle_*`` setting names remain storage/UI compatibility fields for
now. Runtime code should resolve them through :func:`resolve_ocr_channel_plan`
instead of reading them independently in every feature.
"""

from dataclasses import dataclass, field
import gc
from io import BytesIO
import subprocess
import threading
from typing import Any, Callable, Iterable

import numpy as np
from PIL import Image, ImageOps

from .ocr import channel_preparation as _channel_preparation
from .ocr import channel_results as _channel_results
from .ocr import channel_engine_execution as _channel_engine_execution
from .ocr import paddle_engine_lifecycle as _paddle_engine_lifecycle
from .preprocess.analysis_image import normalize_page_rgb
from .models import AppSettings, resolved_tesseract_language
from .ocr.engines import find_tesseract, run_google_lens
from .quality.inference_performance import resolve_inference_policy, paddle_constructor_variants


OCR_ENGINE_ORDER: tuple[str, ...] = ("paddle", "tesseract", "lens")
_ENGINE_ALIASES = {
    "paddle": "paddle",
    "paddleocr": "paddle",
    "tesseract": "tesseract",
    "lens": "lens",
    "google_lens": "lens",
    "googlelens": "lens",
}
_RAW_OCR_THRESHOLD = 0.20
_PADDLE_ENGINE_CACHE: dict[tuple[str, str, str, bool], Any] = {}
_PADDLE_ENGINE_CACHE_LOCK = threading.RLock()


@dataclass(frozen=True, slots=True)
class OcrChannelPlan:
    """Resolved engine policy shared by OCR consumers."""

    enabled_engines: tuple[str, ...]
    voting_engines: tuple[str, ...]
    lens_mode: str = "off"

    def enabled(self, engine: str) -> bool:
        return str(engine or "").strip().lower() in self.enabled_engines

    def votes(self, engine: str) -> bool:
        return str(engine or "").strip().lower() in self.voting_engines


@dataclass(frozen=True, slots=True)
class OcrChannelRecord:
    """Engine-neutral OCR text fragment with source-crop geometry."""

    text: str
    confidence: float
    box: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class OcrChannelCandidate:
    """One engine result on a shared crop/band."""

    engine: str
    text: str = ""
    confidence: float | None = None
    records: tuple[Any, ...] = ()
    error: str = ""
    participates_in_fusion: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(str(self.text or "").strip()) and not self.error


@dataclass(frozen=True, slots=True)
class OcrChannelResult:
    plan: OcrChannelPlan
    candidates: tuple[OcrChannelCandidate, ...]
    lens_attempted: bool = False

    def candidate(self, engine: str) -> OcrChannelCandidate | None:
        wanted = str(engine or "").strip().lower()
        return next((item for item in self.candidates if item.engine == wanted), None)

    @property
    def successful(self) -> tuple[OcrChannelCandidate, ...]:
        return tuple(item for item in self.candidates if item.ok)


@dataclass(frozen=True, slots=True)
class OcrTextChoice:
    engine: str
    text: str
    confidence: float | None = None


def _normalized_engine_name(value: object) -> str:
    return _ENGINE_ALIASES.get(str(value or "").strip().lower(), "")


def resolve_ocr_channel_plan(settings: AppSettings) -> OcrChannelPlan:
    """Resolve the project-wide OCR engine selection.

    Existing main-window OCR checkboxes are the authoritative selection source:
    Paddle, Tesseract and Lens can all be enabled together. The historical
    single ``ocr_engine`` value is only a fallback when every multi-engine switch
    is disabled, preserving older projects and non-GUI callers.
    """

    enabled: list[str] = []
    if bool(getattr(settings, "paddle_use_paddleocr", True)):
        enabled.append("paddle")
    if bool(
        getattr(settings, "paddle_compare_tesseract", False)
        or getattr(settings, "paddle_tesseract_rescue", False)
    ):
        enabled.append("tesseract")

    lens_mode = str(getattr(settings, "paddle_lens_mode", "off") or "off").strip().lower()
    if lens_mode not in {"off", "diagnostic", "conflict", "full"}:
        lens_mode = "conflict"
    lens_enabled = bool(getattr(settings, "paddle_enable_lens", False)) and lens_mode != "off"
    if lens_enabled:
        enabled.append("lens")
    else:
        lens_mode = "off"

    if not enabled:
        legacy = _normalized_engine_name(getattr(settings, "ocr_engine", ""))
        enabled.append(legacy or "tesseract")
        if enabled[0] == "lens":
            # A legacy Lens-only project has no separate mode setting. Treat it
            # as a normal participating OCR rather than a diagnostic observer.
            lens_mode = "full"

    enabled = [name for name in OCR_ENGINE_ORDER if name in set(enabled)]
    voting = [
        name for name in enabled
        if not (name == "lens" and lens_mode == "diagnostic")
    ]
    return OcrChannelPlan(
        enabled_engines=tuple(enabled),
        voting_engines=tuple(voting),
        lens_mode=lens_mode,
    )


# Historical OCR-channel imports remain supported. Pure voting is now owned
# by ocr/text_arbitration; the neutral dataclasses stay here for stable pickles.
from .ocr.text_arbitration import channel_text_key, choose_ocr_text

def _paddle_language(settings: AppSettings) -> str:
    return _channel_preparation.paddle_language(settings)


def _ocr_input_otsu_threshold(gray: np.ndarray) -> int:
    return _channel_preparation.otsu_threshold(gray, np_module=np)


def prepare_ocr_input(
    image: Image.Image, *, max_long_side: int = 2800, mode: str = "original",
) -> tuple[Image.Image, float]:
    """Preserve source-to-input scale and current monkeypatch hooks."""
    return _channel_preparation.prepare_ocr_input_impl(
        image, max_long_side=max_long_side, mode=mode,
        normalize_rgb_fn=normalize_page_rgb, image_ops=ImageOps,
        image_cls=Image, np_module=np, otsu_fn=_ocr_input_otsu_threshold,
    )


def clear_ocr_channel_paddle_engine_cache(
    *, keep_key: tuple[str, str, str, bool] | None = None,
) -> None:
    """Historical mutable cache hook; safely drop inactive Paddle engines."""
    return _paddle_engine_lifecycle.clear_cached_engines(
        keep_key=keep_key, cache=_PADDLE_ENGINE_CACHE,
        lock=_PADDLE_ENGINE_CACHE_LOCK, gc_module=gc,
    )


def _create_paddle_engine(settings: AppSettings) -> Any:
    """Historical lazy engine factory with call-time providers and one cache."""
    return _paddle_engine_lifecycle.create_paddle_engine_impl(
        settings, paddle_language_fn=_paddle_language,
        resolve_inference_policy_fn=resolve_inference_policy,
        constructor_variants_fn=paddle_constructor_variants,
        cache=_PADDLE_ENGINE_CACHE, cache_lock=_PADDLE_ENGINE_CACHE_LOCK,
        clear_cache_fn=clear_ocr_channel_paddle_engine_cache,
    )


def _paddle_json_payload(result: Any) -> dict[str, Any]:
    return _channel_results.paddle_json_payload(result)


def normalize_paddle_result(result: Any) -> tuple[OcrChannelRecord, ...]:
    return _channel_results.normalize_paddle_result_impl(
        result, payload_fn=_paddle_json_payload, np_module=np,
        record_cls=OcrChannelRecord,
    )


def _rescale_channel_records(
    records: Iterable[OcrChannelRecord], input_scale: float,
) -> tuple[OcrChannelRecord, ...]:
    return _channel_results.rescale_channel_records(records, input_scale, record_cls=OcrChannelRecord)


def _candidate_from_records(
    engine: str, records: Iterable[OcrChannelRecord], *, text: str = "",
    metadata: dict[str, Any] | None = None, participates_in_fusion: bool = True,
) -> OcrChannelCandidate:
    return _channel_results.candidate_from_records(
        engine, records, text=text, metadata=metadata,
        participates_in_fusion=participates_in_fusion, candidate_cls=OcrChannelCandidate,
    )


class OcrChannelSession:
    """Reusable multi-engine OCR session for many crops from one page/job."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        plan: OcrChannelPlan | None = None,
        paddle_runner: Callable[[Image.Image], OcrChannelCandidate] | None = None,
        tesseract_runner: Callable[[Image.Image, int], OcrChannelCandidate] | None = None,
        lens_runner: Callable[[Image.Image], OcrChannelCandidate] | None = None,
    ) -> None:
        self.settings = settings
        self.plan = plan or resolve_ocr_channel_plan(settings)
        self._paddle_runner = paddle_runner
        self._tesseract_runner = tesseract_runner
        self._lens_runner = lens_runner
        self._paddle_engine: Any | None = None

    def get_paddle_engine(self) -> Any:
        """Return the channel-owned cached Paddle engine for this session."""

        if self._paddle_engine is None:
            self._paddle_engine = _create_paddle_engine(self.settings)
        return self._paddle_engine

    def run_paddle_raw(
        self,
        image: Image.Image,
        *,
        engine: Any | None = None,
    ) -> tuple[Any, ...]:
        """Compatibility method; engine execution is physically owned in ocr/."""
        return _channel_engine_execution.run_paddle_raw(self, image, engine=engine, deps={"np": np, "normalize_page_rgb": normalize_page_rgb, "_RAW_OCR_THRESHOLD": _RAW_OCR_THRESHOLD})

    def run_paddle_records(
        self,
        image: Image.Image,
        *,
        engine: Any | None = None,
    ) -> OcrChannelCandidate:
        """Compatibility method; engine execution is physically owned in ocr/."""
        return _channel_engine_execution.run_paddle_records(self, image, engine=engine, deps={"prepare_ocr_input": prepare_ocr_input, "normalize_paddle_result": normalize_paddle_result, "_rescale_channel_records": _rescale_channel_records, "_candidate_from_records": _candidate_from_records, "OcrChannelCandidate": OcrChannelCandidate})

    def _run_paddle(self, image: Image.Image) -> OcrChannelCandidate:
        if self._paddle_runner is not None:
            return self._paddle_runner(image)
        return self.run_paddle_records(image)

    def run_tesseract_records(
        self,
        image: Image.Image,
        psm: int,
    ) -> OcrChannelCandidate:
        """Compatibility method; engine execution is physically owned in ocr/."""
        return _channel_engine_execution.run_tesseract_records(self, image, psm, deps={"find_tesseract": find_tesseract, "BytesIO": BytesIO, "normalize_page_rgb": normalize_page_rgb, "resolved_tesseract_language": resolved_tesseract_language, "subprocess": subprocess, "OcrChannelRecord": OcrChannelRecord, "_candidate_from_records": _candidate_from_records, "OcrChannelCandidate": OcrChannelCandidate})

    def _run_tesseract(self, image: Image.Image, psm: int) -> OcrChannelCandidate:
        return self.run_tesseract_records(image, psm)

    def run_lens_records(
        self,
        image: Image.Image,
        *,
        language: str | None = None,
        timeout: int | None = None,
        default_confidence: float | None = None,
    ) -> OcrChannelCandidate:
        """Compatibility method; engine execution is physically owned in ocr/."""
        return _channel_engine_execution.run_lens_records(self, image, language=language, timeout=timeout, default_confidence=default_confidence, deps={"run_google_lens": run_google_lens, "normalize_page_rgb": normalize_page_rgb, "OcrChannelRecord": OcrChannelRecord, "_candidate_from_records": _candidate_from_records, "OcrChannelCandidate": OcrChannelCandidate})

    def _run_lens(self, image: Image.Image) -> OcrChannelCandidate:
        return self.run_lens_records(image)

    @staticmethod
    def _needs_conflict_lens(candidates: Iterable[OcrChannelCandidate]) -> bool:
        successful = [item for item in candidates if item.ok]
        if len(successful) < 2:
            return True
        keys = {
            channel_text_key(item.text)
            for item in successful
            if channel_text_key(item.text)
        }
        return len(keys) > 1

    def recognize_crop(
        self,
        image: Image.Image,
        *,
        tesseract_psm: int = 7,
    ) -> OcrChannelResult:
        """Compatibility method; engine execution is physically owned in ocr/."""
        return _channel_engine_execution.recognize_crop(self, image, tesseract_psm=tesseract_psm, deps={"OcrChannelResult": OcrChannelResult})


__all__ = [
    "OCR_ENGINE_ORDER",
    "OcrChannelCandidate",
    "OcrChannelPlan",
    "OcrChannelRecord",
    "OcrChannelResult",
    "OcrChannelSession",
    "OcrTextChoice",
    "channel_text_key",
    "choose_ocr_text",
    "clear_ocr_channel_paddle_engine_cache",
    "normalize_paddle_result",
    "prepare_ocr_input",
    "resolve_ocr_channel_plan",
]
