from __future__ import annotations

"""Pure review text, range, and OCR-candidate presentation helpers."""

import difflib
import re
import unicodedata

from .models import AppSettings, Entry as WordEntry


def _review_editor_font_size(settings: AppSettings) -> int:
    """Review text font is fixed; image zoom must not resize editor typography."""
    return max(5, int(settings.review_entry_font_size))


def _entry_font_spec(family: str, size: int, bold: bool = False, italic: bool = False) -> tuple:
    """Return a Tk font tuple while keeping main/review typography independent."""
    styles: list[str] = []
    if bold:
        styles.append("bold")
    if italic:
        styles.append("italic")
    return (str(family or "TkDefaultFont"), int(size), *styles)


def _review_similarity_key(value: object) -> str:
    """Normalize a review/OCR string for visual similarity comparison.

    Full/half-width forms and case are normalized, while whitespace and
    punctuation are ignored. Letters (including accents), CJK characters and
    digits remain significant.
    """
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    kept: list[str] = []
    for ch in text:
        category = unicodedata.category(ch)
        if ch.isspace() or category.startswith("P") or category.startswith("Z"):
            continue
        kept.append(ch)
    return "".join(kept)


def _review_text_similarity(left: object, right: object) -> float | None:
    """Return 0..1 OCR/editor similarity, or None when either side is blank."""
    a = _review_similarity_key(left)
    b = _review_similarity_key(right)
    if not a or not b:
        return None
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _focused_review_character_tokens(value: object) -> tuple[str, ...]:
    """Parse comma-separated focused-review character tokens deterministically."""
    parts = [
        token.strip()
        for token in re.split(r"[,，]+", str(value or ""))
        if token.strip()
    ]
    return tuple(dict.fromkeys(parts))


def _focused_review_page_indices(value: object, total: int) -> list[int]:
    """Parse 1-based ranges such as 1-20,25,30-35; blank means all pages."""
    total = max(0, int(total))
    text = str(value or "").strip()
    if not text:
        return list(range(total))
    result: set[int] = set()
    for token in re.split(r"[,，;；\s]+", text):
        token = token.strip()
        if not token:
            continue
        match = re.fullmatch(r"(\d+)\s*[-–—~～]\s*(\d+)", token)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if end < start:
                start, end = end, start
            if start < 1 or end > total:
                raise ValueError(f"页面范围必须在 1–{total} 内。")
            result.update(range(start - 1, end))
            continue
        if not token.isdigit():
            raise ValueError("页面范围格式示例：1-20,25,30-35；留空表示全部页面。")
        page = int(token)
        if page < 1 or page > total:
            raise ValueError(f"页面范围必须在 1–{total} 内。")
        result.add(page - 1)
    return sorted(result)


def _focused_review_is_single_character(value: object) -> bool:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return len([char for char in text if not char.isspace()]) == 1


def _candidate_for_entry_from_list(
    entry: WordEntry, candidates: list[dict], *, y_tolerance: int,
) -> dict | None:
    """Match one PDIC row to OCR metadata using original-image X/Y."""
    if entry.candidate_id:
        for candidate in candidates:
            if str(candidate.get("candidate_id", "")) == entry.candidate_id:
                return candidate
    nearby: list[tuple[float, dict]] = []
    tolerance = max(4, int(y_tolerance))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("position_variant") or "refined") == "original":
            continue
        try:
            dx = abs(int(candidate.get("source_x", entry.x)) - int(entry.x))
            dy = abs(int(candidate.get("source_y", entry.y)) - int(entry.y))
        except (TypeError, ValueError):
            continue
        if dx <= 20 and dy <= tolerance:
            nearby.append((dy + dx * 0.1, candidate))
    return min(nearby, key=lambda item: item[0])[1] if nearby else None

def _candidate_word_for_ocr_source(candidate: dict | None, source: str) -> str:
    """Return the OCR lemma for one explicit review comparison source."""
    if not candidate:
        return ""
    key = str(source or "fusion").strip().lower()
    if key == "fusion":
        return str(candidate.get("word") or "").strip()
    side = candidate.get(key, {}) or {}
    if not isinstance(side, dict):
        return ""
    return str(side.get("lemma") or "").strip()


def _review_similarity_color(score: float | None) -> str:
    """Semantic background colour for one OCR option in the review panel."""
    if score is None:
        return "#f2f2f2"
    if score >= 0.98:
        return "#b7e1cd"
    if score >= 0.85:
        return "#d9ead3"
    if score >= 0.65:
        return "#fff2cc"
    if score >= 0.40:
        return "#fce5cd"
    return "#f4cccc"


def _candidate_choice_rows(candidate: dict | None) -> list[tuple[str, str, str, float | None, bool]]:
    """Return compact, deterministic OCR choices for one review candidate.

    The last boolean marks the fused/final row.  Engine rows are deliberately
    retained even when they recognize the same lemma: seeing agreement between
    PaddleOCR, Tesseract and Lens is useful context when editing on the page.
    """
    if not candidate:
        return []
    rows: list[tuple[str, str, str, float | None, bool]] = []
    for engine, label in (("paddle", "PaddleOCR"), ("tesseract", "Tesseract"), ("lens", "Google Lens")):
        side = candidate.get(engine, {}) or {}
        word = str(side.get("lemma") or "").strip()
        if not word:
            continue
        confidence = side.get("confidence")
        try:
            confidence_value = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_value = None
        rows.append((engine, label, word, confidence_value, False))
    final_word = str(candidate.get("word") or "").strip()
    if final_word:
        rows.append((str(candidate.get("final_engine") or "fusion"), "融合结果", final_word, None, True))
    return rows
