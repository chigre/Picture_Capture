from __future__ import annotations

"""Annotation-only dictionary alphabetical anomaly diagnostics.

Warnings are never rejection decisions. No cache/PDIC sidecars are written by
this calculation owner; the historical core passes current patchable helpers.
"""

from collections.abc import Callable
from typing import Any
import unicodedata
from ..models import Entry
from ..persistence.page_sections import PageSection


def alphabetical_sort_key(word: str, *, unicode_data: Any = unicodedata) -> str:
    """Approximate Spanish dictionary collation for anomaly detection only."""
    value = (word or "").casefold().strip()
    # Preserve ñ as distinct from n while stripping acute/diaeresis accents.
    value = value.replace("ñ", "\ue000")
    value = "".join(
        ch for ch in unicode_data.normalize("NFD", value)
        if unicode_data.category(ch) != "Mn"
    )
    value = value.replace("\ue000", "n~")
    return "".join(ch for ch in value if ch.isalpha() or ch == "~")


def annotate_alphabetical_warnings(
    report_columns: list[dict[str, Any]],
    page_sections: list[PageSection] | None = None,
    *,
    top_v: int | None = None,
    bottom_v: int | None = None,
    candidate_rows_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    axis_fn: Callable[[dict[str, Any] | None], int | None],
    sort_key_fn: Callable[[str], str],
    section_fn: Callable[..., int],
    normalize_fn: Callable[..., list[PageSection]],
) -> list[dict[str, Any]]:
    """Annotate, never reject, order anomalies along the real page reading path."""
    warnings: list[dict[str, Any]] = []
    effective_sections = None
    if page_sections and top_v is not None and bottom_v is not None:
        effective_sections = normalize_fn(page_sections, int(top_v), int(bottom_v))

    for engine in ("paddle", "tesseract", "lens"):
        seq: list[tuple[int, int, dict[str, Any], str]] = []
        for col in report_columns:
            diagnostics = (
                col.get("candidates", []) if engine == "paddle"
                else (col.get(engine, {}) or {}).get("candidates", [])
            )
            col_idx = int(col.get("column", 0))
            for cand in candidate_rows_fn(diagnostics):
                cand["alphabetical_warning"] = ""
                if not cand.get("accepted"):
                    continue
                lemma = str(cand.get("normalized_headword", ""))
                key = sort_key_fn(lemma)
                if not key:
                    continue
                axis_v = axis_fn(cand) or 0
                section_idx = (
                    section_fn(
                        axis_v, effective_sections, int(top_v), int(bottom_v),
                    )
                    if effective_sections is not None else 0
                )
                seq.append((section_idx, col_idx, cand, key))

        seq.sort(key=lambda item: (
            item[0], item[1], axis_fn(item[2]) or 0,
        ))
        for i, (section_idx, col_idx, cand, key) in enumerate(seq):
            prev_key = seq[i - 1][3] if i > 0 else ""
            next_key = seq[i + 1][3] if i + 1 < len(seq) else ""
            prev_lemma = str(seq[i - 1][2].get("normalized_headword", "")) if i > 0 else ""
            next_lemma = str(seq[i + 1][2].get("normalized_headword", "")) if i + 1 < len(seq) else ""
            warning = ""
            if prev_key and key < prev_key:
                warning = f"alphabetical_backtrack_vs:{prev_lemma}"
            elif prev_key and next_key and prev_key <= next_key and key > next_key:
                warning = f"alphabetical_forward_outlier_between:{prev_lemma}|{next_lemma}"
            if warning:
                cand["alphabetical_warning"] = warning
                warnings.append({
                    "engine": engine,
                    "section": section_idx + 1,
                    "column": col_idx,
                    "source_y": cand.get("source_y"),
                    "lemma": cand.get("normalized_headword", ""),
                    "warning": warning,
                })
    return warnings


def apply_alphabetical_warnings_to_entries(
    report_columns: list[dict[str, Any]], entries: list[Entry], tolerance: int = 5,
    *,
    candidate_rows_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> None:
    warning_candidates: list[tuple[str, int, str, str]] = []
    for col in report_columns:
        for engine, diagnostics in (
            ("paddle", col.get("candidates", [])),
            ("tesseract", (col.get("tesseract", {}) or {}).get("candidates", [])),
            ("lens", (col.get("lens", {}) or {}).get("candidates", [])),
        ):
            for cand in candidate_rows_fn(diagnostics):
                warning = str(cand.get("alphabetical_warning", ""))
                if warning and cand.get("accepted"):
                    warning_candidates.append((
                        engine, int(cand.get("source_y", 0)),
                        str(cand.get("normalized_headword", "")), warning,
                    ))
    for entry in entries:
        for engine, y, lemma, warning in warning_candidates:
            if entry.ocr_source == engine and entry.word.casefold() == lemma.casefold() and abs(entry.y - y) <= tolerance:
                entry.alphabetical_warning = warning
                break
