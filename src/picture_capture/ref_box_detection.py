"""Local, opt-in whole-image template matching for REF rectangles.

Samples are cropped from the user's image into local project storage only.
No scan, sample, template, or OCR content is sent over the network.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import uuid

import numpy as np
from PIL import Image

from .formats import pdic_path, read_pdic
from .page_sections import read_page_sections
from .ref_boxes import (
    RefBox, box_intersection_fraction, next_ref_id, read_ref_boxes,
    ref_box_ticket, ref_sample_root, write_ref_boxes,
)


def list_ref_samples(project_root: Path) -> list[Path]:
    folder = ref_sample_root(project_root)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.name.startswith("ref_sample_")
                  and p.suffix.lower() == ".png")


def add_ref_sample(image_path: Path, source_box: tuple[int, int, int, int]) -> Path:
    """Store only an explicitly user-selected rectangle; never a full scan."""
    page = Path(image_path)
    with Image.open(page) as source:
        x0, y0, x1, y1 = map(int, source_box)
        if not (0 <= x0 < x1 <= source.width and 0 <= y0 < y1 <= source.height):
            raise ValueError("REF template selection exceeds the page")
        if x1 - x0 < 4 or y1 - y0 < 4:
            raise ValueError("REF template crop is too small")
        sample = source.convert("RGB").crop((x0, y0, x1, y1))
    target_dir = ref_sample_root(page.parent)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"ref_sample_{uuid.uuid4().hex}.png"
    temp = target_dir / f".{target.stem}.tmp"
    try:
        sample.save(temp, format="PNG")
        temp.replace(target)
    finally:
        sample.close()
        temp.unlink(missing_ok=True)
    return target


def match_ref_templates(
    image: Image.Image, samples: list[Path], *,
    threshold: float = 0.88, max_results: int = 200,
) -> list[tuple[int, int, int, int]]:
    """Bounded multi-scale TM_CCOEFF_NORMED; returns non-overlapping boxes.

    Works with arbitrary colors/typography, not only blue backgrounds.
    Empty/constant samples are invalid; an unavailable cv2 dependency causes
    an explicit error rather than pretending the recognition was successful.
    """
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("自动 REF 识别需要 OpenCV，请安装项目的图像处理依赖") from exc
    if not 0.60 <= float(threshold) <= 0.999:
        raise ValueError("REF match threshold must be between 0.60 and 0.999")
    source = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = source.shape[:2]
    proposals: list[tuple[float, int, int, int, int]] = []
    for sample_path in samples:
        with Image.open(sample_path) as opened:
            source_template = np.asarray(opened.convert("RGB"), dtype=np.uint8)
        if min(source_template.shape[:2]) < 4 or float(source_template.std()) < 4.0:
            continue
        for factor in (0.85, 1.0, 1.15):
            sw = max(4, round(source_template.shape[1] * factor))
            sh = max(4, round(source_template.shape[0] * factor))
            if sw > width or sh > height:
                continue
            template = cv2.resize(source_template, (sw, sh), interpolation=cv2.INTER_AREA)
            if template.std() < 4.0:
                continue
            scores = cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED)
            # Never enumerate every pixel in a large saturated similarity map:
            # suppress one accepted peak at a time in score space.
            for _ in range(max_results):
                _, score, _, (xx, yy) = cv2.minMaxLoc(scores)
                if not np.isfinite(score) or score < threshold:
                    break
                proposals.append((float(score), xx, yy, sw, sh))
                pad_x, pad_y = max(1, round(sw * 0.65)), max(1, round(sh * 0.65))
                scores[max(0, yy-pad_y):min(scores.shape[0], yy+pad_y+1),
                       max(0, xx-pad_x):min(scores.shape[1], xx+pad_x+1)] = -1.0
    accepted: list[RefBox] = []
    for _, x, y, w, h in sorted(proposals, key=lambda row: (-row[0], row[2], row[1])):
        item = RefBox(len(accepted)+1, x, y, w, h, None)
        if any(box_intersection_fraction(item, other) > 0.25 for other in accepted):
            continue
        accepted.append(item)
        if len(accepted) >= max_results:
            break
    return [(p.x, p.y, p.w, p.h) for p in accepted]


def associate_ref_to_entry(
    image: Image.Image, entries: list, settings, page_index: int,
    sections, x: int, y: int, w: int, h: int,
) -> int | None:
    """Use the same SECTION/column/entry crop travel as word export.

    A REF inside an unowned previous-page continuation remains unlinked.
    """
    if not entries:
        return None
    from .processing_core import _base_entry_crop_pieces
    _ordered, pieces = _base_entry_crop_pieces(
        image, entries, settings, profile_page_index=page_index,
        page_sections=sections,
    )
    cx, cy = x + w / 2, y + h / 2
    matches = [
        p for p in pieces
        if p.entry_ref_index is not None and
        p.box[0] <= cx < p.box[2] and p.box[1] <= cy < p.box[3]
    ]
    if not matches:
        return None
    return matches[0].entry_ref_index


def detect_ref_boxes_page(image_path: Path, settings, page_index: int) -> dict:
    """Add non-overlapping REF matches, preserving every existing REF record."""
    page = Path(image_path)
    ticket = ref_box_ticket(page)
    existing = read_ref_boxes(page)
    samples = list_ref_samples(page.parent)
    if not samples:
        return {"status": "skipped_no_samples", "page": page.name, "added": 0}
    with Image.open(page) as opened:
        image = opened.convert("RGB")
    try:
        matches = match_ref_templates(
            image, samples,
            threshold=float(getattr(settings, "ref_match_threshold", 0.88)),
        )
        entries = read_pdic(pdic_path(page))
        sections = read_page_sections(page)
        proposed = list(existing)
        for x, y, w, h in matches:
            placeholder = RefBox(1, x, y, w, h, None)
            if any(box_intersection_fraction(placeholder, old) > 0.15 for old in proposed):
                continue
            ordinal = associate_ref_to_entry(
                image, entries, settings, page_index, sections, x, y, w, h,
            )
            proposed.append(RefBox(next_ref_id(proposed), x, y, w, h, ordinal, ""))
    finally:
        image.close()
    added = len(proposed) - len(existing)
    if added:
        write_ref_boxes(page, proposed, expected_ticket=ticket)
    return {"status": "changed" if added else "unchanged", "page": page.name, "added": added}


def detect_ref_boxes_job(image_path: str, settings, page_index: int) -> dict:
    try:
        return detect_ref_boxes_page(Path(image_path), settings, page_index)
    except Exception as exc:
        return {"status": "failed", "page": Path(image_path).name,
                "error": f"{type(exc).__name__}: {exc}", "added": 0}
