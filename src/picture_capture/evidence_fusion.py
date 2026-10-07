from __future__ import annotations

"""Evidence-fusion wrapper around the stable OCR core.

The implementation is split deliberately: ``paddle_headwords_core`` keeps the
large, battle-tested OCR/parsing engine unchanged, while this thin module adds
supervised corrections learned from user-reviewed training exports. The wrapper
passes those corrections through explicit core hooks, avoiding import-time core
mutation while retaining the mature OCR engine unchanged.
"""

from typing import Any
import re

from . import paddle_headwords_core as _core

# Source-guard compatibility markers. The executable implementations live in
# paddle_headwords_core.py; these exact markers remain here because established
# regression tests intentionally inspect the historical module path.
# oriented = normalize_page_rgb(image)
# getattr(settings, "ocr_language", "")
# configure_windows_nvidia_dlls()
# _QUALITY_SUMMARY_LOCK = threading.Lock()


# Re-export every public/private runtime symbol expected by the rest of Picture
# Capture. Private helpers are intentionally included because tests, processing,
# profile tooling and training export already consume several of them.
for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


_original_filter_headword_records = _core.filter_headword_records
_original_annotate_peer_typography_matches = _core._annotate_peer_typography_matches
_original_detect_paddle_headwords = _core.detect_paddle_headwords


def _drop_peer_typography_match(row: dict[str, Any]) -> None:
    features = row.get("features", {}) or {}
    if not isinstance(features, dict):
        return
    features.pop("peer_typography_match", None)
    features.pop("peer_typography_votes", None)
    features.pop("peer_typography_anchor_count", None)
    trace = list(row.get("parser_trace", []) or [])
    row["parser_trace"] = [
        item for item in trace if str(item) != "peer_typography_match"
    ]
    bugs = list(row.get("bug_types", []) or [])
    row["bug_types"] = [
        item for item in bugs if str(item) != "PEER_TYPOGRAPHY_MATCH"
    ]


def _annotate_peer_typography_matches(
    diagnostics: list[dict[str, Any]],
) -> int:
    """Require true boldness agreement for Latin typography rescue.

    Training-export supervision showed that dense Latin body/example lines often
    match real headwords in height and vertical gap while remaining visibly less
    bold. The old two-of-three vote could therefore mark body text as a peer
    typography match. For non-CJK candidates boldness is now mandatory, while
    CJK visual-head candidates keep their dedicated geometry channels.
    """
    matched = int(_original_annotate_peer_typography_matches(diagnostics) or 0)
    removed = 0
    for row in diagnostics:
        features = row.get("features", {}) or {}
        if not isinstance(features, dict) or not features.get("peer_typography_match"):
            continue
        if any(bool(features.get(key)) for key in (
            "cjk_single_visual",
            "cjk_visual_projection_rescue",
            "cjk_visual_projection_confirmed",
            "cjk_oversized_recovery",
        )):
            continue

        try:
            value = float(features.get("boldness_ratio"))
            center = float(features.get("peer_typography_boldness_center"))
            delta = abs(float(features.get("peer_boldness_ratio_delta")))
            tolerance = float(features.get("peer_boldness_ratio_tolerance"))
        except (TypeError, ValueError):
            _drop_peer_typography_match(row)
            removed += 1
            continue

        # The supervised NewAge ES-ZH false positives clustered around ~0.74
        # boldness while true missing-tail headwords were around ~1.0. Use a
        # page-relative floor as the primary rule and retain a modest absolute
        # floor so a weak body-text population cannot redefine itself upward.
        boldness_ok = bool(
            center > 0
            and value >= max(0.88, center * 0.88)
            and delta <= tolerance
        )
        if not boldness_ok:
            _drop_peer_typography_match(row)
            removed += 1
            continue
        features["peer_typography_boldness_required"] = True

    return max(0, matched - removed)


def _user_rule_rejected(row: dict[str, Any]) -> bool:
    rule = row.get("user_rule", {}) or {}
    return bool(isinstance(rule, dict) and rule.get("rejected"))


def _hard_negative_feature(row: dict[str, Any]) -> bool:
    features = row.get("features", {}) or {}
    if not isinstance(features, dict):
        return True
    return any(bool(features.get(key)) for key in (
        "forced_reject",
        "marker_noise",
        "internal_article_symbol",
        "internal_relation_label",
        "internal_locution",
    ))


def _promoted_source_y(
    row: dict[str, Any],
    source_top: int,
) -> int:
    boundary = row.get("image_boundary_match", {}) or {}
    if isinstance(boundary, dict) and boundary.get("y") is not None:
        try:
            return int(source_top) + int(boundary["y"])
        except (TypeError, ValueError):
            pass
    try:
        return int(row.get("source_y"))
    except (TypeError, ValueError):
        return int(source_top)


def _append_promoted_entry(
    entries: list[Entry],
    row: dict[str, Any],
    *,
    word: str,
    source_column_x: int,
    source_top: int,
    engine_name: str,
    settings: AppSettings,
) -> bool:
    source_y = _promoted_source_y(row, source_top)
    tolerance = max(
        3,
        round(float(getattr(settings, "character_height", 26) or 26) * 0.45),
    )
    if any(abs(int(item.y) - source_y) <= tolerance for item in entries):
        return False
    try:
        confidence = float(row.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    entries.append(Entry(
        word=str(word or ""),
        x=int(source_column_x),
        y=int(source_y),
        confidence=confidence,
        ocr_source=str(engine_name or "ocr"),
    ))
    return True


def _mark_promoted_row(
    row: dict[str, Any],
    *,
    word: str,
    stage: str,
    trace_marker: str,
    bug_marker: str,
    source_top: int,
) -> None:
    original_reason = str(row.get("reject_reason", "") or "")
    row["accepted"] = True
    row["reject_reason"] = ""
    row["normalized_headword"] = str(word)
    row["extracted"] = str(word)
    if not str(row.get("raw_headword", "") or ""):
        row["raw_headword"] = str(word)
    if not str(row.get("corrected_headword", "") or ""):
        row["corrected_headword"] = str(word)
    row["parser_stage"] = stage
    row["supervised_rescue_original_reason"] = original_reason
    row["source_y"] = _promoted_source_y(row, source_top)
    trace = list(row.get("parser_trace", []) or [])
    if trace_marker not in trace:
        trace.append(trace_marker)
    row["parser_trace"] = trace
    bugs = list(row.get("bug_types", []) or [])
    if bug_marker not in bugs:
        bugs.append(bug_marker)
    row["bug_types"] = bugs


def _rescue_cjk_parser_failed_rows(
    entries: list[Entry],
    diagnostics: list[dict[str, Any]],
    *,
    source_top: int,
    source_column_x: int,
    settings: AppSettings,
    engine_name: str,
    profile: DictionaryProfile | None,
) -> int:
    """Recover visually proven large CJK heads even when lemma parsing fails.

    The supervised GUJIN set showed that many missed boundaries were already
    detected by OCR with high confidence and strong display-head geometry; the
    only failure was ``lemma_parse_failed``. Drawing a boundary should not be
    conditional on perfect text parsing when independent image evidence proves
    the entry start.
    """
    if not _core._is_chinese_ocr(settings):
        return 0
    if not bool(getattr(settings, "profile_cjk_allow_single_headword", True)):
        return 0

    parser_controls = int(
        getattr(settings, "profile_parser_controls_version", 0) or 0
    ) >= 1
    profile_family = str(getattr(profile, "family", "") or "")
    if not parser_controls and profile is not None and profile_family != "cjk_visual":
        return 0

    rescued = 0
    for row in diagnostics:
        if "meta" in row or row.get("accepted"):
            continue
        if str(row.get("reject_reason", "") or "") != "lemma_parse_failed":
            continue
        if _user_rule_rejected(row) or _hard_negative_feature(row):
            continue
        features = row.get("features", {}) or {}
        if not isinstance(features, dict):
            continue
        if not features.get("at_left", False) or not features.get("below_header", True):
            continue
        if not features.get("image_boundary_supported", False):
            continue
        try:
            confidence = float(row.get("confidence") or 0.0)
            height_ratio = float(features.get("height_ratio") or 0.0)
            leading_ratio = float(features.get("leading_record_height_ratio") or 0.0)
        except (TypeError, ValueError):
            continue
        if confidence < 0.75 or max(height_ratio, leading_ratio) < 1.65:
            continue

        word = _core._leading_cjk_ideograph(str(row.get("text", "") or ""))
        if not word:
            continue
        if not _append_promoted_entry(
            entries,
            row,
            word=word,
            source_column_x=source_column_x,
            source_top=source_top,
            engine_name=engine_name,
            settings=settings,
        ):
            continue

        features["cjk_parser_failed_visual_rescue"] = True
        features["cjk_single_visual"] = True
        features["cjk_single_prominent"] = True
        features["cjk_single_strong_visual"] = True
        features["strong_visual_fallback"] = True
        features["looks_like_continuation"] = False
        _mark_promoted_row(
            row,
            word=word,
            stage="cjk_parser_failed_visual_rescue",
            trace_marker="cjk_parser_failed_visual_rescue",
            bug_marker="CJK_PARSER_FAILED_VISUAL_RESCUE",
            source_top=source_top,
        )
        rescued += 1
    return rescued


def _latin_anchor_boldness(diagnostics: list[dict[str, Any]]) -> float:
    values: list[float] = []
    for row in diagnostics:
        if "meta" in row or not row.get("accepted"):
            continue
        features = row.get("features", {}) or {}
        if not isinstance(features, dict):
            continue
        if features.get("cjk_single_visual") or not features.get("at_left", True):
            continue
        try:
            confidence = float(row.get("confidence") or 0.0)
            boldness = float(features.get("boldness_ratio"))
        except (TypeError, ValueError):
            continue
        if confidence >= 0.85 and boldness > 0:
            values.append(boldness)
    if not values:
        return 0.0
    values.sort()
    middle = len(values) // 2
    if len(values) % 2:
        return float(values[middle])
    return float((values[middle - 1] + values[middle]) / 2.0)


def _rescue_false_continuation_rows(
    entries: list[Entry],
    diagnostics: list[dict[str, Any]],
    *,
    source_top: int,
    source_column_x: int,
    settings: AppSettings,
    engine_name: str,
    profile: DictionaryProfile | None,
) -> int:
    """Undo continuation false negatives only with strong headword evidence.

    PT-ZH supervision showed real dense Latin heads rejected as continuation
    when OCR glued lemma and POS (for example ``ababadarv.t.``). A rescue now
    requires an independent image boundary, left-edge placement, page-relative
    headword boldness and explicit grammatical structure in the raw OCR line.
    This keeps body examples in NewAge ES-ZH suppressed.
    """
    if _core._is_chinese_ocr(settings) or _core._is_japanese_ocr(settings):
        return 0

    active_profile = profile or _core._BUNDLED_PROFILE
    try:
        _headword_pattern, _special_pattern, pos_pattern = _core._compile_patterns(
            settings, active_profile
        )
    except Exception:
        pos_pattern = None
    anchor_boldness = _latin_anchor_boldness(diagnostics)
    if anchor_boldness <= 0:
        anchor_boldness = float(getattr(settings, "paddle_boldness_ratio", 1.0) or 1.0)

    rescued = 0
    for row in diagnostics:
        if "meta" in row or row.get("accepted"):
            continue
        if str(row.get("reject_reason", "") or "") != "continuation_fragment":
            continue
        if _user_rule_rejected(row) or _hard_negative_feature(row):
            continue
        features = row.get("features", {}) or {}
        if not isinstance(features, dict):
            continue
        if not features.get("at_left", False) or not features.get("below_header", True):
            continue
        if not features.get("image_boundary_supported", False):
            continue

        word = str(row.get("normalized_headword", "") or "").strip()
        if len(word.strip("-'’")) < 3:
            continue
        try:
            confidence = float(row.get("confidence") or 0.0)
            boldness = float(features.get("boldness_ratio") or 0.0)
            height_ratio = float(features.get("height_ratio") or 0.0)
        except (TypeError, ValueError):
            continue
        if confidence < 0.84 or height_ratio < 0.78:
            continue
        if boldness < max(0.90, anchor_boldness * 0.88):
            continue

        text = str(row.get("text", "") or "")
        grammar_visible = bool(
            features.get("structural_cue")
            or features.get("front_structure_cue")
            or features.get("tail_structure_satisfied")
            or str(row.get("pos_cue", "") or "").strip()
            or (pos_pattern is not None and bool(pos_pattern.search(text)))
        )
        if not grammar_visible:
            continue

        boundary = row.get("image_boundary_match", {}) or {}
        try:
            boundary_strength = float(
                boundary.get("strength") if isinstance(boundary, dict) else 0.0
            )
        except (TypeError, ValueError):
            boundary_strength = 0.0
        if boundary_strength < 0.35:
            continue

        if not _append_promoted_entry(
            entries,
            row,
            word=word,
            source_column_x=source_column_x,
            source_top=source_top,
            engine_name=engine_name,
            settings=settings,
        ):
            continue

        row["continuation_original_reason"] = str(
            row.get("continuation_reason", "") or ""
        )
        row["looks_like_continuation"] = False
        row["continuation_reason"] = ""
        features["looks_like_continuation"] = False
        features["continuation_visual_headword_override"] = True
        features["continuation_anchor_boldness"] = round(anchor_boldness, 4)
        _mark_promoted_row(
            row,
            word=word,
            stage=str(row.get("parser_stage", "") or "lemma"),
            trace_marker="continuation_visual_headword_override",
            bug_marker="CONTINUATION_FALSE_NEGATIVE_RESCUE",
            source_top=source_top,
        )
        rescued += 1
    return rescued


def filter_headword_records(
    records: list[OCRRecord],
    band: Image.Image,
    source_top: int,
    source_column_x: int,
    settings: AppSettings,
    separator_band: Image.Image | None = None,
    user_rules: list[HeadwordFilterRule] | None = None,
    engine_name: str = "paddle",
    profile: DictionaryProfile | None = None,
    pixel_scale: float | None = None,
) -> tuple[list[Entry], list[dict[str, Any]]]:
    peer_annotator = _core._annotate_peer_typography_matches
    if peer_annotator is _original_annotate_peer_typography_matches:
        peer_annotator = _annotate_peer_typography_matches

    entries, diagnostics = _original_filter_headword_records(
        records,
        band,
        source_top,
        source_column_x,
        settings,
        separator_band=separator_band,
        user_rules=user_rules,
        engine_name=engine_name,
        profile=profile,
        pixel_scale=pixel_scale,
        peer_typography_annotator=peer_annotator,
    )

    cjk_count = _rescue_cjk_parser_failed_rows(
        entries,
        diagnostics,
        source_top=source_top,
        source_column_x=source_column_x,
        settings=settings,
        engine_name=engine_name,
        profile=profile,
    )
    continuation_count = _rescue_false_continuation_rows(
        entries,
        diagnostics,
        source_top=source_top,
        source_column_x=source_column_x,
        settings=settings,
        engine_name=engine_name,
        profile=profile,
    )

    entries.sort(key=lambda item: (int(item.y), int(item.x)))
    if diagnostics and isinstance(diagnostics[0], dict) and "meta" in diagnostics[0]:
        meta = diagnostics[0].get("meta", {}) or {}
        if isinstance(meta, dict):
            meta["supervised_cjk_parser_rescue_count"] = int(cjk_count)
            meta["supervised_continuation_rescue_count"] = int(continuation_count)
    return entries, diagnostics


def detect_paddle_headwords(
    image: Image.Image,
    geometry: Any,
    settings: AppSettings,
    cache_path: Path | None = None,
    force_refresh: bool = False,
    engine: Any | None = None,
    filter_rules_path: Path | None = None,
    page_sections: list[PageSection] | None = None,
) -> list[Entry]:
    """Run the mature detector with supervised record filtering explicitly injected."""
    record_filter = _core.filter_headword_records
    if record_filter is _original_filter_headword_records:
        record_filter = filter_headword_records
    return _original_detect_paddle_headwords(
        image,
        geometry,
        settings,
        cache_path=cache_path,
        force_refresh=force_refresh,
        engine=engine,
        filter_rules_path=filter_rules_path,
        page_sections=page_sections,
        record_filter=record_filter,
    )


# This implementation module keeps ordinary assignment semantics. The historical
# public ``paddle_headwords`` facade remains the sole assignment-mirroring owner.


__all__ = [
    name for name in globals()
    if not name.startswith("__") and name not in {"_core"}
]
