"""OCR geometry and conservative spatial grouping for illustrated dictionaries.

No column/indent/order assumptions. Detection makes *proposals*, never writes
PDIC or replaces human-confirmed groups. Similar aligned OCR text lines are
grouped locally; an isolated printed label remains a valid one-line group.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Callable

from PIL import Image

from .illustrated_entries import IllustratedEntry, make_entry
from .image_utils import normalize_page_rgb
from .ocr_channel import OcrChannelSession
from .ref_box_ocr import local_ref_ocr_plan


@dataclass(frozen=True)
class SpatialLine:
    text: str
    box: tuple[int, int, int, int]
    confidence: float = 0.0

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


def normalize_ocr_records(records, image_size: tuple[int, int]) -> list[SpatialLine]:
    width, height = image_size
    lines = []
    for record in records:
        text = str(getattr(record, "text", "") or "").strip()
        try:
            x0, y0, x1, y1 = (int(v) for v in record.box)
            confidence = float(getattr(record, "confidence", 0) or 0)
        except (ValueError, AttributeError, TypeError):
            continue
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(width, x1), min(height, y1)
        if text and x1 > x0 and y1 > y0:
            lines.append(SpatialLine(text, (x0, y0, x1, y1), confidence))
    return sorted(lines, key=lambda line: (line.box[1], line.box[0]))


def join_tesseract_words(lines: list[SpatialLine]) -> list[SpatialLine]:
    """Regroup word-level TSV records to printed lines without page columns."""
    ordered = sorted(lines, key=lambda row: ((row.box[1] + row.box[3]) / 2, row.box[0]))
    result: list[SpatialLine] = []
    for word in ordered:
        x0, y0, x1, y1 = word.box
        match = -1
        for i, line in enumerate(result):
            a, b, c, d = line.box
            overlap = min(y1, d) - max(y0, b)
            gap = x0 - c
            if (overlap >= .55 * min(word.height, line.height)
                    and -min(word.height, line.height) * .15 <= gap
                    <= max(word.height, line.height) * .85):
                match = i
                break
        if match < 0:
            result.append(word)
        else:
            prior = result[match]
            a, b, c, d = prior.box
            result[match] = SpatialLine(
                prior.text + " " + word.text,
                (min(a, x0), min(b, y0), max(c, x1), max(d, y1)),
                (prior.confidence + word.confidence) / 2,
            )
    return sorted(result, key=lambda line: (line.box[1], line.box[0]))


def group_spatial_lines(lines: list[SpatialLine], *,
                        max_lines: int = 10) -> list[list[SpatialLine]]:
    """Cluster compact, vertically successive labels; never use global Y sort.

    Candidate line must be close vertically, start near the same X or share a
    center, and sit below the current group's last printed line. This avoids
    merging neighboring labels in the same row, or distant caption blocks.
    """
    if not lines:
        return []
    groups: list[list[SpatialLine]] = []
    for row in sorted(lines, key=lambda v: (v.box[1], v.box[0])):
        x0, y0, x1, y1 = row.box
        best_index: int | None = None
        best_score = float("inf")
        for i, group in enumerate(groups):
            if len(group) >= max_lines:
                continue
            last = max(group, key=lambda v: v.box[3])
            lx0, ly0, lx1, ly1 = last.box
            scale = max(5.0, median(v.height for v in group + [row]))
            gap = y0 - ly1
            if not (-.10 * scale <= gap <= .95 * scale):
                continue
            group_center = median((v.box[0] + v.box[2]) / 2 for v in group)
            center = (x0 + x1) / 2
            left_align = abs(x0 - median(v.box[0] for v in group)) <= 1.20 * scale
            center_align = abs(center - group_center) <= 1.25 * scale
            overlap = max(0, min(lx1, x1) - max(lx0, x0))
            if not (left_align or center_align) or overlap <= 0:
                continue
            score = max(0.0, gap) / scale + abs(x0 - lx0) / (4 * scale)
            if score < best_score:
                best_index, best_score = i, score
        if best_index is None:
            groups.append([row])
        else:
            groups[best_index].append(row)
    return sorted(groups, key=lambda group: (min(v.box[1] for v in group),
                                               min(v.box[0] for v in group)))


def groups_to_entries(groups: list[list[SpatialLine]]) -> list[IllustratedEntry]:
    result = []
    for group in groups:
        ordered = sorted(group, key=lambda row: (row.box[1], row.box[0]))
        x0 = min(v.box[0] for v in ordered)
        y0 = min(v.box[1] for v in ordered)
        x1 = max(v.box[2] for v in ordered)
        y1 = max(v.box[3] for v in ordered)
        if x1 > x0 and y1 > y0:
            result.append(make_entry(
                x0, y0, x1 - x0, y1 - y0,
                lines=tuple(row.text for row in ordered), source="ocr",
            ))
    return result


def proposal_overlaps(existing: IllustratedEntry, proposed: IllustratedEntry) -> bool:
    left, top = max(existing.x, proposed.x), max(existing.y, proposed.y)
    right = min(existing.x + existing.w, proposed.x + proposed.w)
    bottom = min(existing.y + existing.h, proposed.y + proposed.h)
    common = max(0, right - left) * max(0, bottom - top)
    return common / max(1, min(existing.w * existing.h, proposed.w * proposed.h)) >= .45


def _session(settings, session_factory: Callable[..., Any]):
    plan = local_ref_ocr_plan(settings)
    if not plan.voting_engines:
        raise RuntimeError("请在共享 OCR 设置中启用本地 Paddle 或 Tesseract")
    return session_factory(settings, plan=plan)


def propose_page_entries(page: Path, settings: Any, *,
                         session_factory: Callable[..., Any] = OcrChannelSession
                         ) -> list[IllustratedEntry]:
    """Read-only full-page OCR. Never interprets illustration leader lines."""
    session = _session(settings, session_factory)
    with Image.open(page) as opened:
        image = normalize_page_rgb(opened)
    try:
        outcome = session.recognize_crop(image, tesseract_psm=11)
        candidates = [c for c in outcome.candidates
                      if c.engine in ("paddle", "tesseract") and c.records and not c.error]
        if not candidates:
            errors = [str(c.error) for c in outcome.candidates if c.error]
            if errors:
                raise RuntimeError("OCR 失败：" + errors[0])
            return []
        # Paddle returns recognized text-line rectangles. Tesseract produces
        # word boxes; combine them before multilingual label grouping.
        preferred = next((v for v in candidates if v.engine == "paddle"), candidates[0])
        lines = normalize_ocr_records(preferred.records, image.size)
        if preferred.engine == "tesseract":
            lines = join_tesseract_words(lines)
        return groups_to_entries(group_spatial_lines(lines))
    finally:
        image.close()


def ocr_one_group(page: Path, settings: Any, box: tuple[int, int, int, int],
                  *, session_factory: Callable[..., Any] = OcrChannelSession
                  ) -> tuple[str, ...]:
    session = _session(settings, session_factory)
    x, y, w, h = box
    with Image.open(page) as opened:
        image = normalize_page_rgb(opened)
    try:
        if min(x, y) < 0 or min(w, h) < 1 or x+w > image.width or y+h > image.height:
            raise ValueError("OCR 框超出原图")
        with image.crop((x, y, x+w, y+h)) as cropped:
            result = session.recognize_crop(cropped, tesseract_psm=6)
        candidates = [v for v in result.candidates if v.engine in ("paddle", "tesseract")
                      and v.records and not v.error]
        if not candidates:
            return ()
        chosen = next((v for v in candidates if v.engine == "paddle"), candidates[0])
        lines = normalize_ocr_records(chosen.records, (w, h))
        if chosen.engine == "tesseract":
            lines = join_tesseract_words(lines)
        return tuple(v.text for v in sorted(lines, key=lambda v: (v.box[1], v.box[0])))
    finally:
        image.close()
