"""OCR multi-engine candidate matching and adjudication.

Canonical leaf for the entire Paddle/Tesseract/Lens matching chain:
Unicode-aware lemma normalization, sequence-Y pairing, third-opinion
enrichment, candidate scoring, vote arbitration, original/source coordinate
placement and summary. Core retains original signatures and patchable hooks;
all operations are passed per call without a core import or global installer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING
import difflib
import re
import unicodedata

from ..models import AppSettings

if TYPE_CHECKING:
    from ..processing import Geometry


@dataclass(frozen=True)
class OcrPairingDeps:
    """Call-time OCR compatibility callbacks and pure matching primitives."""
    _candidate_axis_v: object
    _candidate_rows: object
    _alignment_key: object
    _lemma_similarity: object
    _orthographic_similarity: object
    _eligible_alignment_rows: object
    _candidate_pair_score: object
    _pair_ocr_candidates: object
    _pairs_need_lens: object
    _make_ocr_pair: object
    _copy_candidate_to_pair: object
    _pair_with_lens_candidates: object
    _engine_quality: object
    _stable_candidate_id: object
    _issues_for_pair: object
    _arbitrate_pair: object
    _apply_pair_engine_position: object
    _agreement_summary: object


def _alignment_key(
    deps: OcrPairingDeps, word: str) -> str:
    """Return a Unicode-safe OCR alignment key.

    v2.8.1 accidentally reduced alignment to ASCII letters/digits, which made
    every Han headword collapse to the empty key.  That could mis-pair Chinese
    OCR rows and, in turn, leave two review candidates for one physical glyph.
    Preserve all Unicode alphanumeric characters while still discarding
    punctuation/spacing and combining marks.
    """
    value = unicodedata.normalize("NFKD", word or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return "".join(ch for ch in value if ch.isalnum()).casefold()


def _lemma_similarity(
    deps: OcrPairingDeps, left: str, right: str) -> float:
    _alignment_key = deps._alignment_key
    a = _alignment_key(left)
    b = _alignment_key(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _orthographic_similarity(
    deps: OcrPairingDeps, left: str, right: str) -> float:
    """Compare final spellings while preserving meaningful Spanish diacritics."""
    a = re.sub(r"[^\wáéíóúüñ]+", "", unicodedata.normalize("NFC", left or "").casefold(), flags=re.UNICODE)
    b = re.sub(r"[^\wáéíóúüñ]+", "", unicodedata.normalize("NFC", right or "").casefold(), flags=re.UNICODE)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _eligible_alignment_rows(
    deps: OcrPairingDeps, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _candidate_axis_v = deps._candidate_axis_v
    _candidate_rows = deps._candidate_rows
    result: list[dict[str, Any]] = []
    for item in _candidate_rows(rows):
        features = item.get("features", {}) or {}
        # Every left-edge OCR row is retained for v2.0 manual review, even if the
        # grammar parser rejected it. Accepted candidates are always retained.
        if item.get("accepted") or features.get("at_left"):
            result.append(item)
    return sorted(result, key=lambda x: _candidate_axis_v(x) or 0)


def _candidate_pair_score(
    deps: OcrPairingDeps, p: dict[str, Any], t: dict[str, Any], tolerance: int) -> float:
    _candidate_axis_v = deps._candidate_axis_v
    _lemma_similarity = deps._lemma_similarity
    sim = _lemma_similarity(str(p.get("normalized_headword", "")), str(t.get("normalized_headword", "")))
    dy = abs((_candidate_axis_v(p) or 0) - (_candidate_axis_v(t) or 0))
    y_score = max(0.0, 1.0 - dy / max(1.0, tolerance * 2.5))
    return 0.72 * sim + 0.28 * y_score


def _pair_ocr_candidates(
    deps: OcrPairingDeps, 
    paddle_diagnostics: list[dict[str, Any]],
    tess_diagnostics: list[dict[str, Any]],
    tolerance: int,
    min_similarity: float = 0.55,
) -> list[dict[str, Any]]:
    """Align Paddle/Tesseract candidate sequences using lemma order + Y.

    SequenceMatcher first anchors stable equal subsequences. Replace blocks are
    then matched by a combined lemma-similarity/Y score. This prevents a single
    missing OCR row from shifting every subsequent nearest-Y pairing.
    """
    _candidate_axis_v = deps._candidate_axis_v
    _alignment_key = deps._alignment_key
    _lemma_similarity = deps._lemma_similarity
    _eligible_alignment_rows = deps._eligible_alignment_rows
    _candidate_pair_score = deps._candidate_pair_score
    _make_ocr_pair = deps._make_ocr_pair
    paddle = _eligible_alignment_rows(paddle_diagnostics)
    tess = _eligible_alignment_rows(tess_diagnostics)
    pkeys = [_alignment_key(str(x.get("normalized_headword", ""))) for x in paddle]
    tkeys = [_alignment_key(str(x.get("normalized_headword", ""))) for x in tess]
    matcher = difflib.SequenceMatcher(None, pkeys, tkeys, autojunk=False)
    paired: list[tuple[dict[str, Any] | None, dict[str, Any] | None, str]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                paired.append((paddle[i1 + offset], tess[j1 + offset], "sequence_exact"))
            continue
        pblock = list(range(i1, i2))
        tblock = list(range(j1, j2))
        if tag == "replace" and pblock and tblock:
            options: list[tuple[float, int, int]] = []
            for pi in pblock:
                for tj in tblock:
                    score = _candidate_pair_score(paddle[pi], tess[tj], tolerance)
                    dy = abs(
                        int(_candidate_axis_v(paddle[pi]) or 0)
                        - int(_candidate_axis_v(tess[tj]) or 0)
                    )
                    sim = _lemma_similarity(
                        str(paddle[pi].get("normalized_headword", "")),
                        str(tess[tj].get("normalized_headword", "")),
                    )
                    # Very similar words may drift a little in Y; dissimilar
                    # words must be geometrically close to be considered a pair.
                    if score >= max(0.34, min_similarity * 0.76) and (dy <= tolerance * 2.5 or sim >= max(0.68, min_similarity)):
                        options.append((score, pi, tj))
            used_p: set[int] = set(); used_t: set[int] = set()
            for score, pi, tj in sorted(options, reverse=True):
                if pi in used_p or tj in used_t:
                    continue
                used_p.add(pi); used_t.add(tj)
                paired.append((paddle[pi], tess[tj], "sequence_y_similar"))
            for pi in pblock:
                if pi not in used_p:
                    paired.append((paddle[pi], None, "sequence_paddle_only"))
            for tj in tblock:
                if tj not in used_t:
                    paired.append((None, tess[tj], "sequence_tesseract_only"))
        elif tag == "delete":
            paired.extend((paddle[pi], None, "sequence_paddle_only") for pi in pblock)
        elif tag == "insert":
            paired.extend((None, tess[tj], "sequence_tesseract_only") for tj in tblock)

    result = [_make_ocr_pair(p, t, method) for p, t, method in paired]
    result.sort(key=lambda item: min(
        int(item.get("paddle_y") or 10**9), int(item.get("tesseract_y") or 10**9)
    ))
    return result


def _pairs_need_lens(
    deps: OcrPairingDeps, pairs: list[dict[str, Any]]) -> bool:
    """Return whether the remote third opinion could change/review a decision."""
    for pair in pairs:
        pa = pair.get("paddle_accepted") is True
        ta = pair.get("tesseract_accepted") is True
        if pair.get("lemma_compare") in {"different", "similar"} and (pa or ta):
            return True
        if pair.get("status_compare") == "different":
            return True
        if (pa or ta) and (pair.get("paddle_y") is None or pair.get("tesseract_y") is None):
            return True
        confidences = [
            float(value) for value in (pair.get("paddle_conf"), pair.get("tesseract_conf"))
            if value is not None
        ]
        if (pa or ta) and confidences and min(confidences) < 0.80:
            return True
    return False


def _make_ocr_pair(
    deps: OcrPairingDeps, 
    p: dict[str, Any] | None,
    t: dict[str, Any] | None,
    alignment_method: str = "",
) -> dict[str, Any]:
    _candidate_axis_v = deps._candidate_axis_v
    _lemma_similarity = deps._lemma_similarity
    py = _candidate_axis_v(p)
    ty = _candidate_axis_v(t)
    pl = str(p.get("normalized_headword", "")) if p else ""
    tl = str(t.get("normalized_headword", "")) if t else ""
    sim = _lemma_similarity(pl, tl) if p and t else 0.0
    if p and t:
        if pl and tl and pl.casefold() == tl.casefold():
            lemma_compare = "same"
        elif pl and tl and sim >= 0.82:
            lemma_compare = "similar"
        elif pl and tl:
            lemma_compare = "different"
        else:
            lemma_compare = "missing_lemma"
        pa = bool(p.get("accepted")); ta = bool(t.get("accepted"))
        status_compare = "same" if pa == ta else "different"
        if lemma_compare == "same" and status_compare == "same":
            reason = "agree"
        elif lemma_compare in {"different", "similar"}:
            reason = "lemma_conflict" if lemma_compare == "different" else "lemma_variant"
        else:
            reason = "acceptance_conflict"
    elif p:
        lemma_compare = "paddle_only"; status_compare = "paddle_only"; reason = "paddle_only"
    else:
        lemma_compare = "tesseract_only"; status_compare = "tesseract_only"; reason = "tesseract_only"
    return {
        "paddle_y": py,
        "paddle_source_x": p.get("source_x") if p else None,
        "paddle_source_y": p.get("source_y") if p else None,
        "paddle_coarse_source_x": p.get("coarse_source_x") if p else None,
        "paddle_coarse_source_y": p.get("coarse_source_y") if p else None,
        "paddle_anchor_source_x": p.get("anchor_source_x") if p else None,
        "paddle_anchor_source_y": p.get("anchor_source_y") if p else None,
        "paddle_coarse_y": (
            int(p.get("_coarse_axis_v", py)) if p and py is not None else None
        ),
        "paddle_anchor_y": (
            int(p.get("_anchor_axis_v", py)) if p and py is not None else None
        ),
        "paddle_separator_refinement": dict(p.get("separator_refinement", {}) or {}) if p else {},
        "paddle_image_boundary_match": dict(p.get("image_boundary_match", {}) or {}) if p else {},
        "paddle_box": p.get("box") if p else None,
        "paddle_conf": p.get("confidence") if p else None,
        "paddle_accepted": bool(p.get("accepted")) if p else None,
        "paddle_score": p.get("score") if p else None,
        "paddle_lemma": pl,
        "paddle_raw": str(p.get("raw_headword", "")) if p else "",
        "paddle_corrected": str(p.get("corrected_headword", "")) if p else "",
        "paddle_pos": str(p.get("pos_cue", "")) if p else "",
        "paddle_repairs": list(p.get("ocr_repairs", []) or []) if p else [],
        "paddle_text": str(p.get("text", "")) if p else "",
        "paddle_reject_reason": str(p.get("reject_reason", "")) if p else "",
        "paddle_features": dict(p.get("features", {}) or {}) if p else {},
        "paddle_parser_trace": list(p.get("parser_trace", []) or []) if p else [],
        "paddle_bug_types": list(p.get("bug_types", []) or []) if p else [],
        "paddle_alphabetical_warning": str(p.get("alphabetical_warning", "")) if p else "",
        "tesseract_y": ty,
        "tesseract_source_x": t.get("source_x") if t else None,
        "tesseract_source_y": t.get("source_y") if t else None,
        "tesseract_coarse_source_x": t.get("coarse_source_x") if t else None,
        "tesseract_coarse_source_y": t.get("coarse_source_y") if t else None,
        "tesseract_anchor_source_x": t.get("anchor_source_x") if t else None,
        "tesseract_anchor_source_y": t.get("anchor_source_y") if t else None,
        "tesseract_coarse_y": (
            int(t.get("_coarse_axis_v", ty)) if t and ty is not None else None
        ),
        "tesseract_anchor_y": (
            int(t.get("_anchor_axis_v", ty)) if t and ty is not None else None
        ),
        "tesseract_separator_refinement": dict(t.get("separator_refinement", {}) or {}) if t else {},
        "tesseract_image_boundary_match": dict(t.get("image_boundary_match", {}) or {}) if t else {},
        "tesseract_box": t.get("box") if t else None,
        "tesseract_conf": t.get("confidence") if t else None,
        "tesseract_accepted": bool(t.get("accepted")) if t else None,
        "tesseract_score": t.get("score") if t else None,
        "tesseract_lemma": tl,
        "tesseract_raw": str(t.get("raw_headword", "")) if t else "",
        "tesseract_corrected": str(t.get("corrected_headword", "")) if t else "",
        "tesseract_pos": str(t.get("pos_cue", "")) if t else "",
        "tesseract_repairs": list(t.get("ocr_repairs", []) or []) if t else [],
        "tesseract_text": str(t.get("text", "")) if t else "",
        "tesseract_reject_reason": str(t.get("reject_reason", "")) if t else "",
        "tesseract_features": dict(t.get("features", {}) or {}) if t else {},
        "tesseract_parser_trace": list(t.get("parser_trace", []) or []) if t else [],
        "tesseract_bug_types": list(t.get("bug_types", []) or []) if t else [],
        "tesseract_alphabetical_warning": str(t.get("alphabetical_warning", "")) if t else "",
        "lens_y": None,
        "lens_source_x": None,
        "lens_source_y": None,
        "lens_coarse_y": None,
        "lens_anchor_y": None,
        "lens_separator_refinement": {},
        "lens_image_boundary_match": {},
        "lens_box": None,
        "lens_conf": None,
        "lens_accepted": None,
        "lens_score": None,
        "lens_lemma": "",
        "lens_raw": "",
        "lens_corrected": "",
        "lens_pos": "",
        "lens_repairs": [],
        "lens_text": "",
        "lens_reject_reason": "",
        "lens_features": {},
        "lens_parser_trace": [],
        "lens_bug_types": [],
        "lens_alphabetical_warning": "",
        "delta_y": (ty - py) if py is not None and ty is not None else None,
        "lemma_similarity": round(sim, 4) if p and t else "",
        "lemma_compare": lemma_compare,
        "status_compare": status_compare,
        "alignment_method": alignment_method,
        "reason": reason,
    }


def _copy_candidate_to_pair(
    deps: OcrPairingDeps, pair: dict[str, Any], prefix: str, candidate: dict[str, Any]) -> None:
    _candidate_axis_v = deps._candidate_axis_v
    axis_v = _candidate_axis_v(candidate)
    if axis_v is None:
        axis_v = 0
    pair[f"{prefix}_y"] = axis_v
    pair[f"{prefix}_coarse_y"] = int(candidate.get("_coarse_axis_v", axis_v))
    pair[f"{prefix}_anchor_y"] = int(candidate.get("_anchor_axis_v", candidate.get("_coarse_axis_v", axis_v)))
    for suffix in (
        "source_x", "source_y", "coarse_source_x", "coarse_source_y",
        "anchor_source_x", "anchor_source_y",
    ):
        pair[f"{prefix}_{suffix}"] = candidate.get(suffix)
    pair[f"{prefix}_box"] = candidate.get("box")
    pair[f"{prefix}_separator_refinement"] = dict(candidate.get("separator_refinement", {}) or {})
    pair[f"{prefix}_image_boundary_match"] = dict(candidate.get("image_boundary_match", {}) or {})
    pair[f"{prefix}_conf"] = candidate.get("confidence")
    pair[f"{prefix}_accepted"] = bool(candidate.get("accepted"))
    pair[f"{prefix}_score"] = candidate.get("score")
    pair[f"{prefix}_lemma"] = str(candidate.get("normalized_headword", ""))
    pair[f"{prefix}_raw"] = str(candidate.get("raw_headword", ""))
    pair[f"{prefix}_corrected"] = str(candidate.get("corrected_headword", ""))
    pair[f"{prefix}_pos"] = str(candidate.get("pos_cue", ""))
    pair[f"{prefix}_repairs"] = list(candidate.get("ocr_repairs", []) or [])
    pair[f"{prefix}_text"] = str(candidate.get("text", ""))
    pair[f"{prefix}_reject_reason"] = str(candidate.get("reject_reason", ""))
    pair[f"{prefix}_features"] = dict(candidate.get("features", {}) or {})
    pair[f"{prefix}_parser_trace"] = list(candidate.get("parser_trace", []) or [])
    pair[f"{prefix}_bug_types"] = list(candidate.get("bug_types", []) or [])
    pair[f"{prefix}_alphabetical_warning"] = str(candidate.get("alphabetical_warning", ""))


def _pair_with_lens_candidates(
    deps: OcrPairingDeps, 
    pairs: list[dict[str, Any]],
    lens_diagnostics: list[dict[str, Any]],
    tolerance: int,
    min_similarity: float,
) -> list[dict[str, Any]]:
    """Attach Lens rows to the existing Paddle/Tesseract sequence alignment."""
    _candidate_axis_v = deps._candidate_axis_v
    _lemma_similarity = deps._lemma_similarity
    _eligible_alignment_rows = deps._eligible_alignment_rows
    _make_ocr_pair = deps._make_ocr_pair
    _copy_candidate_to_pair = deps._copy_candidate_to_pair
    lens_rows = _eligible_alignment_rows(lens_diagnostics)
    used: set[int] = set()
    for pair in pairs:
        base_y_values = [pair.get("paddle_y"), pair.get("tesseract_y")]
        base_y_values = [int(value) for value in base_y_values if value is not None]
        if not base_y_values:
            continue
        base_y = round(sum(base_y_values) / len(base_y_values))
        base_words = [str(pair.get("paddle_lemma") or ""), str(pair.get("tesseract_lemma") or "")]
        options: list[tuple[float, int]] = []
        for index, candidate in enumerate(lens_rows):
            if index in used:
                continue
            cy = _candidate_axis_v(candidate) or 0
            lemma = str(candidate.get("normalized_headword", ""))
            similarity = max((_lemma_similarity(lemma, word) for word in base_words if word), default=0.0)
            dy = abs(cy - base_y)
            y_score = max(0.0, 1.0 - dy / max(1.0, tolerance * 2.5))
            score = 0.72 * similarity + 0.28 * y_score
            if score >= max(0.34, min_similarity * 0.76) and (dy <= tolerance * 2.5 or similarity >= 0.68):
                options.append((score, index))
        if options:
            _, index = max(options)
            used.add(index)
            _copy_candidate_to_pair(pair, "lens", lens_rows[index])
            pair["lens_alignment_method"] = "sequence_y_similar"

    for index, candidate in enumerate(lens_rows):
        if index in used:
            continue
        pair = _make_ocr_pair(None, None, "sequence_lens_only")
        _copy_candidate_to_pair(pair, "lens", candidate)
        pair.update({
            "lemma_compare": "lens_only",
            "status_compare": "lens_only",
            "reason": "lens_only",
            "lens_alignment_method": "sequence_lens_only",
        })
        pairs.append(pair)
    pairs.sort(key=lambda item: min(
        int(value) for value in (item.get("paddle_y"), item.get("tesseract_y"), item.get("lens_y"))
        if value is not None
    ))
    return pairs


def _engine_quality(
    deps: OcrPairingDeps, pair: dict[str, Any], prefix: str) -> float:
    accepted = pair.get(f"{prefix}_accepted") is True
    score = float(pair.get(f"{prefix}_score") or 0.0)
    conf = float(pair.get(f"{prefix}_conf") or 0.0)
    features = pair.get(f"{prefix}_features", {}) or {}
    repairs = pair.get(f"{prefix}_repairs", []) or []
    q = score + 2.0 * conf + (1.0 if accepted else 0.0)
    if features.get("structural_cue"):
        q += 1.0
    if features.get("strong_visual_fallback"):
        q += 0.35
    if features.get("peer_typography_match"):
        q += 0.30
    boundary = pair.get(f"{prefix}_image_boundary_match", {}) or {}
    if isinstance(boundary, dict) and boundary:
        try:
            boundary_strength = max(
                0.0, min(1.0, float(boundary.get("strength") or 0.0))
            )
        except (TypeError, ValueError):
            boundary_strength = 0.0
        # Boundary detection is independent of OCR recognition and parser
        # semantics. Reward a mutually matched blank->ink transition modestly;
        # it should break close ties, not overpower a strong semantic mismatch.
        q += 0.20 + 0.35 * boundary_strength
    if features.get("forced_accept"):
        q += 1.2
    if features.get("forced_reject"):
        q -= 5.0
    q -= min(0.9, 0.08 * len(repairs))
    return q


def _stable_candidate_id(
    deps: OcrPairingDeps, column: int, y: int, ptext: str, ttext: str) -> str:
    # Manual checkbox choices should survive small OCR spelling/bbox changes on
    # a forced refresh. Dictionary rows are far more than 10 source pixels apart,
    # so a quantized Y + column is stable without relying on OCR text.
    qy = int(round(int(y) / 10.0) * 10)
    return f"c{column+1}-y{qy}"


def _issues_for_pair(
    deps: OcrPairingDeps, pair: dict[str, Any], chosen: str, needs_review: bool) -> list[str]:
    _lemma_similarity = deps._lemma_similarity
    issues: list[str] = []
    reason = str(pair.get("reason", ""))
    if reason == "paddle_only": issues.append("PADDLE_ONLY")
    if reason == "tesseract_only": issues.append("TESSERACT_ONLY")
    if reason == "lens_only": issues.append("LENS_ONLY")
    if pair.get("lemma_compare") == "different": issues.append("OCR_CONFLICT")
    elif pair.get("lemma_compare") == "similar": issues.append("OCR_VARIANT")
    if pair.get("status_compare") == "different": issues.append("ACCEPTANCE_CONFLICT")
    if pair.get("lens_y") is not None:
        lens_word = str(pair.get("lens_lemma") or "")
        other_words = [str(pair.get(f"{engine}_lemma") or "") for engine in ("paddle", "tesseract")]
        similarities = [_lemma_similarity(lens_word, word) for word in other_words if word]
        if similarities and max(similarities) < 0.82:
            issues.append("LENS_DISAGREEMENT")
    repairs = list(pair.get(f"{chosen}_repairs", []) or []) if chosen else []
    bug_types = list(pair.get(f"{chosen}_bug_types", []) or []) if chosen else []
    issues.extend(str(x) for x in bug_types)
    for repair in repairs:
        if repair == "MULTILINE_POS" or repair.startswith("MULTILINE_STATE_JOIN"):
            issues.append("MULTILINE_POS")
        if repair == "RIGHT_FRAGMENT_ABSORBED":
            issues.append("SPLIT_OCR_BOX")
    if repairs:
        issues.append("OCR_REPAIR")
    conf = float(pair.get(f"{chosen}_conf") or 0.0) if chosen else 0.0
    if chosen and conf < 0.80:
        issues.append("LOW_CONFIDENCE")
    warning = str(pair.get(f"{chosen}_alphabetical_warning", "")) if chosen else ""
    if warning:
        issues.append("ALPHABETICAL_WARNING")
    reject_reason = str(pair.get(f"{chosen}_reject_reason", "")) if chosen else ""
    reject_map = {
        "lemma_parse_failed": "LEMMA_PARSE_FAILED",
        "missing_pos_inflection_descriptor_or_symbol": "MISSING_STRUCTURE",
        "continuation_fragment": "CONTINUATION_FRAGMENT",
        "marker_glyph_ocr_noise": "MARKER_GLYPH_NOISE",
        "internal_article_symbol": "INTERNAL_ARTICLE_STRUCTURE",
        "internal_relation_label": "INTERNAL_ARTICLE_STRUCTURE",
        "score_below_threshold": "LOW_PARSER_SCORE",
        "not_at_column_left": "NOT_AT_LEFT",
        "internal_locution": "INTERNAL_LOCUTION",
    }
    if reject_reason in reject_map:
        issues.append(reject_map[reject_reason])
    score = float(pair.get(f"{chosen}_score") or 0.0) if chosen else 0.0
    if chosen and score < 5.5:
        issues.append("LOW_PARSER_SCORE")
    if needs_review:
        issues.append("NEEDS_REVIEW")
    return list(dict.fromkeys(issues))


def _arbitrate_pair(
    deps: OcrPairingDeps, 
    pair: dict[str, Any],
    column: int,
    canonical_u: int,
    settings: AppSettings,
    *,
    geometry: "Geometry" | None = None,
) -> dict[str, Any]:
    _orthographic_similarity = deps._orthographic_similarity
    _engine_quality = deps._engine_quality
    _stable_candidate_id = deps._stable_candidate_id
    _issues_for_pair = deps._issues_for_pair
    has_p = pair.get("paddle_y") is not None
    has_t = pair.get("tesseract_y") is not None
    has_l = pair.get("lens_y") is not None
    lens_can_vote = str(settings.paddle_lens_mode or "off").lower() != "diagnostic"
    pq = _engine_quality(pair, "paddle") if has_p else -999.0
    tq = _engine_quality(pair, "tesseract") if has_t else -999.0
    lq = _engine_quality(pair, "lens") if has_l else -999.0
    pa = pair.get("paddle_accepted") is True
    ta = pair.get("tesseract_accepted") is True
    sim = float(pair.get("lemma_similarity") or 0.0)
    chosen = ""
    needs_review = False
    decision_reason = ""

    if has_p and has_t:
        if pair.get("lemma_compare") == "same":
            chosen = "paddle" if pq >= tq else "tesseract"
            decision_reason = "dual_agree_higher_quality"
        elif pair.get("lemma_compare") == "similar":
            chosen = "paddle" if pq >= tq else "tesseract"
            decision_reason = "dual_similar_higher_quality"
            needs_review = abs(pq - tq) < settings.paddle_conflict_review_margin
        else:
            if pa != ta:
                chosen = "paddle" if pa else "tesseract"
                decision_reason = "acceptance_wins_conflict"
            else:
                chosen = "paddle" if pq >= tq else "tesseract"
                decision_reason = "conflict_higher_quality"
                needs_review = bool(pa and ta) or abs(pq - tq) < settings.paddle_conflict_review_margin
    elif has_p:
        chosen = "paddle"; decision_reason = "paddle_only"
    elif has_t:
        chosen = "tesseract"; decision_reason = "tesseract_only"
    elif has_l:
        if lens_can_vote:
            chosen = "lens"; decision_reason = "lens_only"
        else:
            decision_reason = "lens_diagnostic_only"

    # Lens acts as a third vote. When it agrees with one side of a real P/T
    # conflict, the agreement cluster wins; when all three agree, quality picks
    # the cleanest spelling. A lone Lens disagreement never silently overturns
    # two agreeing local engines.
    if has_l and lens_can_vote and (has_p or has_t):
        lens_word = str(pair.get("lens_lemma") or "")
        local_engines = [engine for engine, present in (("paddle", has_p), ("tesseract", has_t)) if present]
        agreeing_local = [
            engine for engine in local_engines
            if _orthographic_similarity(lens_word, str(pair.get(f"{engine}_lemma") or "")) >= 0.94
        ]
        if agreeing_local:
            # If both local engines agree with Lens, this is full consensus. If
            # only one agrees, Lens resolves the local conflict in its favour.
            cluster = agreeing_local + ["lens"]
            qualities = {"paddle": pq, "tesseract": tq, "lens": lq}
            chosen = max(cluster, key=lambda engine_name: qualities[engine_name])
            decision_reason = (
                "three_engine_agree_higher_quality"
                if len(agreeing_local) == len(local_engines) and len(local_engines) == 2
                else "lens_breaks_local_conflict"
            )
            if decision_reason == "lens_breaks_local_conflict":
                needs_review = False
        elif len(local_engines) >= 2 and _orthographic_similarity(
            str(pair.get("paddle_lemma") or ""), str(pair.get("tesseract_lemma") or "")
        ) >= 0.94:
            # Two agreeing local engines outweigh a disagreeing remote result.
            needs_review = bool(pair.get("lens_accepted") is True and lq >= max(pq, tq) - settings.paddle_conflict_review_margin)
            decision_reason = "local_consensus_over_lens"
        else:
            needs_review = bool(pair.get("lens_accepted") is True or needs_review)

    selected = bool(pair.get(f"{chosen}_accepted") is True) if chosen else False
    # When both OCR engines independently agree on the same/similar left-edge
    # lemma, a lost POS glyph should not automatically erase the entry.  Permit
    # a conservative visual-consensus rescue only for high-confidence rows whose
    # rejection reason is specifically missing structure.
    if has_p and has_t and not selected and sim >= 0.90:
        preasons = {str(pair.get("paddle_reject_reason", "")), str(pair.get("tesseract_reject_reason", ""))}
        pfeat = pair.get("paddle_features", {}) or {}; tfeat = pair.get("tesseract_features", {}) or {}
        high_conf = min(float(pair.get("paddle_conf") or 0.0), float(pair.get("tesseract_conf") or 0.0)) >= 0.85
        visual = bool(pfeat.get("strong_visual_fallback") or tfeat.get("strong_visual_fallback"))
        if preasons <= {"missing_pos_inflection_descriptor_or_symbol", ""} and high_conf and visual:
            selected = True
            decision_reason = "dual_consensus_visual_rescue"
            needs_review = True
    # Evidence-fusion v3: a parser rejection is not equivalent to "not a
    # headword".  OCR text, local image-boundary geometry and visual/structural
    # evidence are independent observations.  Rescue only when at least two
    # independent evidence families agree, and never override explicit/hard
    # negative semantics.  Every rescue remains review-visible.
    if chosen and not selected:
        chosen_features = dict(pair.get(f"{chosen}_features", {}) or {})
        chosen_reason = str(pair.get(f"{chosen}_reject_reason", "") or "")
        hard_negative_reasons = {
            "user_reject_rule",
            "not_at_column_left",
            "above_header_cutoff",
            "continuation_fragment",
            "marker_glyph_ocr_noise",
            "internal_article_symbol",
            "internal_relation_label",
            "internal_locution",
            "incompatible_headword_script",
            "cjk_single_headword_disabled",
            "cjk_bracketed_headword_disabled",
        }
        soft_reasons = {
            "",
            "missing_pos_inflection_descriptor_or_symbol",
            "missing_selected_tail_structure",
            "score_below_threshold",
            "missing_structure_or_visual_cue",
            "candidate_rejected",
            "cjk_single_needs_stronger_visual_evidence",
            "cjk_single_not_visually_prominent",
            "cjk_bracket_needs_visual_evidence",
        }
        chosen_conf = float(pair.get(f"{chosen}_conf") or 0.0)
        boundary = dict(pair.get(f"{chosen}_image_boundary_match", {}) or {})
        boundary_supported = bool(
            boundary
            or chosen_features.get("image_boundary_supported")
        )
        strong_visual = bool(
            chosen_features.get("strong_visual_fallback")
            or chosen_features.get("ordinary_strong_edge_visual_rescue")
            or chosen_features.get("visual_entry_marker")
            or chosen_features.get("configured_marker_evidence")
            or chosen_features.get("numbered_prefix_evidence")
            or chosen_features.get("cjk_single_strong_visual")
            or chosen_features.get("cjk_visual_projection_rescue")
            or chosen_features.get("cjk_visual_projection_confirmed")
            or chosen_features.get("peer_typography_match")
        )
        explicit_structure = bool(
            chosen_features.get("structural_cue")
            or chosen_features.get("front_structure_cue")
            or chosen_features.get("tail_structure_satisfied")
        )
        no_hard_negative = bool(
            chosen_reason not in hard_negative_reasons
            and not chosen_features.get("forced_reject")
        )

        dual_reasons = {
            str(pair.get("paddle_reject_reason", "") or ""),
            str(pair.get("tesseract_reject_reason", "") or ""),
        } if has_p and has_t else set()
        dual_soft = bool(
            has_p and has_t
            and dual_reasons <= soft_reasons
            and not (dual_reasons & hard_negative_reasons)
        )

        # Two independent OCR engines that agree on the lemma plus an image
        # boundary are strong enough to survive a missing POS/structure glyph.
        # This is especially useful on dense Latin dictionaries where the
        # headword is clear but a tiny POS token is lost by both OCR parsers.
        if (
            has_p and has_t
            and sim >= 0.94
            and dual_soft
            and no_hard_negative
            and boundary_supported
            and min(
                float(pair.get("paddle_conf") or 0.0),
                float(pair.get("tesseract_conf") or 0.0),
            ) >= 0.88
            and bool((pair.get("paddle_features", {}) or {}).get("at_left"))
            and bool((pair.get("tesseract_features", {}) or {}).get("at_left"))
        ):
            selected = True
            decision_reason = "dual_consensus_boundary_rescue"
            needs_review = True
        # A single OCR engine may be rescued only by explicit/strong visual
        # evidence (marker, numbered prefix, oversized CJK, strong typography)
        # *and* an independent local image boundary.  Generic bold text alone
        # is deliberately insufficient.
        elif (
            chosen_reason in soft_reasons
            and no_hard_negative
            and boundary_supported
            and strong_visual
            and chosen_conf >= 0.68
            and bool(chosen_features.get("at_left", True))
            and (
                explicit_structure
                or chosen_features.get("visual_entry_marker")
                or chosen_features.get("configured_marker_evidence")
                or chosen_features.get("numbered_prefix_evidence")
                or chosen_features.get("cjk_single_strong_visual")
                or chosen_features.get("cjk_visual_projection_rescue")
                or chosen_conf >= 0.82
            )
        ):
            selected = True
            decision_reason = "multi_evidence_visual_boundary_rescue"
            needs_review = True

    # Arbitration may accept a strong Tesseract-only entry without the legacy
    # rescue switch; this is the core v2.0 dual-engine behaviour.
    features = pair.get(f"{chosen}_features", {}) or {} if chosen else {}
    if chosen in {"tesseract", "lens"} and features.get("structural_cue"):
        selected = bool(pair.get(f"{chosen}_accepted") is True)

    y = int(pair.get(f"{chosen}_y") or pair.get("paddle_y") or pair.get("tesseract_y") or pair.get("lens_y") or 0)
    lemma = str(pair.get(f"{chosen}_lemma") or pair.get("paddle_lemma") or pair.get("tesseract_lemma") or pair.get("lens_lemma") or "")
    conf = float(pair.get(f"{chosen}_conf") or 0.0) if chosen else 0.0
    score = float(pair.get(f"{chosen}_score") or 0.0) if chosen else 0.0
    box = pair.get(f"{chosen}_box") or pair.get("paddle_box") or pair.get("tesseract_box") or pair.get("lens_box")
    coarse_y = int(
        pair.get(f"{chosen}_coarse_y")
        or pair.get("paddle_coarse_y")
        or pair.get("tesseract_coarse_y")
        or pair.get("lens_coarse_y")
        or y
    )
    anchor_y = int(
        pair.get(f"{chosen}_anchor_y")
        or pair.get("paddle_anchor_y")
        or pair.get("tesseract_anchor_y")
        or pair.get("lens_anchor_y")
        or coarse_y
    )
    separator_refinement = dict(
        pair.get(f"{chosen}_separator_refinement")
        or pair.get("paddle_separator_refinement")
        or pair.get("tesseract_separator_refinement")
        or pair.get("lens_separator_refinement")
        or {}
    )
    image_boundary_match = dict(
        pair.get(f"{chosen}_image_boundary_match")
        or pair.get("paddle_image_boundary_match")
        or pair.get("tesseract_image_boundary_match")
        or pair.get("lens_image_boundary_match")
        or {}
    )
    issues = _issues_for_pair(pair, chosen, needs_review)
    if decision_reason == "dual_consensus_visual_rescue" and "DUAL_CONSENSUS_RESCUE" not in issues:
        issues.append("DUAL_CONSENSUS_RESCUE")
    if decision_reason == "dual_consensus_boundary_rescue" and "DUAL_BOUNDARY_RESCUE" not in issues:
        issues.append("DUAL_BOUNDARY_RESCUE")
    if decision_reason == "multi_evidence_visual_boundary_rescue" and "MULTI_EVIDENCE_RESCUE" not in issues:
        issues.append("MULTI_EVIDENCE_RESCUE")
    candidate_id = _stable_candidate_id(
        column, y, str(pair.get("paddle_text", "")), str(pair.get("tesseract_text", ""))
    )
    if geometry is not None:
        refined_u = int(geometry.x_at(column, y))
        source_x, source_y = geometry.canonical_to_source(refined_u, y)
        coarse_u = int(geometry.x_at(column, coarse_y))
        coarse_source_x, coarse_source_y = geometry.canonical_to_source(
            coarse_u, coarse_y
        )
        anchor_u = int(geometry.x_at(column, anchor_y))
        anchor_source_x, anchor_source_y = geometry.canonical_to_source(
            anchor_u, anchor_y
        )
    else:
        refined_u = int(canonical_u)
        source_x, source_y = int(canonical_u), int(y)
        coarse_u = int(canonical_u)
        coarse_source_x, coarse_source_y = int(canonical_u), int(coarse_y)
        anchor_u = int(canonical_u)
        anchor_source_x, anchor_source_y = int(canonical_u), int(anchor_y)

    return {
        "candidate_id": candidate_id,
        "column": column,
        "coordinate_space": "source_image_pixels",
        "_axis_u": int(refined_u),
        "_axis_v": int(y),
        "_coarse_axis_v": int(coarse_y),
        "_anchor_axis_v": int(anchor_y),
        "source_x": int(source_x),
        "source_y": int(source_y),
        "refined_source_y": int(source_y),
        "coarse_source_x": int(coarse_source_x),
        "coarse_source_y": int(coarse_source_y),
        "anchor_source_x": int(anchor_source_x),
        "anchor_source_y": int(anchor_source_y),
        "box": box,
        "original_box": list(box) if isinstance(box, (list, tuple)) and len(box) == 4 else box,
        "separator_refinement": separator_refinement,
        "image_boundary_match": image_boundary_match,
        "position_variant": "refined",
        "selected": selected,
        "word": lemma,
        "final_engine": chosen,
        "confidence": round(conf, 6),
        "score": round(score, 3),
        "quality_paddle": round(pq, 3) if has_p else None,
        "quality_tesseract": round(tq, 3) if has_t else None,
        "quality_lens": round(lq, 3) if has_l else None,
        "needs_review": needs_review,
        "issue_types": issues,
        "decision_reason": decision_reason,
        "alphabetical_warning": str(pair.get(f"{chosen}_alphabetical_warning", "")) if chosen else "",
        "lemma_similarity": sim,
        "paddle": {
            "source_x": pair.get("paddle_source_x"),
            "source_y": (
                pair.get("paddle_source_y")
                if pair.get("paddle_source_y") is not None
                else pair.get("paddle_y")
            ),
            "y": (
                pair.get("paddle_source_y")
                if pair.get("paddle_source_y") is not None
                else pair.get("paddle_y")
            ),
            "box": pair.get("paddle_box"), "confidence": pair.get("paddle_conf"),
            "accepted": pair.get("paddle_accepted"), "score": pair.get("paddle_score"), "lemma": pair.get("paddle_lemma"),
            "raw": pair.get("paddle_raw"), "corrected": pair.get("paddle_corrected"), "POS": pair.get("paddle_pos"),
            "repairs": pair.get("paddle_repairs"), "text": pair.get("paddle_text"), "reason": pair.get("paddle_reject_reason"),
            "parser_trace": pair.get("paddle_parser_trace"),
            "features": dict(pair.get("paddle_features", {}) or {}),
        },
        "tesseract": {
            "source_x": pair.get("tesseract_source_x"),
            "source_y": (
                pair.get("tesseract_source_y")
                if pair.get("tesseract_source_y") is not None
                else pair.get("tesseract_y")
            ),
            "y": (
                pair.get("tesseract_source_y")
                if pair.get("tesseract_source_y") is not None
                else pair.get("tesseract_y")
            ),
            "box": pair.get("tesseract_box"), "confidence": pair.get("tesseract_conf"),
            "accepted": pair.get("tesseract_accepted"), "score": pair.get("tesseract_score"), "lemma": pair.get("tesseract_lemma"),
            "raw": pair.get("tesseract_raw"), "corrected": pair.get("tesseract_corrected"), "POS": pair.get("tesseract_pos"),
            "repairs": pair.get("tesseract_repairs"), "text": pair.get("tesseract_text"), "reason": pair.get("tesseract_reject_reason"),
            "parser_trace": pair.get("tesseract_parser_trace"),
            "features": dict(pair.get("tesseract_features", {}) or {}),
        },
        "lens": {
            "source_x": pair.get("lens_source_x"),
            "source_y": (
                pair.get("lens_source_y")
                if pair.get("lens_source_y") is not None
                else pair.get("lens_y")
            ),
            "y": (
                pair.get("lens_source_y")
                if pair.get("lens_source_y") is not None
                else pair.get("lens_y")
            ),
            "box": pair.get("lens_box"), "confidence": pair.get("lens_conf"),
            "accepted": pair.get("lens_accepted"), "score": pair.get("lens_score"), "lemma": pair.get("lens_lemma"),
            "raw": pair.get("lens_raw"), "corrected": pair.get("lens_corrected"), "POS": pair.get("lens_pos"),
            "repairs": pair.get("lens_repairs"), "text": pair.get("lens_text"), "reason": pair.get("lens_reject_reason"),
            "parser_trace": pair.get("lens_parser_trace"),
            "features": dict(pair.get("lens_features", {}) or {}),
        },
        "alignment_method": pair.get("alignment_method", ""),
        "pair_reason": pair.get("reason", ""),
    }


def _apply_pair_engine_position(
    deps: OcrPairingDeps, 
    item: dict[str, Any],
    pair: dict[str, Any],
    prefix: str,
    column: int,
    canonical_u: int,
    geometry: "Geometry" | None,
) -> None:
    """Apply one engine's position without mixing temporary reading axis and source Y."""
    raw_v = pair.get(f"{prefix}_y")
    if raw_v is None:
        return
    canonical_v = int(raw_v)
    coarse_v = int(pair.get(f"{prefix}_coarse_y") or canonical_v)
    anchor_v = int(pair.get(f"{prefix}_anchor_y") or coarse_v)

    if geometry is not None:
        refined_u = int(geometry.x_at(column, canonical_v))
        source_x, source_y = geometry.canonical_to_source(refined_u, canonical_v)
        coarse_u = int(geometry.x_at(column, coarse_v))
        coarse_source_x, coarse_source_y = geometry.canonical_to_source(
            coarse_u, coarse_v
        )
        anchor_u = int(geometry.x_at(column, anchor_v))
        anchor_source_x, anchor_source_y = geometry.canonical_to_source(
            anchor_u, anchor_v
        )
    else:
        refined_u = int(canonical_u)
        source_x = pair.get(f"{prefix}_source_x")
        source_y = pair.get(f"{prefix}_source_y")
        source_x = refined_u if source_x is None else int(source_x)
        source_y = canonical_v if source_y is None else int(source_y)
        coarse_u = refined_u
        coarse_source_x, coarse_source_y = source_x, coarse_v
        anchor_u = refined_u
        anchor_source_x, anchor_source_y = source_x, anchor_v

    item.update({
        "_axis_u": int(refined_u),
        "_axis_v": int(canonical_v),
        "_coarse_axis_v": int(coarse_v),
        "_anchor_axis_v": int(anchor_v),
        "source_x": int(source_x),
        "source_y": int(source_y),
        "refined_source_y": int(source_y),
        "coarse_source_x": int(coarse_source_x),
        "coarse_source_y": int(coarse_source_y),
        "anchor_source_x": int(anchor_source_x),
        "anchor_source_y": int(anchor_source_y),
    })


def _agreement_summary(
    deps: OcrPairingDeps, review_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    _lemma_similarity = deps._lemma_similarity
    exact = similar = conflict = paddle_only = tesseract_only = 0
    both = 0
    lens_used = lens_only = triple_exact = majority_agree = 0
    for row in review_candidates:
        # Original-Y fallback rows are editing alternatives for the same physical
        # headword, not additional OCR observations. Exclude them from page
        # agreement/quality statistics so preserving a fallback cannot lower the
        # reported page confidence.
        if str(row.get("position_variant", "refined")) == "original":
            continue
        p = row.get("paddle", {}) or {}; t = row.get("tesseract", {}) or {}; lens = row.get("lens", {}) or {}
        # Agreement is a headword-quality metric, not a whole-page text metric.
        # Ignore ordinary rejected body rows that are kept only to power the
        # manual checkbox overlay.
        if not (row.get("selected") or p.get("accepted") or t.get("accepted") or row.get("needs_review")):
            continue
        if p.get("y") is not None and t.get("y") is not None:
            both += 1
            pl = str(p.get("lemma") or ""); tl = str(t.get("lemma") or "")
            if pl and tl and pl.casefold() == tl.casefold(): exact += 1
            elif _lemma_similarity(pl, tl) >= 0.82: similar += 1
            else: conflict += 1
        elif p.get("y") is not None:
            paddle_only += 1
        elif t.get("y") is not None:
            tesseract_only += 1
        if lens.get("y") is not None:
            lens_used += 1
            if p.get("y") is None and t.get("y") is None:
                lens_only += 1
            words = [
                str(side.get("lemma") or "")
                for side in (p, t, lens) if side.get("y") is not None and side.get("lemma")
            ]
            if len(words) == 3 and all(_lemma_similarity(words[0], value) >= 0.82 for value in words[1:]):
                triple_exact += 1
            if len(words) >= 2 and max(
                (_lemma_similarity(words[i], words[j]) for i in range(len(words)) for j in range(i + 1, len(words))),
                default=0.0,
            ) >= 0.82:
                majority_agree += 1
    union = max(1, exact + similar + conflict + paddle_only + tesseract_only)
    agreement = (exact + 0.65 * similar) / union
    return {
        "candidate_union": union, "paired": both, "exact": exact, "similar": similar,
        "conflict": conflict, "paddle_only": paddle_only, "tesseract_only": tesseract_only,
        "agreement": round(agreement, 4),
        "lens_used": lens_used, "lens_only": lens_only,
        "triple_agree": triple_exact, "multi_engine_majority": majority_agree,
    }

