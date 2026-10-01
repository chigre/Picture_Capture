from __future__ import annotations

"""Runtime bridge from final Layout rows to canonical Entry classification."""

from pathlib import Path
from typing import Any

from .entry_classification import (
    copy_layout_line_classification,
    get_entry_classification,
)
from .entry_ocr_crop import (
    entry_ocr_crop_box,
    resolve_entry_ocr_row_metrics,
)


def _install_marker_ocr_crop(processing_module: Any) -> None:
    """Make existing-marker OCR consume the canonical classification crop box."""
    core = processing_module._core
    if getattr(core, "_entry_classification_crop_installed", False):
        return

    def classified_marker_crop(
        canonical,
        entry,
        geometry,
        settings,
        *,
        row_metrics=None,
    ):
        box = entry_ocr_crop_box(
            entry,
            geometry,
            settings,
            canonical.size,
            row_metrics=row_metrics,
        )
        meta = get_entry_classification(entry)
        return core.normalize_page_rgb(canonical.crop(box)), meta.entry_scale == "oversized"

    core._ordinary_marker_local_crop = classified_marker_crop
    processing_module._ordinary_marker_local_crop = classified_marker_crop
    core._entry_classification_crop_installed = True


def _install_marker_ocr_engine_dispatch(processing_module: Any) -> None:
    """Make 【仅OCR】 honor the configured OCR engine on one shared crop."""
    core = processing_module._core
    if getattr(core, "_entry_marker_ocr_dispatch_installed", False):
        return

    def ocr_existing_entry_words_from_markers(
        image,
        entries,
        settings,
        replace_rules,
        *,
        profile_page_index: int = 0,
        page_sections=None,
        profile_path: Path | None = None,
        only_blank: bool = True,
    ):
        _source, effective, analysis_source, geometry = core._page_geometry_context(
            image, settings, profile_page_index,
        )
        canonical = geometry.transform.canonical_image_for_analysis(analysis_source)
        ordered = core.sort_entries_reading_order(entries, geometry, page_sections)
        row_metrics = resolve_entry_ocr_row_metrics(
            image,
            settings,
            page_index=profile_page_index,
        )

        from .dictionary_profile import effective_project_profile_id, load_dictionary_profile
        from .paddle_headwords import parse_headword_text

        profile = load_dictionary_profile(
            profile_path,
            preset=effective_project_profile_id(effective, profile_path),
            language=effective.ocr_language,
        )
        stats = {
            "total": len(ordered),
            "filled": 0,
            "large": 0,
            "regular": 0,
            "failed": 0,
            "skipped_existing": 0,
            "skipped_manual": 0,
        }
        targets = [
            entry for entry in ordered
            if not (
                (only_blank and str(entry.word or "").strip())
                or bool(entry.manually_selected)
            )
        ]
        stats["skipped_existing"] = sum(
            1 for entry in ordered if only_blank and str(entry.word or "").strip()
        )
        stats["skipped_manual"] = sum(
            1 for entry in ordered
            if bool(entry.manually_selected)
            and not (only_blank and str(entry.word or "").strip())
        )
        if not targets:
            return ordered, stats

        engine_name = str(
            getattr(effective, "ocr_engine", "tesseract") or "tesseract"
        ).strip().lower()
        paddle_engine = None
        if engine_name == "paddleocr":
            from .paddle_headwords import get_paddle_engine
            paddle_engine = get_paddle_engine(effective)

        def parsed_or_raw(raw: str) -> str:
            text = str(raw or "").strip()
            if not text:
                return ""
            parsed = parse_headword_text(text, effective, profile=profile)
            if parsed is not None and str(parsed.normalized or "").strip():
                return str(parsed.normalized).strip()
            first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
            return first_line[:64].strip()

        for entry in targets:
            original_x, original_y = int(entry.x), int(entry.y)
            crop, is_large = core._ordinary_marker_local_crop(
                canonical,
                entry,
                geometry,
                effective,
                row_metrics=row_metrics,
            )
            stats["large" if is_large else "regular"] += 1
            word = ""
            confidence = None

            try:
                if engine_name == "paddleocr":
                    from .paddle_headwords import (
                        _single_cjk_from_local_records,
                        group_ocr_records,
                        recognize_paddle_text,
                        run_paddle_band,
                    )
                    records = run_paddle_band(crop, effective, engine=paddle_engine)
                    if records and is_large:
                        word, confidence_value, _source_text = _single_cjk_from_local_records(
                            records,
                            effective,
                            profile,
                            max_left_x=max(16, round(crop.width * 0.75)),
                        )
                        confidence = float(confidence_value) if word else None
                    elif records:
                        lines = group_ocr_records(
                            records,
                            float(getattr(effective, "paddle_line_merge_y_ratio", 0.55) or 0.55),
                        )
                        for line in sorted(
                            lines,
                            key=lambda value: (
                                int(value.box[0]), int(value.box[1]), -float(value.confidence),
                            ),
                        ):
                            word = parsed_or_raw(str(line.text or ""))
                            if word:
                                confidence = float(line.confidence)
                                break
                    if not word:
                        word = parsed_or_raw(
                            recognize_paddle_text(crop, effective, engine=paddle_engine)
                        )
                else:
                    psm = (
                        5
                        if str(getattr(effective, "layout_writing_mode", "")).startswith("vertical")
                        else 7
                    )
                    raw = core.run_tesseract(
                        crop,
                        core.resolved_tesseract_language(effective),
                        effective.ocr_executable,
                        psm=psm,
                    )
                    word = parsed_or_raw(raw)
            except Exception:
                word = ""

            if word:
                if effective.ocr_replace:
                    word = core.process_ocr_text(
                        word, replace_rules, bool(effective.lowercase_ocr)
                    )
                entry.word = str(word).strip()
                entry.confidence = confidence
                paddle = engine_name == "paddleocr"
                entry.ocr_source = f"ordinary_marker:{'paddle' if paddle else 'tesseract'}"
                entry.final_engine = "paddle" if paddle else "tesseract"
                issue = "ORDINARY_MARKER_TEXT_OCR"
                existing = [part for part in str(entry.issue_type or "").split(",") if part]
                if issue not in existing:
                    existing.append(issue)
                    entry.issue_type = ",".join(existing)
                stats["filled"] += 1
            else:
                stats["failed"] += 1

            if int(entry.x) != original_x or int(entry.y) != original_y:
                raise RuntimeError("普通画线后OCR文字不得修改任何画线坐标")

        return ordered, stats

    core.ocr_existing_entry_words_from_markers = ocr_existing_entry_words_from_markers
    processing_module.ocr_existing_entry_words_from_markers = ocr_existing_entry_words_from_markers
    core._entry_marker_ocr_dispatch_installed = True


def install_processing_entry_classification(processing_module: Any) -> None:
    """Retain row source/scale and share it with marker-based OCR cropping."""
    if getattr(processing_module, "_entry_classification_runtime_installed", False):
        return

    original = processing_module._ordinary_entries_from_layout_roles

    def materialize(understanding, image=None, *, page_index: int = 0):
        entries = original(
            understanding,
            image,
            page_index=page_index,
        )
        lines = [
            line
            for column in list(getattr(understanding.layout, "columns", []) or [])
            for line in list(getattr(column, "lines", []) or [])
            if str(getattr(line, "role", "") or "") == "entry"
        ]
        for line, entry in zip(lines, entries):
            meta = copy_layout_line_classification(line, entry)
            if meta.entry_scale == "oversized":
                entry.ocr_oversized_cjk = True
                entry.ocr_single_cjk = True
                if meta.detected_head_height > 0:
                    entry.ocr_visual_run_height = float(meta.detected_head_height)
                    entry.ocr_line_height_reference = float(
                        getattr(understanding.layout, "ordinary_line_height", 0.0) or 0.0
                    )
        return entries

    processing_module._ordinary_entries_from_layout_roles = materialize
    _install_marker_ocr_crop(processing_module)
    _install_marker_ocr_engine_dispatch(processing_module)
    processing_module._entry_classification_runtime_installed = True


__all__ = ["install_processing_entry_classification"]
