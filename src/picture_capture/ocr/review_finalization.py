"""Final selection deduplication, Entry conversion and project quality report.

Native owner for the OCR post-arbitration review lifecycle; all historical
private patch seams, model identities, thresholds and the process lock are
bound explicitly at call time by paddle_headwords_core.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from ..models import Entry
import re
import unicodedata


@dataclass(frozen=True)
class ReviewFinalizationDeps:
    """Existing OCR hooks, limits, persisted Entry class and shared lock."""
    _is_single_cjk_ideograph: object
    _review_candidate_box_height: object
    _review_candidates_same_cjk_glyph: object
    _review_candidate_priority: object
    _normalize_cjk_review_word: object
    _looks_like_multi_cjk_headword: object
    _review_candidates_same_cjk_compound: object
    _candidate_has_single_cjk_identity: object
    _candidate_line_height: object
    _boxes_same_large_cjk_region: object
    _single_cjk_duplicate_pair: object
    _FINAL_LINE_DEDUP_RATIO: object
    _SINGLE_CJK_LINE_DEDUP_RATIO: object
    Entry: object
    _QUALITY_SUMMARY_LOCK: object
    _QUALITY_HEADER: object
    _tsv_clean: object
    _atomic_write_text: object


def _review_candidate_box_height(
    deps: ReviewFinalizationDeps, item: dict[str, Any]) -> int:
    box = item.get("box") or []
    if isinstance(box, (list, tuple)) and len(box) == 4:
        try:
            return max(1, int(box[3]) - int(box[1]))
        except Exception:
            pass
    return 1


def _review_candidates_same_cjk_glyph(
    deps: ReviewFinalizationDeps, left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return True when two selected rows are duplicate detections of one Han glyph."""
    _is_single_cjk_ideograph = deps._is_single_cjk_ideograph
    _review_candidate_box_height = deps._review_candidate_box_height

    if int(left.get("column", -1)) != int(right.get("column", -2)):
        return False
    lw = str(left.get("word", "")).strip()
    rw = str(right.get("word", "")).strip()
    if not (_is_single_cjk_ideograph(lw) and _is_single_cjk_ideograph(rw)):
        return False

    lbox = left.get("box") or []
    rbox = right.get("box") or []
    lh = _review_candidate_box_height(left)
    rh = _review_candidate_box_height(right)
    max_h = max(lh, rh, 1)
    dy = abs(
        int(left.get("_axis_v", left.get("source_y", 0)))
        - int(right.get("_axis_v", right.get("source_y", 0)))
    )

    box_same_row = False
    if isinstance(lbox, (list, tuple)) and len(lbox) == 4 and isinstance(rbox, (list, tuple)) and len(rbox) == 4:
        ly0, ly1 = int(lbox[1]), int(lbox[3])
        ry0, ry1 = int(rbox[1]), int(rbox[3])
        overlap = max(0, min(ly1, ry1) - max(ly0, ry0))
        center_delta = abs(((ly0 + ly1) / 2.0) - ((ry0 + ry1) / 2.0))
        box_same_row = (
            overlap >= min(lh, rh) * 0.20
            or center_delta <= max_h * 0.58
        )

    # Same recognized character gets a slightly wider marker-Y allowance; OCR
    # disagreements still merge when their boxes clearly cover the same glyph.
    if lw == rw and dy <= max(8, round(max_h * 0.95)):
        return True
    return box_same_row and dy <= max(10, round(max_h * 1.10))


def _review_candidate_priority(
    deps: ReviewFinalizationDeps, item: dict[str, Any]) -> tuple[float, float, float, float]:
    manual = 1.0 if item.get("manual_override") else 0.0
    engine_votes = 0.0
    for engine in ("paddle", "tesseract", "lens"):
        side = item.get(engine, {}) or {}
        if side.get("y") is not None:
            engine_votes += 1.0
        if side.get("accepted") is True:
            engine_votes += 0.35
    return (
        manual,
        engine_votes,
        float(item.get("score") or 0.0),
        float(item.get("confidence") or 0.0),
    )


def _normalize_cjk_review_word(
    deps: ReviewFinalizationDeps, word: str) -> str:
    """Return a Unicode-safe normalized review word for CJK duplicate checks."""
    normalized = unicodedata.normalize("NFKC", str(word or "")).strip()
    normalized = re.sub(r"^[【〔［\[]\s*", "", normalized)
    normalized = re.sub(r"\s*[】〕］\]]$", "", normalized)
    normalized = re.sub(r"(?<=[㐀-鿿])\s+(?=[㐀-鿿])", "", normalized)
    return normalized.strip()


def _looks_like_multi_cjk_headword(
    deps: ReviewFinalizationDeps, word: str) -> bool:
    _is_single_cjk_ideograph = deps._is_single_cjk_ideograph
    _normalize_cjk_review_word = deps._normalize_cjk_review_word
    normalized = _normalize_cjk_review_word(word)
    if not normalized or _is_single_cjk_ideograph(normalized):
        return False
    chars = [ch for ch in normalized if _is_single_cjk_ideograph(ch)]
    return len(chars) >= 2 and len(normalized) <= 16


def _review_candidates_same_cjk_compound(
    deps: ReviewFinalizationDeps, left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return True when two selected rows are duplicate detections of one CJK compound headword.

    This handles ordinary-size Chinese bracketed compounds such as 【並肩】 that
    can be emitted twice by slightly different OCR pairings.  To avoid merging
    neighbouring real entries, require the normalized lemma to match exactly and
    the physical boxes to overlap strongly or have almost identical centres.
    """
    _review_candidate_box_height = deps._review_candidate_box_height
    _normalize_cjk_review_word = deps._normalize_cjk_review_word
    _looks_like_multi_cjk_headword = deps._looks_like_multi_cjk_headword

    if int(left.get("column", -1)) != int(right.get("column", -2)):
        return False
    lw = _normalize_cjk_review_word(str(left.get("word", "")))
    rw = _normalize_cjk_review_word(str(right.get("word", "")))
    if not lw or lw != rw:
        return False
    if not (_looks_like_multi_cjk_headword(lw) and _looks_like_multi_cjk_headword(rw)):
        return False

    lbox = left.get("box") or []
    rbox = right.get("box") or []
    lh = _review_candidate_box_height(left)
    rh = _review_candidate_box_height(right)
    max_h = max(lh, rh, 1)
    dy = abs(
        int(left.get("_axis_v", left.get("source_y", 0)))
        - int(right.get("_axis_v", right.get("source_y", 0)))
    )

    if not (isinstance(lbox, (list, tuple)) and len(lbox) == 4 and isinstance(rbox, (list, tuple)) and len(rbox) == 4):
        return dy <= max(6, round(max_h * 0.42))

    ly0, ly1 = int(lbox[1]), int(lbox[3])
    ry0, ry1 = int(rbox[1]), int(rbox[3])
    overlap = max(0, min(ly1, ry1) - max(ly0, ry0))
    center_delta = abs(((ly0 + ly1) / 2.0) - ((ry0 + ry1) / 2.0))
    min_h = max(1, min(lh, rh))
    strong_same_row = (
        overlap >= min_h * 0.45
        or center_delta <= max_h * 0.35
    )
    return strong_same_row and dy <= max(8, round(max_h * 0.55))


def _candidate_has_single_cjk_identity(
    deps: ReviewFinalizationDeps, item: dict[str, Any]) -> bool:
    """Return True when review metadata identifies a large single-Han headword.

    Do not rely only on the final OCR word: the two OCR engines can disagree on
    the glyph while still pointing at the same oversized dictionary headword.
    Parser traces and each engine's lemma/raw/corrected forms are therefore also
    inspected.
    """
    _is_single_cjk_ideograph = deps._is_single_cjk_ideograph
    _normalize_cjk_review_word = deps._normalize_cjk_review_word

    values = [str(item.get("word", ""))]
    for engine in ("paddle", "tesseract", "lens"):
        side = item.get(engine, {}) or {}
        values.extend(str(side.get(key, "")) for key in ("lemma", "raw", "corrected"))
        trace = side.get("parser_trace", []) or []
        if any("chinese_single_character" in str(step) for step in trace):
            return True
    return any(_is_single_cjk_ideograph(_normalize_cjk_review_word(value)) for value in values if value)


def _candidate_line_height(
    deps: ReviewFinalizationDeps, item: dict[str, Any]) -> float:
    _review_candidate_box_height = deps._review_candidate_box_height
    try:
        value = float(item.get("line_height_reference") or 0.0)
    except Exception:
        value = 0.0
    if value > 0:
        return value
    # Legacy/manual rows do not carry the normal-line reference.  Their box is
    # still useful as a conservative fallback, but avoid treating a huge glyph
    # height as the normal line height.
    return float(max(1, _review_candidate_box_height(item)))


def _boxes_same_large_cjk_region(
    deps: ReviewFinalizationDeps, left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Check whether two candidates plausibly cover the same oversized glyph."""
    _review_candidate_box_height = deps._review_candidate_box_height

    lbox = left.get("box") or []
    rbox = right.get("box") or []
    if not (isinstance(lbox, (list, tuple)) and len(lbox) == 4 and isinstance(rbox, (list, tuple)) and len(rbox) == 4):
        return True
    lh = _review_candidate_box_height(left)
    rh = _review_candidate_box_height(right)
    ly0, ly1 = int(lbox[1]), int(lbox[3])
    ry0, ry1 = int(rbox[1]), int(rbox[3])
    overlap = max(0, min(ly1, ry1) - max(ly0, ry0))
    center_delta = abs(((ly0 + ly1) / 2.0) - ((ry0 + ry1) / 2.0))
    return (
        overlap >= max(1, min(lh, rh) * 0.18)
        or center_delta <= max(lh, rh) * 0.62
    )


def _single_cjk_duplicate_pair(
    deps: ReviewFinalizationDeps, left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Use a wider Y tolerance for duplicate large single-character entries.

    OCR and visual-projection channels can refine the separator independently,
    leaving two lines farther apart than the ordinary 0.22-line threshold.  A
    single-character pair may therefore use 0.55 of a normal text line, but only
    when geometry still says both candidates belong to the same large glyph.
    """
    _candidate_has_single_cjk_identity = deps._candidate_has_single_cjk_identity
    _candidate_line_height = deps._candidate_line_height
    _boxes_same_large_cjk_region = deps._boxes_same_large_cjk_region
    _SINGLE_CJK_LINE_DEDUP_RATIO = deps._SINGLE_CJK_LINE_DEDUP_RATIO

    if int(left.get("column", -1)) != int(right.get("column", -2)):
        return False
    if not (_candidate_has_single_cjk_identity(left) and _candidate_has_single_cjk_identity(right)):
        return False
    normal_line = max(_candidate_line_height(left), _candidate_line_height(right), 1.0)
    dy = abs(
        int(left.get("_axis_v", left.get("source_y", 0)))
        - int(right.get("_axis_v", right.get("source_y", 0)))
    )
    tolerance = max(4, round(normal_line * _SINGLE_CJK_LINE_DEDUP_RATIO))
    return dy <= tolerance and _boxes_same_large_cjk_region(left, right)


def _deduplicate_selected_cjk_review_candidates(
    deps: ReviewFinalizationDeps, review_candidates: list[dict[str, Any]]) -> int:
    """Suppress duplicate final separator lines with type-aware Y tolerances.

    Ordinary/bracketed entries keep the strict ~0.22-normal-line rule.  Large
    single-character CJK heads first get a dedicated OCR+visual-channel check
    with a wider ~0.55-normal-line allowance, because their two refinement paths
    can legitimately land farther apart while still describing one glyph.

    For ordinary/bracketed duplicates the final separator keeps the *lower*
    safe Y.  For oversized single-CJK duplicates we keep the *upper* boundary:
    the lower visual/OCR duplicate can fall inside the same entry around
    pronunciation/radical metadata (e.g. between 播 ba and Bộ:), while the upper
    line is the true entry-start separator.
    """
    _review_candidate_box_height = deps._review_candidate_box_height
    _review_candidate_priority = deps._review_candidate_priority
    _single_cjk_duplicate_pair = deps._single_cjk_duplicate_pair
    _FINAL_LINE_DEDUP_RATIO = deps._FINAL_LINE_DEDUP_RATIO

    merged = 0
    by_column: dict[int, list[dict[str, Any]]] = {}
    for item in review_candidates:
        if item.get("selected"):
            by_column.setdefault(int(item.get("column", 0)), []).append(item)

    def _threshold(left: dict[str, Any], right: dict[str, Any]) -> int:
        values: list[int] = []
        for item in (left, right):
            try:
                value = int(item.get("line_dedup_tolerance") or 0)
            except Exception:
                value = 0
            if value > 0:
                values.append(value)
        if values:
            return max(2, max(values))
        # Compatibility fallback for manually constructed/legacy cached rows.
        # Box height is in source-image pixels, so 0.22 of the smaller box is a
        # conservative approximation of one fifth of a normal text line.
        approx_line = min(_review_candidate_box_height(left), _review_candidate_box_height(right))
        return max(2, round(approx_line * _FINAL_LINE_DEDUP_RATIO))

    def _merge_selected_rows(
        left: dict[str, Any], right: dict[str, Any], *, single_cjk_special: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        keeper, loser = (left, right) if _review_candidate_priority(left) >= _review_candidate_priority(right) else (right, left)
        # Copy one complete temporary-axis+source point; never mix individual
        # coordinates after rotation. Ordinary duplicates keep the lower/closer
        # marker, but oversized single-CJK duplicates keep the upper entry-start
        # boundary so a lower visual confirmation cannot move the separator into
        # pronunciation/radical metadata inside the same entry.
        left_v = int(left.get("_axis_v", left.get("source_y", 0)))
        right_v = int(right.get("_axis_v", right.get("source_y", 0)))
        if single_cjk_special:
            position_row = left if left_v <= right_v else right
        else:
            position_row = left if left_v >= right_v else right
        for key in (
            "_axis_u", "_axis_v", "source_x", "source_y",
            "refined_source_y", "_coarse_axis_v", "coarse_source_x",
            "coarse_source_y", "_anchor_axis_v", "anchor_source_x",
            "anchor_source_y",
        ):
            if position_row.get(key) is not None:
                keeper[key] = position_row.get(key)
        for engine in ("paddle", "tesseract", "lens"):
            if not (keeper.get(engine, {}) or {}).get("y") and (loser.get(engine, {}) or {}).get("y") is not None:
                keeper[engine] = dict(loser.get(engine, {}) or {})
        issues = list(keeper.get("issue_types", []) or [])
        if "NEAR_Y_DUPLICATE_MERGED" not in issues:
            issues.append("NEAR_Y_DUPLICATE_MERGED")
        if single_cjk_special and "SINGLE_CJK_DUPLICATE_MERGED" not in issues:
            issues.append("SINGLE_CJK_DUPLICATE_MERGED")
        keeper["issue_types"] = issues
        reason = "+single_cjk_duplicate_merge" if single_cjk_special else "+near_y_duplicate_merge"
        keeper["decision_reason"] = str(keeper.get("decision_reason", "")) + reason
        loser["selected"] = False
        loser["needs_review"] = False
        loser_issues = list(loser.get("issue_types", []) or [])
        if "NEAR_Y_DUPLICATE_SUPPRESSED" not in loser_issues:
            loser_issues.append("NEAR_Y_DUPLICATE_SUPPRESSED")
        loser["issue_types"] = loser_issues
        loser["decision_reason"] = "near_y_duplicate_suppressed"
        return keeper, loser

    for rows in by_column.values():
        rows.sort(
            key=lambda item: int(
                item.get("_axis_v", item.get("source_y", 0))
            )
        )
        i = 0
        while i < len(rows) - 1:
            left, right = rows[i], rows[i + 1]
            dy = abs(
        int(left.get("_axis_v", left.get("source_y", 0)))
        - int(right.get("_axis_v", right.get("source_y", 0)))
    )
            single_cjk_special = _single_cjk_duplicate_pair(left, right)
            tolerance = _threshold(left, right)
            if not single_cjk_special and dy > tolerance:
                i += 1
                continue
            _keeper, loser = _merge_selected_rows(
                left, right, single_cjk_special=single_cjk_special,
            )
            merged += 1
            rows.remove(loser)
            rows.sort(
            key=lambda item: int(
                item.get("_axis_v", item.get("source_y", 0))
            )
        )
            i = max(0, i - 1)
    return merged


def _entries_from_review_candidates(
    deps: ReviewFinalizationDeps, review_candidates: list[dict[str, Any]]) -> list[Entry]:
    _candidate_has_single_cjk_identity = deps._candidate_has_single_cjk_identity
    Entry = deps.Entry
    entries: list[Entry] = []
    selected = [item for item in review_candidates if item.get("selected")]
    selected.sort(key=lambda item: (
        int(item.get("column", 0)),
        int(item.get("_axis_v", item.get("source_y", 0))),
        int(item.get("_axis_u", item.get("source_x", 0))),
    ))

    def _positive_float(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    for item in selected:
        engine_name = str(item.get("final_engine", ""))
        side = item.get(engine_name, {}) or {} if engine_name else {}
        features = dict(side.get("features", {}) or {})
        box = side.get("box") or item.get("box") or []
        box_height: float | None = None
        if isinstance(box, (list, tuple)) and len(box) == 4:
            try:
                box_height = float(max(1, int(box[3]) - int(box[1])))
            except (TypeError, ValueError):
                box_height = None

        line_height_reference = _positive_float(item.get("line_height_reference"))
        visual_run_height = _positive_float(features.get("cjk_visual_run_height"))
        leading_height_ratio = _positive_float(features.get("leading_record_height_ratio"))
        single_cjk = _candidate_has_single_cjk_identity(item)
        oversized_cjk = bool(
            single_cjk
            and (
                bool(features.get("cjk_oversized_recovery"))
                or (leading_height_ratio is not None and leading_height_ratio >= 1.45)
                or (
                    visual_run_height is not None
                    and line_height_reference is not None
                    and visual_run_height / line_height_reference >= 1.45
                )
                or (
                    box_height is not None
                    and line_height_reference is not None
                    and box_height / line_height_reference >= 1.45
                )
            )
        )

        entries.append(Entry(
            word=str(item.get("word", "")),
            x=int(item.get("source_x", 0)),
            y=int(item.get("source_y", 0)),
            confidence=(float(item.get("confidence")) if item.get("confidence") is not None else None),
            ocr_source=engine_name,
            alphabetical_warning=str(item.get("alphabetical_warning", "")),
            candidate_id=str(item.get("candidate_id", "")),
            final_engine=engine_name,
            issue_type=",".join(str(x) for x in item.get("issue_types", []) or []),
            parser_score=(float(item.get("score")) if item.get("score") is not None else None),
            manually_selected=bool(item.get("manual_override", False)),
            ocr_box_height=box_height,
            ocr_line_height_reference=line_height_reference,
            ocr_visual_run_height=visual_run_height,
            ocr_leading_height_ratio=leading_height_ratio,
            ocr_single_cjk=bool(single_cjk),
            ocr_oversized_cjk=oversized_cjk,
        ))
    return entries


def _update_project_quality_summary(
    deps: ReviewFinalizationDeps, 
    cache_path: Path, summary: dict[str, Any], review_candidates: list[dict[str, Any]],
) -> None:
    _QUALITY_SUMMARY_LOCK = deps._QUALITY_SUMMARY_LOCK
    _QUALITY_HEADER = deps._QUALITY_HEADER
    _tsv_clean = deps._tsv_clean
    _atomic_write_text = deps._atomic_write_text
    path = cache_path.parent / "_quality_summary.tsv"
    with _QUALITY_SUMMARY_LOCK:
        rows: dict[str, list[str]] = {}
        if path.exists():
            try:
                for line in path.read_text(encoding="utf-8-sig").splitlines()[1:]:
                    cols = line.split("\t")
                    if cols and cols[0]:
                        rows[cols[0]] = cols
            except Exception:
                rows = {}
        page = cache_path.stem
        issues = sum(1 for x in review_candidates if x.get("issue_types"))
        needs_review = sum(1 for x in review_candidates if x.get("needs_review"))
        selected = sum(1 for x in review_candidates if x.get("selected"))
        vals = [
            page, f"{float(summary.get('agreement', 0.0)):.4f}", summary.get("candidate_union", 0),
            summary.get("paired", 0), summary.get("exact", 0), summary.get("similar", 0),
            summary.get("conflict", 0), summary.get("paddle_only", 0), summary.get("tesseract_only", 0),
            summary.get("lens_used", 0), summary.get("lens_only", 0), summary.get("triple_agree", 0),
            summary.get("multi_engine_majority", 0),
            selected, issues, needs_review,
        ]
        rows[page] = [_tsv_clean(v) for v in vals]
        output = [_QUALITY_HEADER] + ["\t".join(rows[key]) for key in sorted(rows)]
        _atomic_write_text(path, "\n".join(output) + "\n", encoding="utf-8")

