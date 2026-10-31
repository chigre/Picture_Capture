"""OCR and combined-mode observations in a shared Page Understanding geometry.

The processing facade supplies its current public/core hooks on every call.
Paddle OCR remains a lazy import, preserving worker spawn and runtime patching.
No persistence, cache or model identities are owned by this module.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image
from ..models import AppSettings, Entry
from ..layout.page_understanding import PageUnderstanding
from ..persistence.page_sections import PageSection


def shared_detector_observations(
    image: Image.Image,
    understanding: PageUnderstanding,
    method: str,
    *,
    paddle_cache_path: Path | None,
    force_paddle_refresh: bool,
    paddle_filter_rules_path: Path | None,
    profile_page_index: int,
    page_sections: list[PageSection] | None,
    normalize_page_rgb: Any,
    effective_page_settings: Any,
    page_template_image: Any,
    geometry_from_page_understanding: Any,
    review_candidates_from_cache: Any,
    ordinary_settings_for_shared_geometry: Any,
    detect_entries_left_edge: Any,
    fuse_detection_entries: Any,
) -> tuple[list[Entry], Any, list[dict]]:
    """Generate OCR/combined observations in the shared page coordinate model."""
    source = normalize_page_rgb(image)
    effective = effective_page_settings(
        understanding.page_settings,
        source.size,
        profile_page_index,
    )
    analysis_source = page_template_image(
        source, effective, profile_page_index,
    )
    geometry = geometry_from_page_understanding(understanding)

    if method in {"paddleocr", "combined"}:
        from ..paddle_headwords import detect_paddle_headwords

        ocr_entries = detect_paddle_headwords(
            analysis_source,
            geometry,
            effective,
            cache_path=paddle_cache_path,
            force_refresh=force_paddle_refresh,
            filter_rules_path=paddle_filter_rules_path,
            page_sections=page_sections,
        )
        review_candidates = review_candidates_from_cache(paddle_cache_path)
        if method == "paddleocr":
            return list(ocr_entries), geometry, review_candidates

        ordinary_settings = ordinary_settings_for_shared_geometry(
            effective,
            geometry,
            method="combined",
        )
        ordinary_entries, _ordinary_geometry = detect_entries_left_edge(
            analysis_source,
            ordinary_settings,
            page_sections=page_sections,
        )
        entries = fuse_detection_entries(
            ordinary_entries,
            ocr_entries,
            geometry,
            effective,
            page_sections,
            review_candidates=review_candidates,
            image=analysis_source,
        )
        return list(entries), geometry, review_candidates

    return [], geometry, []
