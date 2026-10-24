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
        """Execute Paddle inference and return raw Paddle results.

        This deliberately contains no headword/parser policy. The shared channel
        also owns Paddle result normalization; compatibility consumers only adapt
        the neutral records into their historical record type.
        """

        active = engine or self.get_paddle_engine()
        try:
            results = list(active.predict(
                np.asarray(normalize_page_rgb(image)),
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=bool(
                    getattr(self.settings, "paddle_use_textline_orientation", False)
                ),
                text_rec_score_thresh=_RAW_OCR_THRESHOLD,
            ))
        except Exception as exc:
            raise RuntimeError(f"PaddleOCR 推理失败：{exc}") from exc
        return tuple(results)

    def run_paddle_records(
        self,
        image: Image.Image,
        *,
        engine: Any | None = None,
    ) -> OcrChannelCandidate:
        """Run Paddle with mature crop preprocessing and source-coordinate boxes."""

        try:
            prepared, input_scale = prepare_ocr_input(
                image,
                max_long_side=getattr(self.settings, "paddle_max_input_side", 2800),
                mode=getattr(self.settings, "paddle_preprocessing", "original"),
            )
            results = self.run_paddle_raw(prepared, engine=engine)
            records: tuple[OcrChannelRecord, ...] = ()
            if results:
                records = normalize_paddle_result(results[0])
                records = _rescale_channel_records(records, input_scale)
            return _candidate_from_records(
                "paddle",
                records,
                metadata={
                    "input_scale": float(input_scale),
                    "preprocessing": str(
                        getattr(self.settings, "paddle_preprocessing", "original")
                        or "original"
                    ),
                },
            )
        except Exception as exc:
            return OcrChannelCandidate(engine="paddle", error=str(exc))

    def _run_paddle(self, image: Image.Image) -> OcrChannelCandidate:
        if self._paddle_runner is not None:
            return self._paddle_runner(image)
        return self.run_paddle_records(image)

    def run_tesseract_records(
        self,
        image: Image.Image,
        psm: int,
    ) -> OcrChannelCandidate:
        """Run Tesseract TSV and retain word boxes for every consumer."""

        if self._tesseract_runner is not None:
            return self._tesseract_runner(image, int(psm))
        try:
            resolved = find_tesseract(
                str(getattr(self.settings, "ocr_executable", "tesseract") or "tesseract")
            )
            if not resolved:
                raise RuntimeError("未找到 Tesseract OCR")
            payload = BytesIO()
            normalize_page_rgb(image).save(payload, format="PNG")
            effective_psm = max(1, int(psm))
            command = [
                str(resolved),
                "stdin",
                "stdout",
                "-l",
                resolved_tesseract_language(self.settings),
                "--psm",
                str(effective_psm),
                "tsv",
            ]
            proc = subprocess.run(
                command,
                input=payload.getvalue(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=120,
            )
            if proc.returncode:
                detail = proc.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(detail or f"Tesseract exit={proc.returncode}")

            tsv = proc.stdout.decode("utf-8", errors="replace")
            lines = tsv.splitlines()
            if not lines:
                return _candidate_from_records(
                    "tesseract", (), metadata={"psm": effective_psm, "executable": str(resolved)}
                )
            header = lines[0].split("\t")
            index = {name: i for i, name in enumerate(header)}
            required = {"level", "left", "top", "width", "height", "conf", "text"}
            if not required.issubset(index):
                raise RuntimeError("Tesseract TSV 缺少必要字段")

            records: list[OcrChannelRecord] = []
            line_fields = ("page_num", "block_num", "par_num", "line_num", "word_num")
            can_group = all(name in index for name in line_fields)
            grouped_text: dict[tuple[int, int, int, int], list[tuple[int, str]]] = {}
            for raw in lines[1:]:
                cells = raw.split("\t")
                try:
                    if int(cells[index["level"]]) != 5:
                        continue
                    text = cells[index["text"]].strip()
                    if not text:
                        continue
                    confidence = float(cells[index["conf"]]) / 100.0
                    left = int(cells[index["left"]])
                    top = int(cells[index["top"]])
                    width = int(cells[index["width"]])
                    height = int(cells[index["height"]])
                    if can_group:
                        page_num = int(cells[index["page_num"]])
                        block_num = int(cells[index["block_num"]])
                        par_num = int(cells[index["par_num"]])
                        line_num = int(cells[index["line_num"]])
                        word_num = int(cells[index["word_num"]])
                except (ValueError, IndexError):
                    continue
                if width <= 0 or height <= 0:
                    continue
                records.append(OcrChannelRecord(
                    text=text,
                    confidence=max(0.0, confidence),
                    box=(left, top, left + width, top + height),
                ))
                if can_group:
                    key = (page_num, block_num, par_num, line_num)
                    grouped_text.setdefault(key, []).append((word_num, text))
            records.sort(key=lambda item: (item.box[1], item.box[0]))
            if can_group:
                text_lines = [
                    " ".join(value for _word, value in sorted(words)).strip()
                    for _key, words in sorted(grouped_text.items())
                ]
                text = "\n".join(line for line in text_lines if line)
            else:
                text = " ".join(record.text for record in records).strip()
            return _candidate_from_records(
                "tesseract",
                records,
                text=text,
                metadata={"psm": effective_psm, "executable": str(resolved)},
            )
        except Exception as exc:
            return OcrChannelCandidate(engine="tesseract", error=str(exc))

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
        """Run Lens and normalize its geometry without consumer policy."""

        if self._lens_runner is not None:
            return self._lens_runner(image)
        participates = self.plan.lens_mode != "diagnostic"
        try:
            confidence_default = float(
                default_confidence
                if default_confidence is not None
                else (
                    getattr(self.settings, "paddle_lens_default_confidence", 0.82)
                    or 0.82
                )
            )
            records, text, version = run_google_lens(
                normalize_page_rgb(image),
                language=str(
                    language
                    if language is not None
                    else (
                        getattr(self.settings, "ocr_language", "")
                        or getattr(self.settings, "paddle_lens_language", "")
                        or ""
                    )
                ),
                timeout=int(
                    timeout
                    if timeout is not None
                    else (getattr(self.settings, "paddle_lens_timeout", 60) or 60)
                ),
                default_confidence=confidence_default,
            )
            normalized_records = tuple(
                OcrChannelRecord(
                    text=str(record[0] or "").strip(),
                    confidence=float(record[1]),
                    box=tuple(int(value) for value in record[2]),
                )
                for record in records
                if len(record) >= 3 and str(record[0] or "").strip()
            )
            candidate = _candidate_from_records(
                "lens",
                normalized_records,
                text=str(text or "").strip(),
                metadata={"version": str(version or "")},
                participates_in_fusion=participates,
            )
            if candidate.confidence is None:
                return OcrChannelCandidate(
                    engine="lens",
                    text=candidate.text,
                    confidence=confidence_default if candidate.text else None,
                    records=candidate.records,
                    participates_in_fusion=participates,
                    metadata=candidate.metadata,
                )
            return candidate
        except Exception as exc:
            return OcrChannelCandidate(
                engine="lens",
                error=str(exc),
                participates_in_fusion=participates,
            )

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
        """Run all OCR engines selected for the shared channel on one crop."""

        candidates: list[OcrChannelCandidate] = []
        if self.plan.enabled("paddle"):
            candidates.append(self._run_paddle(image))
        if self.plan.enabled("tesseract"):
            candidates.append(self._run_tesseract(image, tesseract_psm))

        lens_attempted = False
        if self.plan.enabled("lens"):
            lens_attempted = self.plan.lens_mode in {"diagnostic", "full"}
            if self.plan.lens_mode == "conflict":
                lens_attempted = self._needs_conflict_lens(candidates)
            if lens_attempted:
                candidates.append(self._run_lens(image))

        return OcrChannelResult(
            plan=self.plan,
            candidates=tuple(candidates),
            lens_attempted=lens_attempted,
        )


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
