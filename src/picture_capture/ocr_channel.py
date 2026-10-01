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
import unicodedata
from typing import Any, Callable, Iterable

import numpy as np
from PIL import Image, ImageOps

from .image_utils import normalize_page_rgb
from .models import AppSettings, resolved_tesseract_language
from .ocr_engines import find_tesseract, run_google_lens
from .runtime_environment import resolve_paddle_device


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


def channel_text_key(value: object) -> str:
    """Low-level OCR agreement key; consumers may still apply richer parsing."""

    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return " ".join(text.split())


def choose_ocr_text(
    plan: OcrChannelPlan,
    choices: Iterable[OcrTextChoice],
) -> tuple[OcrTextChoice | None, bool]:
    """Choose text without embedding any separator/headword drawing policy.

    Exact normalized agreement between two enabled voting engines wins. When
    engines disagree, deterministic channel order is used instead of inventing a
    geometry/parser score here; higher-level consumers remain free to perform a
    richer arbitration before calling this helper. Diagnostic-only engines never
    become the selected text source, even when all voting engines fail.
    """

    by_engine = {
        item.engine: item
        for item in choices
        if str(item.text or "").strip()
    }
    voting = [
        by_engine[name]
        for name in plan.voting_engines
        if name in by_engine
    ]
    if not voting:
        return None, False

    groups: dict[str, list[OcrTextChoice]] = {}
    for item in voting:
        key = channel_text_key(item.text)
        if key:
            groups.setdefault(key, []).append(item)
    agreeing = [items for items in groups.values() if len(items) >= 2]
    if agreeing:
        agreeing.sort(
            key=lambda items: (
                -len(items),
                min(plan.enabled_engines.index(item.engine) for item in items),
            )
        )
        group = agreeing[0]
        group.sort(key=lambda item: plan.enabled_engines.index(item.engine))
        return group[0], True

    return voting[0], False


def _paddle_language(settings: AppSettings) -> str:
    """Preserve the mature core's Paddle language/model resolution exactly."""

    configured = str(getattr(settings, "paddle_language", "") or "").strip()
    if configured:
        return configured
    mapping = {
        "eng": "en",
        "ita": "it",
        "spa": "es",
        "fra": "fr",
        "por": "pt",
        "deu": "de",
        "chi_sim": "ch",
        "chi_tra": "chinese_cht",
    }
    # Tesseract accepts composite packs such as spa+eng; Paddle expects one
    # language/model family. Prefer the first recognized component. A separate
    # tesseract_language setting must never alter Paddle model selection.
    raw_language = str(getattr(settings, "ocr_language", "") or "").strip()
    parts = [part.strip() for part in raw_language.split("+") if part.strip()]
    for part in parts:
        if part in mapping:
            return mapping[part]
    return mapping.get(raw_language, raw_language)


def _ocr_input_otsu_threshold(gray: np.ndarray) -> int:
    """Return the same conservative Otsu threshold used by the mature runner."""

    if gray.size == 0:
        return 180
    hist = np.bincount(gray.astype(np.uint8).ravel(), minlength=256).astype(np.float64)
    total = float(gray.size)
    weighted_total = float(np.dot(np.arange(256, dtype=np.float64), hist))
    background_weight = 0.0
    background_sum = 0.0
    best_variance = -1.0
    best_threshold = 180
    for threshold in range(256):
        background_weight += hist[threshold]
        if background_weight <= 0:
            continue
        foreground_weight = total - background_weight
        if foreground_weight <= 0:
            break
        background_sum += threshold * hist[threshold]
        background_mean = background_sum / background_weight
        foreground_mean = (weighted_total - background_sum) / foreground_weight
        between = background_weight * foreground_weight * (background_mean - foreground_mean) ** 2
        if between > best_variance:
            best_variance = between
            best_threshold = threshold
    return int(min(220, max(80, best_threshold)))


def prepare_ocr_input(
    image: Image.Image,
    *,
    max_long_side: int = 2800,
    mode: str = "original",
) -> tuple[Image.Image, float]:
    """Prepare a Paddle crop and return source-to-input coordinate scale.

    This is the engine-level preprocessing formerly reached indirectly through
    ``paddle_headwords_core.run_paddle_band``. Keeping it in the shared channel
    preserves marker-only OCR behavior without importing the mature parser.
    """

    source = normalize_page_rgb(image)
    normalized_mode = str(mode or "original").strip().lower()
    if normalized_mode in {"grayscale", "gray", "auto_contrast", "binary"}:
        gray = ImageOps.grayscale(source)
        if normalized_mode in {"auto_contrast", "binary"}:
            gray = ImageOps.autocontrast(gray)
        if normalized_mode == "binary":
            array = np.asarray(gray)
            threshold = _ocr_input_otsu_threshold(array)
            gray = Image.fromarray(
                np.where(array > threshold, 255, 0).astype(np.uint8),
                mode="L",
            )
        source = gray.convert("RGB")
    limit = max(256, int(max_long_side or 2800))
    scale = min(1.0, limit / max(source.size))
    if scale < 1.0:
        source = source.resize(
            (
                max(1, round(source.width * scale)),
                max(1, round(source.height * scale)),
            ),
            Image.Resampling.LANCZOS,
        )
    return source, scale


def clear_ocr_channel_paddle_engine_cache(
    *,
    keep_key: tuple[str, str, str, bool] | None = None,
) -> None:
    """Drop channel-owned Paddle engines that are no longer active.

    Local references held by in-flight OCR calls remain valid. Keeping only one
    strongly cached configuration preserves the mature runner's memory behavior
    when users switch language/model/device settings.
    """

    with _PADDLE_ENGINE_CACHE_LOCK:
        stale = [key for key in _PADDLE_ENGINE_CACHE if key != keep_key]
        for key in stale:
            _PADDLE_ENGINE_CACHE.pop(key, None)
    if stale:
        gc.collect()


def _create_paddle_engine(settings: AppSettings) -> Any:
    language = _paddle_language(settings)
    orientation = bool(getattr(settings, "paddle_use_textline_orientation", False))
    device = resolve_paddle_device()
    version = str(getattr(settings, "paddle_ocr_version", "PP-OCRv5") or "PP-OCRv5")
    key = (language, device, version, orientation)
    with _PADDLE_ENGINE_CACHE_LOCK:
        existing = _PADDLE_ENGINE_CACHE.get(key)
        if existing is not None:
            return existing

    try:
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise RuntimeError(
            "尚未安装 PaddleOCR。请运行当前平台的 OCR 安装脚本，或在受支持平台执行："
            "uv sync --extra ocr-cpu"
        ) from exc
    try:
        kwargs = dict(
            lang=language,
            ocr_version=version,
            device=device,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=orientation,
            enable_mkldnn=False,
        )
        try:
            engine = PaddleOCR(**kwargs)
        except TypeError:
            # Some PaddleOCR 3.x builds do not expose this constructor flag.
            kwargs.pop("enable_mkldnn", None)
            engine = PaddleOCR(**kwargs)
    except Exception as exc:
        raise RuntimeError(
            f"PaddleOCR 初始化失败（语言={language}，设备={device}，版本={version}）：{exc}"
        ) from exc

    clear_ocr_channel_paddle_engine_cache(keep_key=key)
    with _PADDLE_ENGINE_CACHE_LOCK:
        existing = _PADDLE_ENGINE_CACHE.get(key)
        if existing is not None:
            return existing
        _PADDLE_ENGINE_CACHE[key] = engine
    return engine


def _paddle_json_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        payload = result
    else:
        payload = getattr(result, "json", None)
        if callable(payload):
            payload = payload()
        if not isinstance(payload, dict):
            payload = getattr(result, "res", None)
        if not isinstance(payload, dict):
            raise RuntimeError("PaddleOCR 返回了无法解析的结果格式")
    nested = payload.get("res")
    return nested if isinstance(nested, dict) else payload


def _box_from_paddle_value(value: Any) -> tuple[int, int, int, int] | None:
    try:
        array = np.asarray(value, dtype=float)
    except Exception:
        return None
    if array.size == 4:
        flat = array.reshape(-1)
        x0, y0, x1, y1 = (int(round(float(item))) for item in flat[:4])
    elif array.ndim >= 2 and array.shape[-1] >= 2:
        points = array.reshape(-1, array.shape[-1])
        x0 = int(round(float(np.min(points[:, 0]))))
        y0 = int(round(float(np.min(points[:, 1]))))
        x1 = int(round(float(np.max(points[:, 0]))))
        y1 = int(round(float(np.max(points[:, 1]))))
    else:
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def _extract_paddle_channel_records(result: Any) -> tuple[OcrChannelRecord, ...]:
    payload = _paddle_json_payload(result)
    raw_texts = payload.get("rec_texts")
    raw_scores = payload.get("rec_scores")
    raw_boxes = payload.get("rec_boxes")
    if raw_boxes is None:
        raw_boxes = payload.get("rec_polys")
    texts = list(raw_texts) if raw_texts is not None else []
    scores = list(raw_scores) if raw_scores is not None else []
    boxes = list(raw_boxes) if raw_boxes is not None else []
    records: list[OcrChannelRecord] = []
    for index, text in enumerate(texts):
        value = str(text or "").strip()
        if not value or index >= len(boxes):
            continue
        box = _box_from_paddle_value(boxes[index])
        if box is None:
            continue
        try:
            confidence = float(scores[index]) if index < len(scores) else 0.0
        except (TypeError, ValueError):
            confidence = 0.0
        records.append(OcrChannelRecord(value, confidence, box))
    records.sort(key=lambda item: (item.box[1], item.box[0]))
    return tuple(records)


def _rescale_channel_records(
    records: Iterable[OcrChannelRecord],
    input_scale: float,
) -> tuple[OcrChannelRecord, ...]:
    collected = tuple(records)
    if not collected or abs(float(input_scale) - 1.0) < 1e-9:
        return collected
    inverse = 1.0 / max(1e-9, float(input_scale))
    return tuple(
        OcrChannelRecord(
            text=row.text,
            confidence=row.confidence,
            box=tuple(round(float(value) * inverse) for value in row.box),
        )
        for row in collected
    )


def _candidate_from_records(
    engine: str,
    records: Iterable[OcrChannelRecord],
    *,
    text: str = "",
    metadata: dict[str, Any] | None = None,
    participates_in_fusion: bool = True,
) -> OcrChannelCandidate:
    collected = tuple(records)
    final_text = str(text or "").strip()
    if not final_text:
        final_text = " ".join(item.text for item in collected if item.text).strip()
    confidence_values = [float(item.confidence) for item in collected]
    confidence = (
        sum(confidence_values) / len(confidence_values)
        if confidence_values else None
    )
    return OcrChannelCandidate(
        engine=engine,
        text=final_text,
        confidence=confidence,
        records=collected,
        participates_in_fusion=participates_in_fusion,
        metadata=dict(metadata or {}),
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

        This deliberately contains no headword/parser policy. The legacy
        boundary bridge may reuse its battle-tested record normalization while
        all actual engine invocation is owned by the shared OCR channel.
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
                records = _extract_paddle_channel_records(results[0])
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
    "prepare_ocr_input",
    "resolve_ocr_channel_plan",
]
