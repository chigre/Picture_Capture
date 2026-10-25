"""Shared OCR-channel engine execution and per-crop arbitration.

These algorithms are physically owned by the OCR domain, not the root facade.
The public OcrChannelSession retains its stable class identity, while its methods
inject currently patched legacy providers on each invocation. No Tk or eager
Paddle import occurs here; source-pixel boxes and engine failures are unchanged.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image
    from ..ocr_channel import OcrChannelCandidate, OcrChannelResult

def run_paddle_raw(
    self,
    image: Image.Image,
    *,
    engine: Any | None = None,
    deps: dict[str, Any],
) -> tuple[Any, ...]:
    """Execute Paddle inference and return raw Paddle results.

    This deliberately contains no headword/parser policy. The shared channel
    also owns Paddle result normalization; compatibility consumers only adapt
    the neutral records into their historical record type.
    """
    np = deps["np"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    _RAW_OCR_THRESHOLD = deps["_RAW_OCR_THRESHOLD"]


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
    deps: dict[str, Any],
) -> OcrChannelCandidate:
    """Run Paddle with mature crop preprocessing and source-coordinate boxes."""
    prepare_ocr_input = deps["prepare_ocr_input"]
    normalize_paddle_result = deps["normalize_paddle_result"]
    _rescale_channel_records = deps["_rescale_channel_records"]
    _candidate_from_records = deps["_candidate_from_records"]
    OcrChannelCandidate = deps["OcrChannelCandidate"]


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


def run_tesseract_records(
    self,
    image: Image.Image,
    psm: int,
    *, deps: dict[str, Any],
) -> OcrChannelCandidate:
    """Run Tesseract TSV and retain word boxes for every consumer."""
    find_tesseract = deps["find_tesseract"]
    BytesIO = deps["BytesIO"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    resolved_tesseract_language = deps["resolved_tesseract_language"]
    subprocess = deps["subprocess"]
    OcrChannelRecord = deps["OcrChannelRecord"]
    _candidate_from_records = deps["_candidate_from_records"]
    OcrChannelCandidate = deps["OcrChannelCandidate"]


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


def run_lens_records(
    self,
    image: Image.Image,
    *,
    language: str | None = None,
    timeout: int | None = None,
    default_confidence: float | None = None,
    deps: dict[str, Any],
) -> OcrChannelCandidate:
    """Run Lens and normalize its geometry without consumer policy."""
    run_google_lens = deps["run_google_lens"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    OcrChannelRecord = deps["OcrChannelRecord"]
    _candidate_from_records = deps["_candidate_from_records"]
    OcrChannelCandidate = deps["OcrChannelCandidate"]


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


def recognize_crop(
    self,
    image: Image.Image,
    *,
    tesseract_psm: int = 7,
    deps: dict[str, Any],
) -> OcrChannelResult:
    """Run all OCR engines selected for the shared channel on one crop."""
    OcrChannelResult = deps["OcrChannelResult"]


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
