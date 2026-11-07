"""Read-only source-pixel marker geometry and multi-engine OCR text enrichment.

This workflow fills existing ordinary line markers without changing marker count,
source X/Y, class identities or saved sidecar representations. Core callbacks are
provided per call to preserve dynamic profile/crop/processing patches.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, TYPE_CHECKING
from PIL import Image
if TYPE_CHECKING:
    from ..models import AppSettings, Entry
    from ..persistence.page_sections import PageSection


def ocr_existing_entry_words_from_markers_impl(
    image: Image.Image,
    entries: list[Entry],
    settings: AppSettings,
    replace_rules: list[tuple[str, str, str]],
    *,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
    profile_path: Path | None = None,
    only_blank: bool = True,
    deps: dict[str, Any],
) -> tuple[list[Entry], dict[str, int]]:
    """Fill existing markers through the shared multi-engine OCR channel.

    Marker coordinates/count remain immutable. Crop geometry comes from
    canonical Entry classification plus physical row metrics, while one
    OCR channel session is reused for every eligible marker on the page.
    """
    _page_geometry_context = deps["_page_geometry_context"]
    sort_entries_reading_order = deps["sort_entries_reading_order"]
    _ordinary_marker_local_crop = deps["_ordinary_marker_local_crop"]
    process_ocr_text = deps["process_ocr_text"]
    _source, effective, analysis_source, geometry = _page_geometry_context(
        image, settings, profile_page_index,
    )
    canonical = geometry.transform.canonical_image_for_analysis(analysis_source)
    ordered = sort_entries_reading_order(entries, geometry, page_sections)

    from ..profile.dictionary import effective_project_profile_id, load_dictionary_profile
    from .entry_crop import resolve_entry_ocr_row_metrics
    from ..ocr_channel import OcrChannelSession, OcrTextChoice, choose_ocr_text
    from ..paddle_headwords import parse_headword_text
    from ..ordinary.marker_ocr_text import bracketed_ocr_lemma

    row_metrics = resolve_entry_ocr_row_metrics(
        image,
        effective,
        page_index=profile_page_index,
    )
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
        if not bool(entry.manually_selected)
        and not (only_blank and str(entry.word or "").strip())
    ]
    # Preserve the established blank-only stats contract: populated manual
    # entries are also reported as pre-existing words in that legacy mode.
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

    channel = OcrChannelSession(effective)
    # This path fills already-drawn markers, not OCR-line detection. Only
    # CJK bracketed dictionary profiles authorize the optional one-sided
    # 【/】 text cleanup; the user replacement-rule toggle is independent.
    bracket_profile = bool(
        getattr(effective, "profile_cjk_allow_bracketed_headword", False)
        and profile.uses_parser("cjk_bracketed")
    )

    def parsed_or_raw(raw: str) -> str:
        text = str(raw or "").strip()
        if not text:
            return ""
        bracketed = bracketed_ocr_lemma(text, enabled=bracket_profile)
        if bracketed is not None:
            return bracketed
        parsed = parse_headword_text(text, effective, profile=profile)
        if parsed is not None and str(parsed.normalized or "").strip():
            return str(parsed.normalized).strip()
        first_line = next(
            (line.strip() for line in text.splitlines() if line.strip()),
            "",
        )
        return first_line[:64].strip()

    def resolve_candidate(
        candidate,
        *,
        is_large: bool,
        crop_width: int,
    ) -> OcrTextChoice | None:
        if not candidate.ok:
            return None
        word = ""
        confidence = candidate.confidence

        if candidate.engine == "paddle" and candidate.records:
            from ..paddle_headwords import (
                _single_cjk_from_local_records,
                group_ocr_records,
            )

            records = list(candidate.records)
            if is_large:
                word, confidence_value, _source_text = _single_cjk_from_local_records(
                    records,
                    effective,
                    profile,
                    max_left_x=max(
                        16,
                        round(max(1, int(crop_width)) * 0.75),
                    ),
                )
                if word:
                    confidence = float(confidence_value)
            else:
                lines = group_ocr_records(
                    records,
                    float(
                        getattr(
                            effective,
                            "paddle_line_merge_y_ratio",
                            0.55,
                        )
                        or 0.55
                    ),
                )
                for line in sorted(
                    lines,
                    key=lambda value: (
                        int(value.box[0]),
                        int(value.box[1]),
                        -float(value.confidence),
                    ),
                ):
                    word = parsed_or_raw(str(line.text or ""))
                    if word:
                        confidence = float(line.confidence)
                        break

        if not word:
            word = parsed_or_raw(candidate.text)
        if not word:
            return None
        return OcrTextChoice(
            engine=candidate.engine,
            text=str(word).strip(),
            confidence=confidence,
        )

    for entry in targets:
        original_x, original_y = int(entry.x), int(entry.y)
        crop, is_large = _ordinary_marker_local_crop(
            canonical,
            entry,
            geometry,
            effective,
            row_metrics=row_metrics,
            source_image=_source,
        )
        stats["large" if is_large else "regular"] += 1

        psm = (
            5
            if str(
                getattr(effective, "layout_writing_mode", "")
            ).startswith("vertical")
            else 7
        )
        result = channel.recognize_crop(crop, tesseract_psm=psm)
        resolved: list[OcrTextChoice] = []
        for candidate in result.candidates:
            choice = resolve_candidate(
                candidate,
                is_large=is_large,
                crop_width=int(crop.width),
            )
            if choice is not None:
                resolved.append(choice)

        selected, _agreed = choose_ocr_text(result.plan, resolved)
        word = str(selected.text).strip() if selected is not None else ""
        confidence = selected.confidence if selected is not None else None

        if word:
            bracketed = bracketed_ocr_lemma(word, enabled=bracket_profile)
            if bracketed is not None:
                word = bracketed
            if effective.ocr_replace:
                word = process_ocr_text(
                    word,
                    replace_rules,
                    bool(effective.lowercase_ocr),
                )
            entry.word = str(word).strip()
            entry.confidence = confidence
            engine = str(selected.engine)
            entry.ocr_source = f"ordinary_marker:{engine}"
            entry.final_engine = engine
            issue = "ORDINARY_MARKER_TEXT_OCR"
            existing = [
                part
                for part in str(entry.issue_type or "").split(",")
                if part
            ]
            if issue not in existing:
                existing.append(issue)
                entry.issue_type = ",".join(existing)
            stats["filled"] += 1
        else:
            stats["failed"] += 1
            if not only_blank:
                # Explicit OCR replacement must not leave previous OCR text
                # masquerading as the result of this fresh recognition pass.
                # Manual selections never reach this branch.
                entry.word = ""
                entry.confidence = None
                entry.ocr_source = ""
                entry.final_engine = ""

        if int(entry.x) != original_x or int(entry.y) != original_y:
            raise RuntimeError("普通画线后OCR文字不得修改任何画线坐标")

    return ordered, stats
