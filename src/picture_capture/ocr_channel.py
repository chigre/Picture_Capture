from __future__ import annotations

"""Shared OCR channel independent from how OCR results are consumed.

The channel owns OCR-engine selection and execution.  Consumers decide what the
recognized text/boxes *mean*: existing-marker text fill, OCR-assisted headword
boundary drawing, proofreading diagnostics, and future OCR features can all use
the same engine plan without coupling OCR itself to separator generation.

Historical ``paddle_*`` setting names remain storage/UI compatibility fields for
now.  Runtime code should resolve them through :func:`resolve_ocr_channel_plan`
instead of reading them independently in every feature.
"""

from dataclasses import dataclass, field
from io import BytesIO
import subprocess
import unicodedata
from typing import Any, Callable, Iterable

from PIL import Image

from .image_utils import normalize_page_rgb
from .models import AppSettings, resolved_tesseract_language
from .ocr_engines import find_tesseract, run_google_lens


OCR_ENGINE_ORDER: tuple[str, ...] = ("paddle", "tesseract", "lens")
_ENGINE_ALIASES = {
    "paddle": "paddle",
    "paddleocr": "paddle",
    "tesseract": "tesseract",
    "lens": "lens",
    "google_lens": "lens",
    "googlelens": "lens",
}


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
    Paddle, Tesseract and Lens can all be enabled together.  The historical
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
            # A legacy Lens-only project has no separate mode setting.  Treat it
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

    Exact normalized agreement between two enabled voting engines wins.  When
    engines disagree, deterministic channel order is used instead of inventing a
    geometry/parser score here; higher-level consumers remain free to perform a
    richer arbitration before calling this helper.
    """

    by_engine = {
        item.engine: item
        for item in choices
        if str(item.text or "").strip()
    }
    voting = [
        by_engine[name]
        for name in plan.enabled_engines
        if name in by_engine and (plan.votes(name) or not plan.voting_engines)
    ]
    if not voting:
        voting = [by_engine[name] for name in plan.enabled_engines if name in by_engine]
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


class OcrChannelSession:
    """Reusable multi-engine OCR session for many crops from one page/job."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        paddle_runner: Callable[[Image.Image], OcrChannelCandidate] | None = None,
        tesseract_runner: Callable[[Image.Image, int], OcrChannelCandidate] | None = None,
        lens_runner: Callable[[Image.Image], OcrChannelCandidate] | None = None,
    ) -> None:
        self.settings = settings
        self.plan = resolve_ocr_channel_plan(settings)
        self._paddle_runner = paddle_runner
        self._tesseract_runner = tesseract_runner
        self._lens_runner = lens_runner
        self._paddle_engine: Any | None = None

    def _run_paddle(self, image: Image.Image) -> OcrChannelCandidate:
        if self._paddle_runner is not None:
            return self._paddle_runner(image)
        try:
            from .paddle_headwords import get_paddle_engine, run_paddle_band

            if self._paddle_engine is None:
                self._paddle_engine = get_paddle_engine(self.settings)
            records = tuple(
                run_paddle_band(
                    normalize_page_rgb(image),
                    self.settings,
                    engine=self._paddle_engine,
                )
            )
            text = " ".join(
                str(getattr(record, "text", "") or "").strip()
                for record in records
                if str(getattr(record, "text", "") or "").strip()
            ).strip()
            conf_values = [
                float(getattr(record, "confidence", 0.0) or 0.0)
                for record in records
                if getattr(record, "confidence", None) is not None
            ]
            confidence = (
                sum(conf_values) / len(conf_values)
                if conf_values else None
            )
            return OcrChannelCandidate(
                engine="paddle",
                text=text,
                confidence=confidence,
                records=records,
            )
        except Exception as exc:
            return OcrChannelCandidate(engine="paddle", error=str(exc))

    def _run_tesseract(self, image: Image.Image, psm: int) -> OcrChannelCandidate:
        if self._tesseract_runner is not None:
            return self._tesseract_runner(image, int(psm))
        try:
            resolved = find_tesseract(str(getattr(self.settings, "ocr_executable", "tesseract") or "tesseract"))
            if not resolved:
                raise RuntimeError("未找到 Tesseract OCR")
            payload = BytesIO()
            normalize_page_rgb(image).save(payload, format="PNG")
            command = [
                str(resolved),
                "stdin",
                "stdout",
                "-l",
                resolved_tesseract_language(self.settings),
                "--psm",
                str(max(1, int(psm))),
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
            text = proc.stdout.decode("utf-8", errors="replace").strip()
            return OcrChannelCandidate(engine="tesseract", text=text)
        except Exception as exc:
            return OcrChannelCandidate(engine="tesseract", error=str(exc))

    def _run_lens(self, image: Image.Image) -> OcrChannelCandidate:
        if self._lens_runner is not None:
            return self._lens_runner(image)
        try:
            records, text, version = run_google_lens(
                normalize_page_rgb(image),
                language=str(
                    getattr(self.settings, "ocr_language", "")
                    or getattr(self.settings, "paddle_lens_language", "")
                    or ""
                ),
                timeout=int(getattr(self.settings, "paddle_lens_timeout", 60) or 60),
                default_confidence=float(
                    getattr(self.settings, "paddle_lens_default_confidence", 0.82)
                    or 0.82
                ),
            )
            conf_values = [float(record[1]) for record in records if len(record) >= 2]
            confidence = (
                sum(conf_values) / len(conf_values)
                if conf_values
                else float(
                    getattr(self.settings, "paddle_lens_default_confidence", 0.82)
                    or 0.82
                )
            )
            return OcrChannelCandidate(
                engine="lens",
                text=str(text or "").strip(),
                confidence=confidence,
                records=tuple(records),
                participates_in_fusion=self.plan.lens_mode != "diagnostic",
                metadata={"version": str(version or "")},
            )
        except Exception as exc:
            return OcrChannelCandidate(
                engine="lens",
                error=str(exc),
                participates_in_fusion=self.plan.lens_mode != "diagnostic",
            )

    @staticmethod
    def _needs_conflict_lens(candidates: Iterable[OcrChannelCandidate]) -> bool:
        successful = [item for item in candidates if item.ok]
        if len(successful) < 2:
            return True
        keys = {channel_text_key(item.text) for item in successful if channel_text_key(item.text)}
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
    "OcrChannelResult",
    "OcrChannelSession",
    "OcrTextChoice",
    "channel_text_key",
    "choose_ocr_text",
    "resolve_ocr_channel_plan",
]
