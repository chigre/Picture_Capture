"""Complete image-to-cached-headword multi-engine OCR page detection.

Canonical owner of a page's enabled Paddle/Tesseract/Lens OCR passes,
canonical column extraction, cache loading, supplementary OCR rescue,
multi-engine pairing/arbitration, review choice, and compact v3 persistence.

The heavy legacy OCR core supplies original patchable callbacks, parser
models, and profile policies per invocation, not via global installers or
a cyclic core import. GUI and native engines remain lazy.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING
import json

import numpy as np
from PIL import Image

from ..models import AppSettings, Entry
from ..persistence.page_sections import PageSection
from .headword_models import OCRRecord

if TYPE_CHECKING:
    from ..processing import Geometry


@dataclass(frozen=True)
class PageDetectionDeps:
    """Historical monkeypatchable OCR page operations bound at call time."""
    load_headword_filter_rules: object
    unwrap_column_band: object
    run_paddle_band: object
    _records_to_canonical_band: object
    run_tesseract_band_records: object
    _recover_oversized_cjk_ocr_records: object
    _recover_image_first_oversized_cjk_records: object
    _suppress_raw_records_shadowed_by_verified_cjk_recovery: object
    filter_headword_records: object
    _attach_source_candidate_coordinates: object
    _candidate_axis_v: object
    _cache_signature: object
    _records_as_merged_lines: object
    _candidate_rows: object
    _annotate_alphabetical_warnings: object
    _apply_alphabetical_warnings_to_entries: object
    _eligible_alignment_rows: object
    _pair_ocr_candidates: object
    _pairs_need_lens: object
    _make_ocr_pair: object
    _pair_with_lens_candidates: object
    _issues_for_pair: object
    _arbitrate_pair: object
    _apply_pair_engine_position: object
    _agreement_summary: object
    _atomic_write_json: object
    compact_ocr_cache_payload: object
    _regenerable_sidecars: object
    _expand_original_y_fallback_candidates: object
    _enforce_position_variant_exclusivity: object
    _load_manual_selection_overrides: object
    _apply_manual_selection_overrides: object
    _deduplicate_selected_cjk_review_candidates: object
    _entries_from_review_candidates: object
    _update_project_quality_summary: object
    PROFILE_FILENAME: object
    effective_project_profile_id: object
    load_dictionary_profile: object
    resolved_tesseract_language: object
    tesseract_status: object
    run_google_lens: object
    normalize_page_rgb: object
    OCRRecord: object
    asdict: object


def detect_paddle_headwords(
    deps: PageDetectionDeps, 
    image: Image.Image,
    geometry: "Geometry",
    settings: AppSettings,
    cache_path: Path | None = None,
    force_refresh: bool = False,
    engine: Any | None = None,
    filter_rules_path: Path | None = None,
    page_sections: list[PageSection] | None = None,
    record_filter: Any | None = None,
) -> list[Entry]:
    """Run the mature multi-OCR dictionary headword pipeline."""
    load_headword_filter_rules = deps.load_headword_filter_rules
    unwrap_column_band = deps.unwrap_column_band
    run_paddle_band = deps.run_paddle_band
    _records_to_canonical_band = deps._records_to_canonical_band
    run_tesseract_band_records = deps.run_tesseract_band_records
    _recover_oversized_cjk_ocr_records = deps._recover_oversized_cjk_ocr_records
    _recover_image_first_oversized_cjk_records = deps._recover_image_first_oversized_cjk_records
    _suppress_raw_records_shadowed_by_verified_cjk_recovery = deps._suppress_raw_records_shadowed_by_verified_cjk_recovery
    filter_headword_records = deps.filter_headword_records
    _attach_source_candidate_coordinates = deps._attach_source_candidate_coordinates
    _candidate_axis_v = deps._candidate_axis_v
    _cache_signature = deps._cache_signature
    _records_as_merged_lines = deps._records_as_merged_lines
    _candidate_rows = deps._candidate_rows
    _annotate_alphabetical_warnings = deps._annotate_alphabetical_warnings
    _apply_alphabetical_warnings_to_entries = deps._apply_alphabetical_warnings_to_entries
    _eligible_alignment_rows = deps._eligible_alignment_rows
    _pair_ocr_candidates = deps._pair_ocr_candidates
    _pairs_need_lens = deps._pairs_need_lens
    _make_ocr_pair = deps._make_ocr_pair
    _pair_with_lens_candidates = deps._pair_with_lens_candidates
    _issues_for_pair = deps._issues_for_pair
    _arbitrate_pair = deps._arbitrate_pair
    _apply_pair_engine_position = deps._apply_pair_engine_position
    _agreement_summary = deps._agreement_summary
    _atomic_write_json = deps._atomic_write_json
    compact_ocr_cache_payload = deps.compact_ocr_cache_payload
    _regenerable_sidecars = deps._regenerable_sidecars
    _expand_original_y_fallback_candidates = deps._expand_original_y_fallback_candidates
    _enforce_position_variant_exclusivity = deps._enforce_position_variant_exclusivity
    _load_manual_selection_overrides = deps._load_manual_selection_overrides
    _apply_manual_selection_overrides = deps._apply_manual_selection_overrides
    _deduplicate_selected_cjk_review_candidates = deps._deduplicate_selected_cjk_review_candidates
    _entries_from_review_candidates = deps._entries_from_review_candidates
    _update_project_quality_summary = deps._update_project_quality_summary
    PROFILE_FILENAME = deps.PROFILE_FILENAME
    effective_project_profile_id = deps.effective_project_profile_id
    load_dictionary_profile = deps.load_dictionary_profile
    resolved_tesseract_language = deps.resolved_tesseract_language
    tesseract_status = deps.tesseract_status
    run_google_lens = deps.run_google_lens
    normalize_page_rgb = deps.normalize_page_rgb
    OCRRecord = deps.OCRRecord
    asdict = deps.asdict

    filter_records = record_filter or filter_headword_records
    signature = _cache_signature(image, geometry, settings)
    runtime_width = geometry.transform.canonical_size(image.size)[0]
    pixel_scale = 1.0
    canonical_character_height = int(settings.character_height)
    user_rules = load_headword_filter_rules(filter_rules_path)
    profile_path = filter_rules_path.parent / PROFILE_FILENAME if filter_rules_path else None
    profile = load_dictionary_profile(
        profile_path,
        preset=effective_project_profile_id(settings, profile_path),
        language=settings.ocr_language,
    )
    cached_columns: list[dict[str, Any]] | None = None
    if cache_path and cache_path.exists() and not force_refresh:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("signature") == signature:
                cached_columns = list(cached.get("columns") or [])
        except (OSError, ValueError, TypeError):
            cached_columns = None

    report_columns: list[dict[str, Any]] = []
    # Main-window engine checkboxes are authoritative. Arbitration is applied
    # only among engines that the user explicitly enabled.
    use_paddle = bool(getattr(settings, "paddle_use_paddleocr", True))
    use_tesseract = bool(settings.paddle_compare_tesseract or settings.paddle_tesseract_rescue)
    tess_language = resolved_tesseract_language(settings)
    tess_availability = tesseract_status(settings.ocr_executable, tess_language) if use_tesseract else {}
    raw_tesseract_cache = None
    if (
        use_tesseract and cache_path is not None
        and bool(getattr(settings, "ocr_cache_tesseract_raw", False))
    ):
        from .tesseract_raw_cache import TesseractRawCache
        raw_tesseract_cache = TesseractRawCache(
            cache_path, signature, language=tess_language,
            executable=str(settings.ocr_executable),
            auto_psm=bool(settings.paddle_tesseract_auto_psm),
            fixed_psm=int(settings.paddle_tesseract_psm),
            vertical=str(getattr(settings, "layout_writing_mode", "")).startswith("vertical"),
            engine_status=tess_availability,
            force_refresh=force_refresh,
        )
    lens_mode = str(settings.paddle_lens_mode or "off").strip().lower()
    if not bool(getattr(settings, "paddle_enable_lens", False)):
        lens_mode = "off"
    if lens_mode not in {"off", "diagnostic", "conflict", "full"}:
        lens_mode = "off"
    if not (use_paddle or use_tesseract or lens_mode != "off"):
        raise RuntimeError("至少选择一个 OCR 引擎后才能运行 OCR 画线。")

    # Build the full-page RGB array once per OCR invocation.  Column-band
    # extraction used to reconvert the whole page for every band, which raised
    # peak memory substantially on high-resolution scans.  This object is local
    # to the current page/call, so zoom changes, page changes, or later parameter
    # edits can never reuse pixels from another page.
    oriented = normalize_page_rgb(image)
    shared_source_rgb = np.asarray(oriented)

    for col, canonical_u in enumerate(geometry.column_starts):
        band, source_top, left_margin = unwrap_column_band(
            image, geometry, col, settings, source_rgb=shared_source_rgb,
        )
        separator_width = max(24, int(geometry.column_widths[col] + left_margin))
        separator_band, _, _ = unwrap_column_band(
            image, geometry, col, settings, source_width=separator_width,
            source_rgb=shared_source_rgb,
        )
        transform_kind = geometry.transform.kind
        analysis_band = geometry.transform.canonical_image_for_analysis(band)
        analysis_separator_band = geometry.transform.canonical_image_for_analysis(separator_band)

        if cached_columns is not None and col < len(cached_columns):
            records = [OCRRecord(
                text=str(item["text"]),
                confidence=float(item["confidence"]),
                box=tuple(int(value) for value in item["box"]),  # type: ignore[arg-type]
                recovery=str(item.get("recovery", "") or ""),
                recovery_source_text=str(
                    item.get("recovery_source_text", "") or ""
                ),
                parent_box=(
                    tuple(int(value) for value in item["parent_box"])
                    if item.get("parent_box") else None
                ),
            ) for item in cached_columns[col].get("ocr_records", [])]
        elif use_paddle:
            source_records = run_paddle_band(band, settings, engine=engine)
            records = _records_to_canonical_band(
                source_records, band.size, transform_kind
            )
        else:
            records = []

        # Preserve raw Paddle records as the cache contract. Multi-entry CJK
        # recovery is Profile-dependent candidate interpretation and therefore
        # must be recomputed from raw records whenever Profile settings change.
        raw_paddle_records = list(records)
        oversized_recovery: list[dict[str, Any]] = []
        if use_paddle:
            if records:
                records, giant_box_recovery = _recover_oversized_cjk_ocr_records(
                    records,
                    analysis_band,
                    settings,
                    profile,
                    engine=engine,
                    pixel_scale=pixel_scale,
                )
                oversized_recovery.extend(giant_box_recovery)
            records, image_first_recovery = _recover_image_first_oversized_cjk_records(
                records,
                analysis_band,
                settings,
                profile,
                engine=engine,
                pixel_scale=pixel_scale,
            )
            oversized_recovery.extend(image_first_recovery)
            records, recovery_duplicate_suppression = (
                _suppress_raw_records_shadowed_by_verified_cjk_recovery(
                    records
                )
            )
            oversized_recovery.extend(recovery_duplicate_suppression)

        paddle_lines = _records_as_merged_lines(records, settings)
        paddle_full_text = "\n".join(line.text for line in paddle_lines)
        paddle_entries, diagnostics = filter_records(
            records, analysis_band, source_top, canonical_u, settings,
            separator_band=analysis_separator_band, user_rules=user_rules, engine_name="paddle", profile=profile,
            pixel_scale=pixel_scale,
        )
        if oversized_recovery and diagnostics:
            meta = diagnostics[0].get("meta")
            if isinstance(meta, dict):
                meta["oversized_multi_entry_recovery"] = oversized_recovery
        _attach_source_candidate_coordinates(diagnostics, geometry, col)
        for entry in paddle_entries:
            entry.x, entry.y = geometry.canonical_to_source(entry.x, entry.y)

        tess_payload: dict[str, Any] = {
            "enabled": use_tesseract,
            "rescue_enabled": bool(settings.paddle_tesseract_rescue),
            "arbitration_enabled": bool(settings.paddle_dual_ocr_arbitration),
            "language": tess_language,
            "psm": settings.paddle_tesseract_psm,
            "auto_psm": bool(settings.paddle_tesseract_auto_psm),
            "availability": tess_availability,
            "variants": [],
            "full_text": "",
            "records": [],
            "candidates": [],
            "accepted_count": 0,
            "error": "",
        }
        tess_entries: list[Entry] = []
        tess_diagnostics: list[dict[str, Any]] = []
        skip_secondary_diagnostic = False
        if bool(getattr(settings, "ocr_lazy_tesseract_diagnostics", False)):
            from .lazy_secondary import can_skip_tesseract_diagnostic_column
            skip_secondary_diagnostic = can_skip_tesseract_diagnostic_column(
                diagnostics, enabled=True, paddle_enabled=use_paddle,
                tesseract_enabled=use_tesseract,
                rescue_enabled=bool(settings.paddle_tesseract_rescue),
                arbitration_enabled=bool(settings.paddle_dual_ocr_arbitration),
                lens_mode=lens_mode,
            )
        if skip_secondary_diagnostic:
            tess_payload["skipped"] = True
            tess_payload["skip_reason"] = "diagnostic_only_high_trust_paddle_column"
        if use_tesseract and not skip_secondary_diagnostic:
            if str(getattr(settings, "layout_writing_mode", "horizontal-tb")).startswith("vertical"):
                psm_values = [5]
            else:
                psm_values = [4, 6] if settings.paddle_tesseract_auto_psm else [max(3, int(settings.paddle_tesseract_psm))]
            variants: list[tuple[tuple[float, ...], int, list[OCRRecord], str, list[Entry], list[dict[str, Any]]]] = []
            errors: list[str] = []
            for psm in dict.fromkeys(psm_values):
                try:
                    cached_tess = (
                        raw_tesseract_cache.read(col, psm)
                        if raw_tesseract_cache is not None else None
                    )
                    if cached_tess is None:
                        source_candidate_records, candidate_text = run_tesseract_band_records(
                            band, settings, psm_override=psm
                        )
                        candidate_records = _records_to_canonical_band(
                            source_candidate_records, band.size, transform_kind
                        )
                        if raw_tesseract_cache is not None:
                            raw_tesseract_cache.record(
                                col, psm, [asdict(record) for record in candidate_records],
                                candidate_text,
                            )
                    else:
                        raw_records, candidate_text = cached_tess
                        candidate_records = [
                            OCRRecord(
                                text=str(raw["text"]),
                                confidence=float(raw["confidence"]),
                                box=tuple(int(v) for v in raw["box"]),
                                recovery=str(raw.get("recovery", "") or ""),
                                recovery_source_text=str(raw.get("recovery_source_text", "") or ""),
                                parent_box=(
                                    tuple(int(v) for v in raw["parent_box"])
                                    if raw.get("parent_box") else None
                                ),
                            )
                            for raw in raw_records
                        ]
                    candidate_entries, candidate_diagnostics = filter_records(
                        candidate_records, analysis_band, source_top, canonical_u, settings,
                        separator_band=analysis_separator_band, user_rules=user_rules,
                        engine_name="tesseract", profile=profile,
                        pixel_scale=pixel_scale,
                    )
                    _attach_source_candidate_coordinates(
                        candidate_diagnostics, geometry, col,
                    )
                    for entry in candidate_entries:
                        entry.x, entry.y = geometry.canonical_to_source(entry.x, entry.y)
                    structural = sum(
                        1 for row in _candidate_rows(candidate_diagnostics)
                        if (row.get("features", {}) or {}).get("structural_cue")
                    )
                    mean_conf = (
                        sum(record.confidence for record in candidate_records) / len(candidate_records)
                        if candidate_records else 0.0
                    )
                    rank = (float(len(candidate_entries)), float(structural), mean_conf, float(len(candidate_records)))
                    variants.append((rank, psm, candidate_records, candidate_text, candidate_entries, candidate_diagnostics))
                    tess_payload["variants"].append({
                        "psm": psm, "records": len(candidate_records),
                        "accepted": len(candidate_entries), "structural": structural,
                        "mean_confidence": round(mean_conf, 4),
                    })
                except Exception as exc:
                    errors.append(f"PSM {psm}: {exc}")
                    tess_payload["variants"].append({"psm": psm, "error": str(exc)})
            if variants:
                _rank, chosen_psm, tess_records, tess_full_text, tess_entries, tess_diagnostics = max(variants, key=lambda item: item[0])
                tess_payload.update({
                    "psm": chosen_psm,
                    "full_text": tess_full_text,
                    "records": [asdict(record) for record in tess_records],
                    "candidates": tess_diagnostics,
                    "accepted_count": len(tess_entries),
                })
            else:
                tess_payload["error"] = " | ".join(errors) or str(tess_availability.get("error") or "Tesseract 不可用")

        if skip_secondary_diagnostic:
            tess_payload["accepted_count"] = 0
        compare_tolerance = max(
            4,
            round(
                canonical_character_height
                * max(0.35, settings.paddle_alignment_y_tolerance_ratio)
            ),
        )
        pre_pairs = (
            _pair_ocr_candidates(diagnostics, tess_diagnostics, compare_tolerance, settings.paddle_alignment_min_similarity)
            if tess_diagnostics else [
                _make_ocr_pair(item, None, "paddle_only_no_secondary")
                for item in _eligible_alignment_rows(diagnostics)
            ]
        )
        lens_attempted = lens_mode in {"diagnostic", "full"} or (
            lens_mode == "conflict" and (_pairs_need_lens(pre_pairs) or not pre_pairs)
        )
        # Lens language is deliberately derived from the active headword OCR
        # language. Keep the persisted legacy field only for compatibility.
        lens_language = str(
            getattr(settings, "ocr_language", "")
            or getattr(settings, "paddle_lens_language", "")
            or ""
        )
        lens_payload: dict[str, Any] = {
            "enabled": lens_mode != "off", "mode": lens_mode, "attempted": lens_attempted,
            "language": lens_language, "version": "", "full_text": "",
            "records": [], "candidates": [], "accepted_count": 0, "error": "",
            "confidence_source": "neutral_default; typography_from_original_bbox",
        }
        if lens_attempted:
            try:
                raw_lens_records, lens_full_text, lens_version = run_google_lens(
                    band, language=lens_language,
                    timeout=settings.paddle_lens_timeout,
                    default_confidence=settings.paddle_lens_default_confidence,
                )
                source_lens_records = [
                    OCRRecord(text, confidence, box) for text, confidence, box in raw_lens_records
                ]
                lens_records = _records_to_canonical_band(
                    source_lens_records, band.size, transform_kind
                )
                lens_entries, lens_diagnostics = filter_records(
                    lens_records, analysis_band, source_top, canonical_u, settings,
                    separator_band=analysis_separator_band, user_rules=user_rules,
                    engine_name="lens", profile=profile,
                )
                _attach_source_candidate_coordinates(
                    lens_diagnostics, geometry, col,
                )
                lens_payload.update({
                    "version": lens_version, "full_text": lens_full_text,
                    "records": [asdict(record) for record in lens_records],
                    "candidates": lens_diagnostics, "accepted_count": len(lens_entries),
                })
            except Exception as exc:
                lens_payload["error"] = str(exc)

        report_columns.append({
            "column": col,
            "_column_axis_u": int(canonical_u),
            "_top_axis_v": int(source_top),
            "band_size": list(band.size),
            "ocr_records": [asdict(record) for record in raw_paddle_records],
            "paddle_effective_records": [
                asdict(record) for record in records
            ],
            "paddle_full_text": paddle_full_text,
            "paddle_merged_lines": [
                {
                    "text": line.text,
                    "confidence": round(line.confidence, 6),
                    "box": list(line.box),
                    "members": [asdict(member) for member in line.records],
                    "logical_repairs": list(line.logical_repairs),
                }
                for line in paddle_lines
            ],
            "candidates": diagnostics,
            "paddle_accepted_count": len(paddle_entries),
            "tesseract": tess_payload,
            "lens": lens_payload,
            # v2 fills these after alphabetical annotation so arbitration sees
            # the warning metadata from both engines.
            "ocr_y_comparison": [],
            "review_candidates": [],
        })

    # Alphabetical order remains a weak warning only. It is computed before OCR
    # arbitration so a suspicious engine result can contribute to review issues.
    alphabetical_warnings = _annotate_alphabetical_warnings(
        report_columns, page_sections,
        top_v=geometry.top, bottom_v=geometry.bottom,
    )

    review_candidates: list[dict[str, Any]] = []
    for col in report_columns:
        col_index = int(col.get("column", 0))
        canonical_u = int(col.get("_column_axis_u", 0))
        band_width = max(
            1,
            int((col.get("band_size") or [settings.paddle_band_width])[0]),
        )
        source_line_height = max(1.0, float(canonical_character_height))
        compare_tolerance = max(
            4,
            round(source_line_height * max(0.35, settings.paddle_alignment_y_tolerance_ratio)),
        )
        final_line_dedup_tolerance = max(2, round(source_line_height * _FINAL_LINE_DEDUP_RATIO))
        tess = col.get("tesseract", {}) or {}
        tess_rows = list(tess.get("candidates", []) or []) if use_tesseract and not tess.get("error") else []
        if tess_rows:
            pairs = _pair_ocr_candidates(
                col.get("candidates", []), tess_rows, compare_tolerance,
                settings.paddle_alignment_min_similarity,
            )
        else:
            pairs = [
                _make_ocr_pair(item, None, "paddle_only_no_secondary")
                for item in _eligible_alignment_rows(col.get("candidates", []))
            ]
        lens = col.get("lens", {}) or {}
        lens_rows = list(lens.get("candidates", []) or []) if lens.get("attempted") and not lens.get("error") else []
        if lens_rows:
            pairs = _pair_with_lens_candidates(
                pairs, lens_rows, compare_tolerance,
                settings.paddle_alignment_min_similarity,
            )
        col["ocr_y_comparison"] = pairs

        column_review: list[dict[str, Any]] = []
        if settings.paddle_dual_ocr_arbitration or not tess_rows:
            for pair in pairs:
                column_review.append(_arbitrate_pair(pair, col_index, canonical_u, settings, geometry=geometry))
        else:
            # Compatibility mode: Paddle remains authoritative; optional legacy
            # Tesseract rescue can still promote structurally strong missing rows.
            paddle_selected_v = {
                int(_candidate_axis_v(c) or 0)
                for c in _candidate_rows(col.get("candidates", [])) if c.get("accepted")
            }
            for pair in pairs:
                item = _arbitrate_pair(pair, col_index, canonical_u, settings, geometry=geometry)
                py = pair.get("paddle_y")
                if py is not None:
                    item["selected"] = int(py) in paddle_selected_v
                    item["final_engine"] = "paddle"
                    item["word"] = str(pair.get("paddle_lemma", ""))
                    _apply_pair_engine_position(
                        item, pair, "paddle", col_index, canonical_u, geometry,
                    )
                    item["confidence"] = pair.get("paddle_conf")
                    item["score"] = pair.get("paddle_score")
                    item["decision_reason"] = "compat_paddle_authoritative"
                elif settings.paddle_tesseract_rescue and pair.get("tesseract_accepted"):
                    features = pair.get("tesseract_features", {}) or {}
                    if features.get("structural_cue"):
                        item["selected"] = True
                        item["decision_reason"] = "compat_tesseract_rescue"
                else:
                    item["selected"] = False
                # Recompute issue list after compatibility selection.
                chosen = str(item.get("final_engine", ""))
                item["issue_types"] = _issues_for_pair(pair, chosen, bool(item.get("needs_review")))
                column_review.append(item)
        for item in column_review:
            item["line_dedup_tolerance"] = final_line_dedup_tolerance
            item["line_height_reference"] = round(source_line_height, 3)
        col["review_candidates"] = column_review
        review_candidates.extend(column_review)

    # Preserve the pre-refinement marker Y as an unchecked fallback candidate.
    # This is added only after OCR arbitration so it cannot influence engine
    # pairing or candidate scoring.
    original_y_fallbacks = _expand_original_y_fallback_candidates(review_candidates)

    # Manual checkbox/review choices have the highest final-selection priority,
    # while parser/OCR data stays untouched for reproducibility.
    overrides = _load_manual_selection_overrides(cache_path)
    _apply_manual_selection_overrides(review_candidates, overrides)
    _enforce_position_variant_exclusivity(review_candidates)
    cjk_duplicates_merged = _deduplicate_selected_cjk_review_candidates(review_candidates)
    all_entries = _entries_from_review_candidates(review_candidates)
    _apply_alphabetical_warnings_to_entries(report_columns, all_entries)

    agreement = _agreement_summary(review_candidates)
    if not use_tesseract and lens_mode == "off":
        agreement["agreement"] = 1.0
    agreement["secondary_diagnostic_columns_skipped"] = sum(
        1 for col in report_columns
        if bool((col.get("tesseract", {}) or {}).get("skipped"))
    )
    agreement["selected"] = sum(1 for item in review_candidates if item.get("selected"))
    agreement["cjk_duplicates_merged"] = cjk_duplicates_merged
    agreement["original_y_fallbacks"] = original_y_fallbacks
    agreement["issues"] = sum(
        1 for item in review_candidates
        if str(item.get("position_variant", "refined")) != "original" and item.get("issue_types")
    )
    agreement["needs_review"] = sum(
        1 for item in review_candidates
        if str(item.get("position_variant", "refined")) != "original" and item.get("needs_review")
    )

    # Keep per-column selected count for readers/tools that used the v1 format.
    for col in report_columns:
        col["accepted_count"] = sum(1 for item in col.get("review_candidates", []) if item.get("selected"))

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "picture-capture-headwords-v3",
            "signature": signature,
            "coordinate_space": "source_image_pixels",
            "filter_rules_path": str(filter_rules_path) if filter_rules_path else "",
            "filter_rule_count": len(user_rules),
            "dictionary_profile": {
                "key": profile.key,
                "name": profile.name,
                "family": profile.family,
                "parser_modes": list(profile.parser_modes),
                "path": str(profile_path) if profile_path and profile_path.exists() else "bundled",
                "pos_labels": len(profile.pos_labels),
                "metadata_labels": len(profile.metadata_labels),
            },
            "dual_ocr": {
                "paddleocr": use_paddle,
                "tesseract_compare": use_tesseract,
                "tesseract_rescue": bool(settings.paddle_tesseract_rescue),
                "arbitration": bool(settings.paddle_dual_ocr_arbitration),
                "tesseract_language": tess_language,
                "tesseract_psm": settings.paddle_tesseract_psm,
                "tesseract_auto_psm": bool(settings.paddle_tesseract_auto_psm),
                "tesseract_status": tess_availability,
                "google_lens_mode": lens_mode,
                "google_lens_language": lens_language,
            },
            "alphabetical_warnings": alphabetical_warnings,
            "page_quality": agreement,
            "review_candidates": review_candidates,
            "manual_override_count": len(overrides),
            "final_entries": [asdict(entry) for entry in all_entries],
            "columns": report_columns,
        }
        # Persist a compact reusable cache. Rich engine-by-engine diagnostics are
        # intentionally runtime-only; historically duplicating them into five
        # text/TSV sidecars made large dictionary projects grow unnecessarily.
        payload = compact_ocr_cache_payload(payload)
        _atomic_write_json(cache_path, payload)
        for obsolete in _regenerable_sidecars(cache_path):
            obsolete.unlink(missing_ok=True)
        _update_project_quality_summary(cache_path, agreement, review_candidates)
        if raw_tesseract_cache is not None:
            try:
                raw_tesseract_cache.save()
            except OSError:
                # A failed *optional* engine cache must never discard a valid
                # final OCR detection or saved primary cache.
                pass

    return all_entries
