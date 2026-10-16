"""Offline, bounded OCR of existing REF rectangles only.

Consumes existing .rbox files, processes unfilled REF text from exact source
pixels, and atomically updates only .rbox. Never OCRs the rest of the page,
saves PDIC/PPP/OCR cache, uploads to Lens or replaces human-entered text.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from .image_utils import normalize_page_rgb
from .ocr_channel import (
    OcrChannelPlan, OcrChannelSession, OcrTextChoice,
    choose_ocr_text, resolve_ocr_channel_plan,
)
from .ref_boxes import (
    RefBox, read_ref_boxes, ref_box_path, ref_box_ticket, write_ref_boxes,
)


def local_ref_ocr_plan(settings: Any) -> OcrChannelPlan:
    """Reuse the configured shared channel without remote Lens uploads."""
    configured = resolve_ocr_channel_plan(settings)
    engines = tuple(x for x in configured.enabled_engines if x in ("paddle", "tesseract"))
    voting = tuple(x for x in configured.voting_engines if x in engines)
    return OcrChannelPlan(enabled_engines=engines, voting_engines=voting, lens_mode="off")


def _page_digest(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_ref_ocr_text(text: str) -> str:
    """Trim OCR line whitespace but keep actual multi-line REF content."""
    return "\n".join(line.strip() for line in str(text or "").splitlines()).strip()


def extract_ref_text(text: str, pattern: str) -> str:
    """Regex extraction: first participating capture wins; otherwise full match.

    Empty patterns and no-match cases leave the OCR text unchanged. A malformed
    configured expression raises ValueError before any REF file is written.
    """
    import re

    original = normalize_ref_ocr_text(text)
    pattern = str(pattern or "")
    if not pattern.strip() or not original:
        return original
    if len(pattern) > 2000:
        raise ValueError("OCR REF extraction regex must be at most 2000 characters")
    try:
        match = re.search(pattern, original, flags=re.DOTALL)
    except re.error as exc:
        raise ValueError(f"Invalid OCR REF extraction regex: {exc}") from exc
    if match is None:
        return original
    captures = match.groups()
    if captures:
        extracted = next((group for group in captures if group is not None), "")
    else:
        extracted = match.group(0)
    return normalize_ref_ocr_text(extracted) or original

def ocr_ref_boxes_page(
    image_path: Path, settings: Any, *,
    session_factory: Callable[..., Any] = OcrChannelSession,
) -> dict[str, Any]:
    """Fill only empty REF text fields, preserving all other records unchanged.

    Missing .rbox => no file creation. One guarded atomic write per page,
    even for multiple REF crops. Failure in one crop retains already accepted
    text from other crops; no OCR result => no write. Source image and .rbox
    both receive exact byte-level change detection before final publication.
    """
    page = Path(image_path)
    rbox = ref_box_path(page)
    result: dict[str, Any] = {
        "page": page.name, "status": "unchanged",
        "filled": 0, "skipped_existing": 0, "blank": 0, "errors": 0,
    }
    if not rbox.is_file():
        result["status"] = "skipped_no_ref"
        return result
    ticket = ref_box_ticket(page)
    boxes = read_ref_boxes(page)
    if not boxes:
        result["status"] = "skipped_no_ref"
        return result
    remaining = [b for b in boxes if not b.text.strip()]
    result["skipped_existing"] = len(boxes) - len(remaining)
    if not remaining:
        result["status"] = "skipped_filled"
        return result
    plan = local_ref_ocr_plan(settings)
    if not plan.enabled_engines or not plan.voting_engines:
        result["status"] = "skipped_no_local_engine"
        return result
    before_image = _page_digest(page)
    updates: dict[int, str] = {}
    with Image.open(page) as opened:
        image = normalize_page_rgb(opened)
    try:
        session = session_factory(settings, plan=plan)
        for box in remaining:
            # Be strict: coordinates from another image/EXIF state must not
            # cause OCR to borrow text from a neighboring word or page.
            if (box.x < 0 or box.y < 0 or box.w < 1 or box.h < 1
                    or box.x + box.w > image.width
                    or box.y + box.h > image.height):
                result["errors"] += 1
                continue
            try:
                cropped = image.crop((box.x, box.y, box.x + box.w, box.y + box.h))
                try:
                    inference = session.recognize_crop(cropped, tesseract_psm=7)
                finally:
                    cropped.close()
                choices = [
                    OcrTextChoice(candidate.engine, normalize_ref_ocr_text(candidate.text),
                                  candidate.confidence)
                    for candidate in inference.successful
                    if candidate.engine in plan.voting_engines
                ]
                selected, _agreed = choose_ocr_text(plan, choices)
                if selected and selected.text:
                    extracted = extract_ref_text(
                        selected.text, getattr(settings, "ref_ocr_extract_regex", ""),
                    )
                    if extracted:
                        updates[box.id] = extracted
                    else:
                        result["blank"] += 1
                else:
                    result["blank"] += 1
            except Exception:
                # Keep the remaining successful per-box results; do not put
                # engine error text into .rbox. The batch reports error count.
                result["errors"] += 1
    finally:
        image.close()
    if not updates:
        result["status"] = "unchanged"
        return result
    if _page_digest(page) != before_image:
        raise RuntimeError("REF OCR source image changed during recognition; nothing saved")
    # A hash guard prevents replacing a concurrent manual edit to any field.
    if ref_box_ticket(page) != ticket:
        raise RuntimeError("REF OCR file changed outside editor; nothing saved")
    proposed: list[RefBox] = [
        replace(box, text=updates[box.id]) if box.id in updates and not box.text.strip()
        else box for box in boxes
    ]
    write_ref_boxes(page, proposed, expected_ticket=ticket)
    result["filled"] = len(updates)
    result["status"] = "changed"
    return result


def ocr_ref_boxes_job(image_path: str, settings: Any) -> dict[str, Any]:
    try:
        return ocr_ref_boxes_page(Path(image_path), settings)
    except Exception as exc:
        return {"page": Path(image_path).name, "status": "failed",
                "filled": 0, "errors": 1,
                "error": f"{type(exc).__name__}: {exc}"}
