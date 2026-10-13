"""Standalone Tesseract TSV execution; keeps oversized OCR core slim."""
from __future__ import annotations
from io import BytesIO
import subprocess
from typing import Any
from PIL import Image
from .image_utils import normalize_page_rgb
from .models import AppSettings, resolved_tesseract_language
from .paddle_headword_models import OCRRecord


def run_tesseract_band_records_impl(
    band: Image.Image,
    settings: AppSettings,
    psm_override: int | None = None,
    *, resolve_fn: Any, group_fn: Any,
) -> tuple[list[OCRRecord], str]:
    """Run Tesseract TSV on the same candidate band used by PaddleOCR.

    This is deliberately optional.  A missing/broken Tesseract installation must
    never prevent the primary PaddleOCR pass from completing; callers catch and
    record the exception in the diagnostics report.
    """
    resolved = resolve_fn(settings.ocr_executable)
    if not resolved:
        raise RuntimeError("未找到 Tesseract OCR；请在环境中心选择 Tesseract 可执行程序或查看安装帮助。")
    payload = BytesIO()
    normalize_page_rgb(band).save(payload, format="PNG")
    command = [
        resolved, "stdin", "stdout", "-l", resolved_tesseract_language(settings),
        "--psm", str(max(3, int(psm_override if psm_override is not None else settings.paddle_tesseract_psm))), "tsv",
    ]
    try:
        proc = subprocess.run(
            command, input=payload.getvalue(), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Tesseract OCR 超时（120 秒）；本栏已放弃 Tesseract 结果。") from exc
    if proc.returncode:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Tesseract OCR 失败：{detail}")
    tsv = proc.stdout.decode("utf-8", errors="replace")
    records: list[OCRRecord] = []
    lines = tsv.splitlines()
    if not lines:
        return records, ""
    header = lines[0].split("\t")
    index = {name: i for i, name in enumerate(header)}
    required = {"level", "left", "top", "width", "height", "conf", "text"}
    if not required.issubset(index):
        raise RuntimeError("Tesseract TSV 缺少必要字段")
    for row in lines[1:]:
        cells = row.split("\t")
        if len(cells) < len(header):
            cells += [""] * (len(header) - len(cells))
        try:
            if int(cells[index["level"]]) != 5:
                continue
            text = cells[index["text"]].strip()
            if not text:
                continue
            conf = float(cells[index["conf"]]) / 100.0
            left = int(cells[index["left"]]); top = int(cells[index["top"]])
            width = int(cells[index["width"]]); height = int(cells[index["height"]])
        except (ValueError, IndexError):
            continue
        if width <= 0 or height <= 0:
            continue
        records.append(OCRRecord(text, max(0.0, conf), (left, top, left + width, top + height)))
    records.sort(key=lambda item: (item.box[1], item.box[0]))
    full_text = "\n".join(line.text for line in group_fn(records, settings.paddle_line_merge_y_ratio))
    return records, full_text

