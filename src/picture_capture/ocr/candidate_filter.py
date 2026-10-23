"""Complete OCR dictionary-headword candidate selection and diagnostic pipeline.

The single canonical owner for OCR grouping/repair, configured structural
grammar, first-ink and symbol evidence, Chinese visual-profile rescue,
geometry, acceptance/rejection scoring, stage diagnostics and final selected
entry list. All original patchable OCR operations are injected at call time.
No runtime import of heavy OCR core, app or native Paddle engines occurs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import re
import unicodedata

import numpy as np
from PIL import Image, ImageOps

from ..models import AppSettings, Entry
from ..profile.dictionary import DictionaryProfile
from .headword_models import HeadwordFilterRule, HeadwordParse, OCRRecord


@dataclass(frozen=True)
class HeadwordFilterDeps:
    """Forty-two original policy objects and functions bound per invocation."""
    evaluate_headword_filter_rules: object
    _headword_script_compatibility: object
    _is_chinese_ocr: object
    _configured_symbol_inventory: object
    _is_single_cjk_ideograph: object
    group_ocr_records: object
    _repair_split_headword_lines: object
    _repair_wrapped_headword_structure: object
    _repair_multiline_headword_state_machine: object
    _compile_patterns: object
    parse_headword_text: object
    _looks_like_marker_noise_lemma: object
    _ink_ratio: object
    _leading_box: object
    detect_image_separator_candidates: object
    match_ocr_lines_to_image_boundaries: object
    _trusted_visual_marker_lanes: object
    _detect_visual_entry_markers: object
    _match_visual_entry_markers_to_lines: object
    _parse_visual_configured_symbol_line: object
    _cjk_visual_projection_runs: object
    _cjk_right_context_metrics: object
    _cjk_right_context_features: object
    _cjk_candidate_right_context_metrics: object
    _cjk_candidate_right_context_features: object
    _cjk_word_for_visual_run: object
    _recover_oversized_cjk_ocr_records: object
    refine_separator_y: object
    refine_separator_y_adaptive: object
    refine_first_content_y: object
    _header_cutoff: object
    _accepted_cjk_row_for_visual_run: object
    _selected_tail_structure_evidence: object
    _ordinary_visual_rescue_thresholds: object
    _ordinary_strong_edge_visual_rescue: object
    _annotate_peer_typography_matches: object
    _BUNDLED_PROFILE: object
    _VERIFIED_OVERSIZED_CJK_RECOVERIES: object
    Entry: object
    load_dictionary_profile: object
    leading_relation_label: object
    starts_with_internal_article_symbol: object


def filter_headword_records(
    deps: HeadwordFilterDeps, 
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
    peer_typography_annotator: Any | None = None,
    separator_y_refiner: Any | None = None,
) -> tuple[list[Entry], list[dict[str, Any]]]:
    """Select dictionary headwords using structure, geometry and visual cues.

    The strongest signals are now: left alignment + lemma syntax + a nearby
    part-of-speech label. Size, ink density/boldness, special symbols and the
    gap before a line remain fallback evidence for entries without a POS label.
    """
    evaluate_headword_filter_rules = deps.evaluate_headword_filter_rules
    _headword_script_compatibility = deps._headword_script_compatibility
    _is_chinese_ocr = deps._is_chinese_ocr
    _configured_symbol_inventory = deps._configured_symbol_inventory
    _is_single_cjk_ideograph = deps._is_single_cjk_ideograph
    group_ocr_records = deps.group_ocr_records
    _repair_split_headword_lines = deps._repair_split_headword_lines
    _repair_wrapped_headword_structure = deps._repair_wrapped_headword_structure
    _repair_multiline_headword_state_machine = deps._repair_multiline_headword_state_machine
    _compile_patterns = deps._compile_patterns
    parse_headword_text = deps.parse_headword_text
    _looks_like_marker_noise_lemma = deps._looks_like_marker_noise_lemma
    _ink_ratio = deps._ink_ratio
    _leading_box = deps._leading_box
    detect_image_separator_candidates = deps.detect_image_separator_candidates
    match_ocr_lines_to_image_boundaries = deps.match_ocr_lines_to_image_boundaries
    _trusted_visual_marker_lanes = deps._trusted_visual_marker_lanes
    _detect_visual_entry_markers = deps._detect_visual_entry_markers
    _match_visual_entry_markers_to_lines = deps._match_visual_entry_markers_to_lines
    _parse_visual_configured_symbol_line = deps._parse_visual_configured_symbol_line
    _cjk_visual_projection_runs = deps._cjk_visual_projection_runs
    _cjk_right_context_metrics = deps._cjk_right_context_metrics
    _cjk_right_context_features = deps._cjk_right_context_features
    _cjk_candidate_right_context_metrics = deps._cjk_candidate_right_context_metrics
    _cjk_candidate_right_context_features = deps._cjk_candidate_right_context_features
    _cjk_word_for_visual_run = deps._cjk_word_for_visual_run
    _recover_oversized_cjk_ocr_records = deps._recover_oversized_cjk_ocr_records
    refine_separator_y = deps.refine_separator_y
    refine_separator_y_adaptive = deps.refine_separator_y_adaptive
    refine_first_content_y = deps.refine_first_content_y
    _header_cutoff = deps._header_cutoff
    _accepted_cjk_row_for_visual_run = deps._accepted_cjk_row_for_visual_run
    _selected_tail_structure_evidence = deps._selected_tail_structure_evidence
    _ordinary_visual_rescue_thresholds = deps._ordinary_visual_rescue_thresholds
    _ordinary_strong_edge_visual_rescue = deps._ordinary_strong_edge_visual_rescue
    _annotate_peer_typography_matches = deps._annotate_peer_typography_matches
    _BUNDLED_PROFILE = deps._BUNDLED_PROFILE
    _VERIFIED_OVERSIZED_CJK_RECOVERIES = deps._VERIFIED_OVERSIZED_CJK_RECOVERIES
    Entry = deps.Entry
    load_dictionary_profile = deps.load_dictionary_profile
    leading_relation_label = deps.leading_relation_label
    starts_with_internal_article_symbol = deps.starts_with_internal_article_symbol
    refine_y = separator_y_refiner or refine_separator_y
    if profile is None and _is_chinese_ocr(settings):
        # Backward-compatible direct API behavior: before v2.10 Chinese parsing
        # was selected from OCR language alone. The full application pipeline
        # passes an explicit layout Profile, but low-level callers/tests that do
        # not pass one should keep the historical bracket/single-character mode.
        active_profile = load_dictionary_profile(
            preset="cjk_bracket_display", language=settings.ocr_language,
        )
    else:
        active_profile = profile or _BUNDLED_PROFILE
    patterns = _compile_patterns(settings, active_profile)
    _headword_pattern, special_pattern, _pos_pattern = patterns
    # Merge first, then actively repair the special case where OCR split a
    # left-edge bold lemma from its right-side gender/POS fragments.
    lines = group_ocr_records([record for record in records if record.text], settings.paddle_line_merge_y_ratio)
    # All visible/profile pixel settings are literal original-image pixels.
    # OCR engines may resize internally, but OCR boxes are mapped back to this
    # full-resolution band before candidate filtering.
    pixel_scale = max(0.01, float(pixel_scale)) if pixel_scale is not None else 1.0
    runtime_width = max(1, band.width)
    row_padding = int(settings.row_padding)
    character_height = int(settings.character_height)
    row_height = max(1, character_height + row_padding)
    left_limit = round(
        (settings.paddle_band_left_margin + settings.paddle_left_tolerance)
        * pixel_scale
    )
    lines = _repair_split_headword_lines(lines, settings, left_limit, patterns)
    lines = _repair_wrapped_headword_structure(lines, settings, left_limit, patterns)
    lines = _repair_multiline_headword_state_machine(lines, settings, left_limit, patterns)
    lines = [line for line in lines if line.confidence >= settings.paddle_rec_score_threshold]
    if not lines:
        return [], []

    gray = np.asarray(ImageOps.grayscale(band), dtype=np.uint8)
    separator_gray = (
        np.asarray(ImageOps.grayscale(separator_band), dtype=np.uint8)
        if separator_band is not None
        else gray
    )
    heights = np.asarray([line.box[3] - line.box[1] for line in lines], dtype=float)
    median_height = max(1.0, float(np.median(heights)))

    # Profile/OCR tuning distances are direct full-resolution image pixels.
    gap_threshold = row_height * settings.paddle_gap_ratio
    header_cutoff = _header_cutoff(gray, settings, pixel_scale)

    # Independent image-only separator candidates.  OCR lines and boundaries
    # are paired with a mutual-nearest rule, so the image validates OCR geometry
    # and OCR in turn validates which blank-to-ink transitions are actual entry
    # candidates.  Pages without stable whitespace simply get no matches.
    image_separator_candidates = detect_image_separator_candidates(
        separator_gray,
        max(2, round(median_height)),
        settings,
        pixel_scale=pixel_scale,
        lower_bound=header_cutoff,
    )
    image_boundary_matches = match_ocr_lines_to_image_boundaries(
        lines, image_separator_candidates, max(2, round(median_height))
    )

    parser_controls = int(
        getattr(settings, "profile_parser_controls_version", 0) or 0
    ) >= 1
    marker_prefix_enabled = (
        bool(getattr(settings, "profile_allow_marker_prefix", False))
        if parser_controls else active_profile.uses_parser("cjk_marker_pinyin")
    )
    bracket_symbol_enabled = (
        bool(getattr(settings, "profile_cjk_allow_bracketed_headword", True))
        if parser_controls else active_profile.uses_parser("cjk_bracketed")
    )
    symbol_inventory = _configured_symbol_inventory(settings, active_profile)
    template_roles = {
        str(sample.get("role") or "")
        for sample in symbol_inventory.get("visual_templates", [])
        if isinstance(sample, dict)
    }
    visual_symbol_enabled = bool(
        symbol_inventory.get("enabled")
        and symbol_inventory.get("visual_rescue")
        and (
            (
                marker_prefix_enabled
                and (
                    symbol_inventory.get("entry_markers")
                    or "entry_marker" in template_roles
                )
            )
            or (
                bracket_symbol_enabled
                and (
                    symbol_inventory.get("bracket_openers")
                    or "bracket_open" in template_roles
                )
            )
        )
    )
    trusted_visual_lanes = (
        _trusted_visual_marker_lanes(
            lines,
            symbol_inventory,
            median_height,
        )
        if visual_symbol_enabled else {}
    )
    visual_entry_markers = (
        _detect_visual_entry_markers(
            gray,
            median_height,
            left_limit,
            lower_bound=header_cutoff,
            inventory=symbol_inventory,
            trusted_lanes=trusted_visual_lanes,
        )
        if visual_symbol_enabled else []
    )
    visual_marker_matches = _match_visual_entry_markers_to_lines(
        lines, visual_entry_markers, median_height,
    )

    # Estimate a page-local reference density from leading text portions, not
    # from the whole line (which often mixes bold lemma with normal definition).
    leading_boxes: list[tuple[int, int, int, int]] = []
    parses: list[HeadwordParse | None] = []
    for line_index, line in enumerate(lines):
        parsed = parse_headword_text(line.text, settings, patterns, active_profile)
        visual_marker = visual_marker_matches.get(line_index)
        if visual_marker is not None:
            expected_stages = (
                {"cjk_marker_pinyin", "cjk_visual_marker_rescue"}
                if visual_marker.get("role") == "entry_marker"
                else {
                    "chinese_bracketed_headword",
                    "chinese_open_bracket_headword",
                    "cjk_visual_bracket_rescue",
                }
            )
            if parsed is None or parsed.parser_stage not in expected_stages:
                rescued = _parse_visual_configured_symbol_line(
                    line.text,
                    visual_marker,
                    settings,
                    active_profile,
                )
                if rescued is not None:
                    parsed = rescued
        parses.append(parsed)
        leading_boxes.append(
            _leading_box(line, parsed.match_end if parsed else min(12, len(line.text)))
        )
    densities = np.asarray([_ink_ratio(gray, box) for box in leading_boxes], dtype=float)
    positive_densities = densities[densities > 0]
    median_density = max(1e-6, float(np.median(positive_densities)) if positive_densities.size else 1e-6)

    diagnostics: list[dict[str, Any]] = []
    accepted: list[tuple[float, Entry]] = []
    previous_bottom = header_cutoff

    for index, line in enumerate(lines):
        parsed = parses[index]
        image_boundary = image_boundary_matches.get(index)
        visual_entry_marker = visual_marker_matches.get(index)
        height_ratio = heights[index] / median_height
        boldness_ratio = densities[index] / median_density
        x0, y0, _, y1 = line.box
        at_left = bool(x0 <= left_limit or visual_entry_marker is not None)
        below_header = y0 >= header_cutoff
        special = bool(
            special_pattern.search(line.text) or visual_entry_marker is not None
        )
        internal_symbol = starts_with_internal_article_symbol(line.text, active_profile)
        relation_label = leading_relation_label(line.text, active_profile)
        rule_result = evaluate_headword_filter_rules(
            user_rules or [],
            raw_lemma=parsed.raw if parsed else "",
            normalized_lemma=parsed.normalized if parsed else "",
            line_text=line.text,
            pos_text=parsed.pos_text if parsed else "",
        )
        script_compatible, leading_script = _headword_script_compatibility(
            settings, parsed
        )
        has_pos = bool(parsed and parsed.has_pos and not rule_result["pos_excluded"])
        has_inflection = bool(parsed and parsed.has_inflection)
        tail_evidence, tail_evidence_features = _selected_tail_structure_evidence(
            settings,
            parsed,
            pos_allowed_by_rules=not bool(rule_result["pos_excluded"]),
        )
        selected_pos = "pos" in tail_evidence
        selected_inflection = "inflection" in tail_evidence
        selected_variant = "variant" in tail_evidence
        selected_pronunciation = "pronunciation" in tail_evidence
        selected_descriptor = "descriptor" in tail_evidence
        cjk_marker_prefixed = bool(
            parsed and parsed.descriptor_text == "cjk_marker_pinyin"
        )
        cjk_single_visual = bool(
            _is_chinese_ocr(settings)
            and parsed
            and _is_single_cjk_ideograph(parsed.normalized)
            and parsed.descriptor_text != "chinese_bracketed_headword"
            and not cjk_marker_prefixed
        )
        parser_controls = int(
            getattr(settings, "profile_parser_controls_version", 0) or 0
        ) >= 1
        cjk_profile_active = bool(
            getattr(active_profile, "family", "") == "cjk_visual"
            or getattr(active_profile, "key", "") == "cjk_visual"
            or parser_controls
        )
        cjk_bracketed = bool(
            cjk_profile_active
            and parsed
            and parsed.descriptor_text == "chinese_bracketed_headword"
        )
        cjk_allow_single = bool(
            getattr(settings, "profile_cjk_allow_single_headword", True)
        )
        cjk_allow_bracketed = bool(
            getattr(settings, "profile_cjk_allow_bracketed_headword", True)
        )
        cjk_require_left_edge = bool(
            getattr(settings, "profile_cjk_require_left_edge", True)
        )
        cjk_brackets_in_body = bool(
            getattr(settings, "profile_cjk_brackets_in_body", False)
        )
        cjk_require_visual_evidence = bool(
            getattr(settings, "profile_cjk_require_visual_evidence", False)
        )
        # OCR sometimes merges a large single-character head with a small
        # pronunciation/variant fragment. The generic parser may still extract
        # a one-Han lemma from that merged line; treat it as the same visual
        # candidate family instead of requiring the dedicated parser stage.
        cjk_at_left = bool(
            at_left
            or (cjk_single_visual and x0 <= max(left_limit, round(band.width * 0.18)))
        )
        # A single Han glyph is intentionally *not* treated as a structural
        # descriptor.  Its acceptance must come from strong visual prominence
        # (large display glyph) rather than the mere fact that it is one CJK
        # character.  Bracketed Chinese compounds remain structural cues.
        has_descriptor = bool(parsed and parsed.has_descriptor and not cjk_single_visual)
        if cjk_single_visual:
            selected_descriptor = False
            tail_evidence = tuple(
                name for name in tail_evidence if name != "descriptor"
            )
        internal_locution = bool(
            parsed and parsed.descriptor_text in {"parallel_gloss", "parallel_gloss_ocr"}
        )
        large = height_ratio >= settings.paddle_height_ratio
        bold = boldness_ratio >= settings.paddle_boldness_ratio
        preceding_gap = max(0, y0 - previous_bottom)
        separated = preceding_gap >= gap_threshold
        leading_record_height_ratio = height_ratio
        leading_record: OCRRecord | None = None
        if line.records:
            leading_record = min(line.records, key=lambda record: (record.box[0], record.box[1]))
            leading_record_height_ratio = (
                leading_record.box[3] - leading_record.box[1]
            ) / median_height

        # A child produced by _recover_oversized_cjk_ocr_records() has already
        # passed a stricter image-level proof than the generic single-CJK gate:
        # one pathological giant OCR box contained multiple physically separate
        # oversized glyph runs, and this exact run was locally re-OCRed as one
        # Han headword.  Do not ask that child to prove "large" a second time
        # against the OCR-line median.  On pages with several consecutive large
        # heads that median can be inflated by the recovered children themselves,
        # which previously made real heads appear ordinary-sized and unchecked.
        cjk_oversized_recovery = bool(
            cjk_single_visual
            and leading_record is not None
            and str(getattr(leading_record, "recovery", "") or "")
            in _VERIFIED_OVERSIZED_CJK_RECOVERIES
        )

        cjk_candidate_right_context: dict[str, Any] | None = None
        cjk_candidate_right_sparse = False
        if (
            cjk_single_visual
            and cjk_allow_single
            and cjk_at_left
            and leading_record is not None
            and bool(getattr(settings, "profile_cjk_right_context_enabled", True))
        ):
            cjk_candidate_right_context = _cjk_candidate_right_context_metrics(
                gray,
                leading_record.box,
                median_height,
                settings,
                header_cutoff=header_cutoff,
            )
            # Candidate-centered sparsity is allowed to rescue a missed visual
            # projection only when the same X-region contains ordinary body ink
            # elsewhere on the page.  This prevents an all-white synthetic/empty
            # region from becoming positive evidence by itself.
            cjk_candidate_right_sparse = bool(
                cjk_candidate_right_context.get("sparse")
                and cjk_candidate_right_context.get("candidate_baseline_supported")
            )

        # Structure carries most of the evidence. POS is deliberately stronger
        # than boldness because body text can also be bold (ANT., FAM., etc.).
        tail_controls_active = int(
            getattr(settings, "profile_tail_structure_version", 0) or 0
        ) >= 1
        numbered_prefix_evidence = False
        if parser_controls and bool(
            getattr(settings, "profile_allow_numbered_prefix", False)
        ):
            prefix_pattern = (
                active_profile.prefix_regex
                or r"^\s*\d{1,4}(?:\s*[.．]\s*|\s+)"
            )
            try:
                numbered_prefix_evidence = bool(
                    re.match(prefix_pattern, line.text, flags=re.UNICODE)
                )
            except re.error:
                numbered_prefix_evidence = False
        configured_marker_evidence = bool(
            marker_prefix_enabled
            and (
                visual_entry_marker is not None
                or special_pattern.search(line.text)
            )
        )
        front_structure_cue = bool(
            numbered_prefix_evidence
            or configured_marker_evidence
            or cjk_marker_prefixed
        )
        tail_structure_cue = bool(tail_evidence)

        score = (
            (2.0 if parsed else 0.0)
            + (2.0 if (cjk_at_left if cjk_single_visual else at_left) else 0.0)
            + (3.0 if selected_pos else 0.0)
            + (2.0 if selected_inflection else 0.0)
            + (1.5 if selected_variant else 0.0)
            + (1.5 if selected_pronunciation else 0.0)
            + (3.0 if selected_descriptor else 0.0)
            + (1.0 if front_structure_cue else 0.0)
            + (0.75 if large else 0.0)
            + (1.0 if bold else 0.0)
            + (0.5 if separated else 0.0)
            + (0.75 if cjk_candidate_right_sparse else 0.0)
        )
        if tail_controls_active:
            structural_cue = tail_structure_cue or front_structure_cue
        else:
            structural_cue = has_pos or has_inflection or has_descriptor or special
        visual_cue = large or bold or separated
        fallback_cue = structural_cue or visual_cue
        # Character dictionaries use oversized single glyphs as entry heads.
        # Their size contrast is much stronger than ordinary bold body text, so
        # use a dedicated gate rather than lowering the global candidate score.
        cjk_single_sparse_context_rescue = bool(
            cjk_single_visual
            and cjk_candidate_right_sparse
            and cjk_at_left
            and leading_record_height_ratio >= 0.72
            and (
                separated
                or bool(
                    parsed
                    and parsed.parser_stage in {
                        "cjk_single_with_pinyin",
                        "chinese_single_character_with_variant",
                    }
                )
                or boldness_ratio >= 0.92
            )
        )
        cjk_single_prominent = bool(
            cjk_single_visual
            and (
                cjk_oversized_recovery
                or leading_record_height_ratio >= 1.45
                or (
                    leading_record_height_ratio >= 1.28
                    and boldness_ratio >= max(1.08, settings.paddle_boldness_ratio * 0.95)
                    and separated
                )
                or cjk_single_sparse_context_rescue
            )
        )
        looks_like_continuation = bool(parsed and parsed.looks_like_continuation)
        marker_noise = _looks_like_marker_noise_lemma(parsed)
        visual_rescue_thresholds = _ordinary_visual_rescue_thresholds(settings)
        ordinary_strong_edge_visual_rescue = _ordinary_strong_edge_visual_rescue(
            settings,
            parsed,
            at_left=at_left,
            below_header=below_header,
            boldness_ratio=boldness_ratio,
            height_ratio=height_ratio,
            confidence=line.confidence,
            looks_like_continuation=looks_like_continuation,
            marker_noise=marker_noise,
        )
        # For saved explicit Profiles the old diagnostic/fusion feature must
        # describe the same visible rescue decision, not a second hidden gate.
        strong_visual = (
            ordinary_strong_edge_visual_rescue
            if tail_controls_active
            else bool(
                parsed
                and len(parsed.normalized.strip("-")) >= 3
                and at_left
                and below_header
                and boldness_ratio >= max(1.25, settings.paddle_boldness_ratio * 1.08)
                and height_ratio >= 0.92
            )
        )
        # "普通左缘短词" always means left-edge. The optional
        # relaxation applies only to the explicitly CJK structural channels.
        if cjk_single_visual or cjk_bracketed:
            position_ok = (
                (cjk_at_left if cjk_single_visual else at_left)
                if cjk_require_left_edge else True
            )
        else:
            position_ok = at_left
        base_eligible = bool(
            parsed
            and parsed.normalized
            and below_header
            and position_ok
            and script_compatible
        )
        normalized_line_text = unicodedata.normalize(
            "NFKC", str(line.text or "")
        ).lstrip()
        configured_bracket_openers = tuple(
            str(symbol)
            for symbol in symbol_inventory.get("bracket_openers", ())
            if str(symbol)
        )
        explicit_bracket_symbol = next(
            (
                symbol for symbol in configured_bracket_openers
                if symbol in normalized_line_text[:24]
            ),
            "",
        )
        cjk_bracket_explicit_ocr = bool(
            cjk_bracketed
            and explicit_bracket_symbol
            and parsed is not None
            and parsed.parser_stage in {
                "chinese_bracketed_headword",
                "chinese_open_bracket_headword",
            }
        )
        cjk_bracket_visual_marker = bool(
            visual_entry_marker is not None
            and str(visual_entry_marker.get("role") or "") == "bracket_open"
        )
        cjk_bracket_visual_supported = bool(
            cjk_bracket_visual_marker
            or large
            or bold
        )
        cjk_bracket_extra_required = bool(
            cjk_bracketed
            and (
                cjk_brackets_in_body
                or (
                    not cjk_bracket_explicit_ocr
                    and cjk_require_visual_evidence
                )
            )
        )
        tail_required = bool(
            tail_controls_active
            and getattr(settings, "profile_tail_require_selected", False)
        )
        tail_visual_rescue_enabled = bool(
            tail_controls_active
            and getattr(settings, "profile_tail_allow_visual_rescue", False)
        )
        tail_requirement_ok = bool(
            not tail_required
            or tail_structure_cue
            or front_structure_cue
            or (
                tail_visual_rescue_enabled
                and ordinary_strong_edge_visual_rescue
            )
        )
        ordinary_accept = bool(
            base_eligible
            and not cjk_single_visual
            and (not cjk_bracketed or cjk_allow_bracketed)
            and (
                not cjk_bracket_extra_required
                or cjk_bracket_visual_supported
            )
            and not looks_like_continuation
            and not marker_noise
            and score >= settings.paddle_min_candidate_score
            and (
                tail_requirement_ok
                if tail_controls_active
                else (
                    structural_cue
                    or not settings.paddle_require_pos_or_symbol
                    or ordinary_strong_edge_visual_rescue
                )
            )
            and (fallback_cue or not settings.paddle_require_visual_cue)
        )
        cjk_single_strong_visual = bool(
            cjk_single_prominent
            and (
                cjk_oversized_recovery
                or leading_record_height_ratio >= 1.55
                or (
                    leading_record_height_ratio >= 1.35
                    and boldness_ratio >= max(1.12, settings.paddle_boldness_ratio)
                    and separated
                )
                or cjk_single_sparse_context_rescue
            )
        )
        cjk_single_accept = bool(
            base_eligible
            and cjk_single_visual
            and (not cjk_profile_active or cjk_allow_single)
            and cjk_single_prominent
            and (
                not cjk_profile_active
                or not cjk_require_visual_evidence
                or cjk_single_strong_visual
            )
            and not looks_like_continuation
            and not marker_noise
        )
        # Explicit reject rules win. Explicit accept rules may rescue a parsed,
        # left-aligned body candidate that fails built-in structural/visual
        # thresholds, but cannot turn arbitrary OCR noise outside the column
        # entry zone into a marker.
        is_headword = bool(
            base_eligible
            and not internal_symbol
            and not relation_label
            and not internal_locution
            and not rule_result["rejected"]
            and (ordinary_accept or cjk_single_accept or rule_result["accepted"])
        )
        if is_headword:
            reject_reason = ""
        elif internal_symbol:
            reject_reason = "internal_article_symbol"
        elif relation_label:
            reject_reason = "internal_relation_label"
        elif internal_locution:
            reject_reason = "internal_locution"
        elif rule_result["rejected"]:
            reject_reason = "user_reject_rule"
        elif not parsed:
            reject_reason = "lemma_parse_failed"
        elif not script_compatible:
            reject_reason = "incompatible_headword_script"
        elif cjk_profile_active and cjk_single_visual and not cjk_allow_single:
            reject_reason = "cjk_single_headword_disabled"
        elif cjk_bracketed and not cjk_allow_bracketed:
            reject_reason = "cjk_bracketed_headword_disabled"
        elif cjk_bracket_extra_required and not cjk_bracket_visual_supported:
            reject_reason = "cjk_bracket_needs_visual_evidence"
        elif (
            cjk_profile_active
            and cjk_single_visual
            and cjk_require_visual_evidence
            and cjk_single_prominent
            and not cjk_single_strong_visual
        ):
            reject_reason = "cjk_single_needs_stronger_visual_evidence"
        elif not position_ok:
            reject_reason = "not_at_column_left"
        elif not below_header:
            reject_reason = "above_header_cutoff"
        elif looks_like_continuation:
            reject_reason = "continuation_fragment"
        elif marker_noise:
            reject_reason = "marker_glyph_ocr_noise"
        elif cjk_single_visual and not cjk_single_prominent:
            reject_reason = "cjk_single_not_visually_prominent"
        elif tail_controls_active and tail_required and not tail_requirement_ok:
            reject_reason = "missing_selected_tail_structure"
        elif settings.paddle_require_pos_or_symbol and not structural_cue:
            reject_reason = "missing_pos_inflection_descriptor_or_symbol"
        elif score < settings.paddle_min_candidate_score:
            reject_reason = "score_below_threshold"
        elif settings.paddle_require_visual_cue and not fallback_cue:
            reject_reason = "missing_structure_or_visual_cue"
        else:
            reject_reason = "candidate_rejected"
        coarse_band_y = max(0, y0 - row_padding)
        if visual_entry_marker is not None:
            marker_coarse_y = max(
                0, int(visual_entry_marker["y0"]) - max(1, int(row_padding))
            )
            coarse_band_y = min(coarse_band_y, marker_coarse_y)
        # The first printed entry is a special geometry case: there is no
        # preceding line and therefore no inter-line whitespace valley. Locate
        # the first sustained ink row instead of applying the ordinary valley rule.
        has_prior_content_line = previous_bottom > header_cutoff
        # Keep refined geometry for a physically verified recovered large head
        # even when another explicit policy (for example a user reject rule)
        # leaves it unchecked.  A later manual checkbox selection must promote
        # the refined separator, not the raw visual-run/OCR top.
        refine_candidate_geometry = bool(is_headword or cjk_oversized_recovery)
        if refine_candidate_geometry and not has_prior_content_line:
            refined_band_y, separator_refinement = refine_first_content_y(
                separator_gray,
                coarse_band_y,
                max(2, round(median_height)),
                settings,
                pixel_scale=pixel_scale,
                lower_bound=header_cutoff,
            )
        elif refine_candidate_geometry and _is_chinese_ocr(settings):
            refined_band_y, separator_refinement = refine_separator_y_adaptive(
                separator_gray,
                coarse_band_y,
                max(2, round(median_height)),
                settings,
                pixel_scale=pixel_scale,
                lower_bound=header_cutoff,
                content_top=(int(image_boundary.get("ink_onset_y", y0)) if image_boundary else y0),
                preceding_gap_hint=preceding_gap,
                fallback_refiner=refine_y,
            )
        elif refine_candidate_geometry:
            refined_band_y, separator_refinement = refine_y(
                separator_gray,
                coarse_band_y,
                max(2, y1 - y0),
                settings,
                pixel_scale=pixel_scale,
                lower_bound=header_cutoff,
            )
        else:
            refined_band_y = coarse_band_y
            separator_refinement = {"enabled": False, "reason": "candidate_rejected"}

        if refine_candidate_geometry and image_boundary is not None and has_prior_content_line:
            boundary_y = int(image_boundary.get("y", refined_band_y))
            previous_refined_y = int(refined_band_y)
            # The mutually matched image boundary is an independent geometry
            # observation. Use its lower blank edge as the final separator while
            # preserving the OCR-only refinement in diagnostics for fallback.
            refined_band_y = max(header_cutoff, min(separator_gray.shape[0] - 1, boundary_y))
            separator_refinement = dict(separator_refinement or {})
            separator_refinement.update({
                "image_boundary_matched": True,
                "pre_boundary_refined_y": previous_refined_y,
                "image_boundary_y": int(boundary_y),
                "image_boundary_ink_onset_y": int(image_boundary.get("ink_onset_y", boundary_y)),
                "image_boundary_blank_rows": int(image_boundary.get("blank_rows", 0)),
                "image_boundary_strength": float(image_boundary.get("strength", 0.0)),
                "image_boundary_match_method": str(image_boundary.get("match_method", "mutual_nearest_y")),
                "reason": "ocr_image_boundary_mutual_match",
                "refined_y": int(refined_band_y),
                "shift": int(refined_band_y) - int(coarse_band_y),
            })
        source_y = source_top + refined_band_y
        coarse_source_y = source_top + coarse_band_y
        anchor_band_y = int((separator_refinement or {}).get("anchor_y", coarse_band_y))
        anchor_source_y = source_top + anchor_band_y
        word = parsed.normalized if parsed else ""
        diagnostics.append({
            "text": line.text,
            "raw_headword": parsed.raw if parsed else "",
            "corrected_headword": parsed.corrected_raw if parsed else "",
            "ocr_parse_text": parsed.parse_text if parsed else line.text,
            "ocr_repairs": list(dict.fromkeys((list(parsed.ocr_repairs) if parsed else []) + list(line.logical_repairs))),
            "logical_repairs": list(line.logical_repairs),
            "normalized_headword": word,
            # Keep the legacy key for tools that already read v1.4 reports.
            "extracted": word,
            "pos_cue": parsed.pos_text if parsed else "",
            "inflection_cue": parsed.inflection_text if parsed else "",
            "descriptor_cue": parsed.descriptor_text if parsed else "",
            "variants": list(parsed.variants) if parsed else [],
            "usage_cue": parsed.usage_text if parsed else "",
            "definition_preview": (parsed.definition_text[:160] if parsed else ""),
            "parser_stage": parsed.parser_stage if parsed else "lemma",
            "parser_trace": list(parsed.parser_trace) if parsed else ["lemma:failed"],
            "bug_types": list(parsed.bug_types) if parsed else ["LEMMA_PARSE_FAILED"],
            "looks_like_continuation": bool(parsed and parsed.looks_like_continuation),
            "continuation_reason": parsed.continuation_reason if parsed else "",
            "confidence": round(line.confidence, 6),
            "box": list(line.box),
            "source_y": source_y,
            "coarse_source_y": coarse_source_y,
            "anchor_source_y": anchor_source_y,
            "separator_refinement": separator_refinement,
            "image_boundary_match": dict(image_boundary) if image_boundary is not None else None,
            "score": round(score, 3),
            "accepted": is_headword,
            "reject_reason": reject_reason,
            "user_rule": {
                "rejected": bool(rule_result["rejected"]),
                "accepted": bool(rule_result["accepted"]),
                "pos_excluded": bool(rule_result["pos_excluded"]),
                "reject_rule": rule_result["reject_rule"],
                "accept_rule": rule_result["accept_rule"],
                "pos_exclude_rule": rule_result["pos_exclude_rule"],
            },
            "features": {
                "at_left": at_left,
                "below_header": below_header,
                "has_pos": has_pos,
                "has_inflection": has_inflection,
                "has_descriptor": has_descriptor,
                "structural_cue": structural_cue,
                "tail_structure_evidence": list(tail_evidence),
                "tail_structure_required": tail_required,
                "tail_structure_satisfied": tail_requirement_ok,
                "front_structure_cue": front_structure_cue,
                "headword_script_guard_enabled": bool(
                    int(
                        getattr(
                            settings,
                            "profile_headword_script_guard_version",
                            0,
                        )
                        or 0
                    ) >= 1
                    and getattr(
                        settings,
                        "profile_headword_script_guard_enabled",
                        True,
                    )
                ),
                "headword_leading_script": leading_script,
                "headword_script_compatible": script_compatible,
                "numbered_prefix_evidence": numbered_prefix_evidence,
                "configured_marker_evidence": configured_marker_evidence,
                **tail_evidence_features,
                "cjk_single_visual": cjk_single_visual,
                "cjk_oversized_recovery": cjk_oversized_recovery,
                "cjk_oversized_recovery_kind": (
                    str(getattr(leading_record, "recovery", "") or "")
                    if cjk_oversized_recovery and leading_record is not None else ""
                ),
                "cjk_at_left": cjk_at_left,
                "cjk_single_prominent": cjk_single_prominent,
                "cjk_single_accept": cjk_single_accept,
                "cjk_single_strong_visual": cjk_single_strong_visual,
                "cjk_single_sparse_context_rescue": cjk_single_sparse_context_rescue,
                **_cjk_candidate_right_context_features(
                    cjk_candidate_right_context
                ),
                "cjk_candidate_right_baseline_supported": bool(
                    cjk_candidate_right_context
                    and cjk_candidate_right_context.get("candidate_baseline_supported")
                ),
                "visual_entry_marker": bool(visual_entry_marker),
                "visual_headword_symbol": bool(visual_entry_marker),
                "visual_entry_marker_type": (
                    str(visual_entry_marker.get("type") or "")
                    if visual_entry_marker else ""
                ),
                "visual_headword_symbol_family": (
                    str(visual_entry_marker.get("family") or "")
                    if visual_entry_marker else ""
                ),
                "visual_headword_symbol_role": (
                    str(visual_entry_marker.get("role") or "")
                    if visual_entry_marker else ""
                ),
                "visual_entry_marker_symbol": (
                    str(visual_entry_marker.get("symbol") or "")
                    if visual_entry_marker else ""
                ),
                "visual_headword_symbol_lane_delta": (
                    float(visual_entry_marker.get("lane_delta") or 0.0)
                    if visual_entry_marker else 0.0
                ),
                "visual_headword_symbol_lane_source": (
                    str(visual_entry_marker.get("lane_source") or "")
                    if visual_entry_marker else ""
                ),
                "visual_headword_symbol_lane_anchor_count": (
                    int(visual_entry_marker.get("lane_anchor_count") or 0)
                    if visual_entry_marker else 0
                ),
                "visual_headword_symbol_lane_tolerance": (
                    float(visual_entry_marker.get("lane_tolerance") or 0.0)
                    if visual_entry_marker else 0.0
                ),
                "visual_headword_symbol_x0": (
                    int(visual_entry_marker.get("x0") or 0)
                    if visual_entry_marker else 0
                ),
                "visual_entry_marker_density": (
                    float(visual_entry_marker.get("density") or 0.0)
                    if visual_entry_marker else 0.0
                ),
                "visual_entry_marker_center_delta": (
                    float(visual_entry_marker.get("center_delta") or 0.0)
                    if visual_entry_marker else 0.0
                ),
                "visual_marker_template_score": (
                    float(visual_entry_marker.get("template_score") or 0.0)
                    if visual_entry_marker else 0.0
                ),
                "visual_marker_template_sample_id": (
                    str(visual_entry_marker.get("template_sample_id") or "")
                    if visual_entry_marker else ""
                ),
                "visual_marker_template_source_page": (
                    str(visual_entry_marker.get("template_source_page") or "")
                    if visual_entry_marker else ""
                ),
                "cjk_marker_prefixed": cjk_marker_prefixed,
                "cjk_bracketed": cjk_bracketed,
                "cjk_bracket_explicit_ocr": cjk_bracket_explicit_ocr,
                "cjk_bracket_explicit_symbol": explicit_bracket_symbol,
                "cjk_bracket_visual_marker": cjk_bracket_visual_marker,
                "cjk_bracket_visual_supported": cjk_bracket_visual_supported,
                "cjk_bracket_extra_required": cjk_bracket_extra_required,
                "cjk_allow_single": cjk_allow_single,
                "cjk_allow_bracketed": cjk_allow_bracketed,
                "cjk_require_left_edge": cjk_require_left_edge,
                "strong_visual_fallback": strong_visual,
                "ordinary_strong_edge_visual_rescue": ordinary_strong_edge_visual_rescue,
                "visual_rescue_threshold_source": str(
                    visual_rescue_thresholds["source"]
                ),
                "visual_rescue_boldness_threshold": round(
                    float(visual_rescue_thresholds["boldness"]), 4
                ),
                "visual_rescue_height_threshold": round(
                    float(visual_rescue_thresholds["height"]), 4
                ),
                "visual_rescue_confidence_threshold": round(
                    float(visual_rescue_thresholds["confidence"]), 4
                ),
                "visual_rescue_left_tolerance": int(settings.paddle_left_tolerance),
                "visual_rescue_candidate_score_threshold": round(
                    float(settings.paddle_min_candidate_score), 4
                ),
                "image_boundary_supported": bool(image_boundary is not None),
                "marker_noise": marker_noise,
                "ordinary_accept": ordinary_accept,
                "forced_accept": bool(rule_result["accepted"]),
                "forced_reject": bool(rule_result["rejected"]),
                "looks_like_continuation": looks_like_continuation,
                "has_prior_content_line": has_prior_content_line,
                "special_symbol": special,
                "internal_article_symbol": internal_symbol,
                "internal_relation_label": relation_label,
                "internal_locution": internal_locution,
                "height_ratio": round(float(height_ratio), 4),
                "leading_record_height_ratio": round(float(leading_record_height_ratio), 4),
                "boldness_ratio": round(float(boldness_ratio), 4),
                "preceding_gap": round(float(preceding_gap), 2),
            },
            "members": [asdict(member) for member in line.records],
        })
        if is_headword:
            accepted.append((score + line.confidence, Entry(
                word=word, x=source_column_x, y=source_y,
                confidence=float(line.confidence), ocr_source=engine_name,
            )))
        previous_bottom = max(previous_bottom, y1)

    # Chinese character dictionaries frequently mix ordinary-size bracketed
    # compounds with oversized single-character heads.  Recover the latter from
    # a left-strip visual projection even when OCR merged the glyph with nearby
    # pronunciation/variant text or shifted its box slightly to the right.
    parser_controls = int(
        getattr(settings, "profile_parser_controls_version", 0) or 0
    ) >= 1
    if _is_chinese_ocr(settings) and (
        not parser_controls
        or bool(getattr(settings, "profile_cjk_allow_single_headword", True))
    ):
        zone_width, visual_runs = _cjk_visual_projection_runs(
            gray, header_cutoff, settings, pixel_scale
        )
        for run_start, run_end in visual_runs:
            right_context = _cjk_right_context_metrics(
                gray,
                (run_start, run_end),
                zone_width,
                settings,
                header_cutoff=header_cutoff,
            )
            word, confidence, matched_record = _cjk_word_for_visual_run(
                records,
                (run_start, run_end),
                zone_width,
                settings,
                active_profile,
                right_context,
            )
            if not word or matched_record is None:
                continue
            coarse_band_y = max(header_cutoff, run_start - row_padding)
            prior_record_bottom = max(
                (int(record.box[3]) for record in records if int(record.box[3]) <= run_start),
                default=header_cutoff,
            )
            visual_gap_hint = max(0, run_start - prior_record_bottom)
            refined_band_y, visual_separator_refinement = refine_separator_y_adaptive(
                separator_gray,
                coarse_band_y,
                max(2, round(median_height)),
                settings,
                pixel_scale=pixel_scale,
                lower_bound=header_cutoff,
                content_top=run_start,
                preceding_gap_hint=visual_gap_hint,
                fallback_refiner=refine_y,
            )
            source_y = source_top + refined_band_y
            visual_anchor_band_y = int((visual_separator_refinement or {}).get("anchor_y", coarse_band_y))
            visual_anchor_source_y = source_top + visual_anchor_band_y
            run_center_source = source_top + (run_start + run_end) // 2
            run_height = max(1, run_end - run_start)

            # If the OCR grammar path already accepted this physical glyph, do
            # not create a second candidate.  Compare the OCR box with the ink
            # run rather than comparing separator-marker Y values: the latter
            # can legitimately differ by 20+ pixels for a large Han glyph.
            existing_cjk = _accepted_cjk_row_for_visual_run(
                diagnostics, run_start, run_end, word
            )
            if existing_cjk is not None:
                # The OCR/grammar path has already produced the entry boundary.
                # The visual run is confirmation/de-duplication evidence only;
                # it must NOT replace a valid separator with a lower line inside
                # the same entry (for example between 播 ba and its Bộ:/radical
                # metadata).  Keep the original marker and store the visual
                # geometry separately for diagnostics.
                existing_cjk.setdefault(
                    "ocr_coarse_source_y", existing_cjk.get("coarse_source_y")
                )
                existing_cjk["visual_confirmation_source_y"] = source_y
                existing_cjk["visual_confirmation_anchor_source_y"] = (
                    visual_anchor_source_y
                )
                existing_cjk["visual_confirmation_separator_refinement"] = (
                    visual_separator_refinement
                )
                features = existing_cjk.setdefault("features", {})
                features["cjk_visual_projection_confirmed"] = True
                features["cjk_visual_run_height"] = run_height
                features["cjk_visual_zone_width"] = zone_width
                features["cjk_visual_run_start"] = int(run_start)
                features["cjk_visual_run_end"] = int(run_end)
                features.update(_cjk_right_context_features(right_context))
                trace = existing_cjk.setdefault("parser_trace", [])
                if "chinese_visual_projection_confirmed" not in trace:
                    trace.append("chinese_visual_projection_confirmed")
                continue

            # Legacy marker-Y proximity is retained as a second guard for rows
            # whose OCR box is unavailable in an imported/cache diagnostic.
            if any(abs(entry.y - source_y) <= max(3, round(run_height * 0.75)) for _rank, entry in accepted):
                continue

            # Reuse the closest diagnostic row when possible so dual-OCR
            # alignment sees one candidate rather than an artificial duplicate.
            nearest: dict[str, Any] | None = None
            nearest_distance = float("inf")
            for row in diagnostics:
                if "meta" in row:
                    continue
                box = row.get("box") or []
                if not isinstance(box, list) or len(box) != 4:
                    continue
                row_center_source = source_top + (int(box[1]) + int(box[3])) / 2.0
                distance = abs(row_center_source - run_center_source)
                if distance <= run_height * 0.80 and distance < nearest_distance:
                    nearest = row
                    nearest_distance = distance

            if nearest is not None:
                nearest["normalized_headword"] = word
                nearest["extracted"] = word
                nearest["accepted"] = True
                nearest["reject_reason"] = ""
                nearest["source_y"] = source_y
                nearest["coarse_source_y"] = source_top + coarse_band_y
                nearest["anchor_source_y"] = visual_anchor_source_y
                nearest["separator_refinement"] = visual_separator_refinement
                context_bonus = 0.75 if right_context.get("sparse") else 0.0
                nearest["score"] = max(
                    float(nearest.get("score") or 0.0), 8.0 + context_bonus
                )
                features = nearest.setdefault("features", {})
                features["cjk_visual_projection_rescue"] = True
                features["cjk_visual_run_height"] = run_height
                features["cjk_visual_zone_width"] = zone_width
                features.update(_cjk_right_context_features(right_context))
                nearest.setdefault("parser_trace", []).append("chinese_visual_projection_rescue")
                nearest["parser_stage"] = "chinese_visual_projection_rescue"
            else:
                diagnostics.append({
                    "text": matched_record.text,
                    "raw_headword": word,
                    "corrected_headword": word,
                    "ocr_parse_text": matched_record.text,
                    "ocr_repairs": [],
                    "logical_repairs": [],
                    "normalized_headword": word,
                    "extracted": word,
                    "pos_cue": "",
                    "inflection_cue": "",
                    "descriptor_cue": "chinese_single_character_visual",
                    "variants": [],
                    "usage_cue": "",
                    "definition_preview": "",
                    "parser_stage": "chinese_visual_projection_rescue",
                    "parser_trace": ["chinese_visual_projection_rescue"],
                    "bug_types": [],
                    "looks_like_continuation": False,
                    "continuation_reason": "",
                    "confidence": round(confidence, 6),
                    "box": list(matched_record.box),
                    "source_y": source_y,
                    "coarse_source_y": source_top + coarse_band_y,
                    "anchor_source_y": visual_anchor_source_y,
                    "separator_refinement": visual_separator_refinement,
                    "score": 8.0 + (
                        0.75 if right_context.get("sparse") else 0.0
                    ),
                    "accepted": True,
                    "reject_reason": "",
                    "user_rule": {
                        "rejected": False, "accepted": False, "pos_excluded": False,
                        "reject_rule": "", "accept_rule": "", "pos_exclude_rule": "",
                    },
                    "features": {
                        "at_left": True,
                        "below_header": True,
                        "has_pos": False,
                        "has_inflection": False,
                        "has_descriptor": False,
                        "structural_cue": False,
                        "cjk_single_visual": True,
                        "cjk_at_left": True,
                        "cjk_single_prominent": True,
                        "cjk_single_accept": True,
                        "cjk_visual_projection_rescue": True,
                        "cjk_visual_run_height": run_height,
                        "cjk_visual_zone_width": zone_width,
                        **_cjk_right_context_features(right_context),
                        "strong_visual_fallback": True,
                        "marker_noise": False,
                        "ordinary_accept": False,
                        "forced_accept": False,
                        "forced_reject": False,
                        "looks_like_continuation": False,
                        "has_prior_content_line": True,
                        "special_symbol": False,
                        "internal_article_symbol": False,
                        "internal_relation_label": False,
                        "internal_locution": False,
                        "height_ratio": round(run_height / median_height, 4),
                        "leading_record_height_ratio": round(run_height / median_height, 4),
                        "boldness_ratio": 0.0,
                        "preceding_gap": 0.0,
                    },
                    "members": [asdict(matched_record)],
                })
            accepted.append((8.0 + confidence, Entry(
                word=word, x=source_column_x, y=source_y,
                confidence=confidence, ocr_source=engine_name,
            )))

    accepted.sort(key=lambda item: item[1].y)
    deduplicated: list[tuple[float, Entry]] = []
    tolerance = max(2, round(character_height * 0.5))
    for item in accepted:
        if deduplicated and item[1].y - deduplicated[-1][1].y <= tolerance:
            if item[0] > deduplicated[-1][0]:
                deduplicated[-1] = item
        else:
            deduplicated.append(item)
    annotate_peer = peer_typography_annotator or _annotate_peer_typography_matches
    peer_typography_match_count = annotate_peer(diagnostics)
    diagnostics.insert(0, {
        "meta": {
            "header_cutoff_band_y": header_cutoff,
            "_header_cutoff_axis_v": source_top + header_cutoff,
            "line_count": len(lines),
            "left_limit_band_x": left_limit,
            "separator_band_width": int(separator_gray.shape[1]),
            "separator_roi_width_ratio": float(getattr(settings, "paddle_separator_roi_width_ratio", 60.0)),
            "image_separator_candidates": image_separator_candidates,
            "image_separator_match_count": len(image_boundary_matches),
            "trusted_visual_marker_lanes": trusted_visual_lanes,
            "visual_marker_candidate_count": len(visual_entry_markers),
            "peer_typography_match_count": int(peer_typography_match_count),
            "user_filter_rule_count": len(user_rules or []),
        }
    })
    return [entry for _, entry in deduplicated], diagnostics

