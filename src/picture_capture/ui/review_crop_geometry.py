"""Review crop settings, source-pixel boxes and per-page Profile geometry.

Physical algorithm owner; original app module supplies live monkeypatch hooks.
No Tk or OCR engine is initialized here.
"""
from __future__ import annotations
from typing import Any

def _review_crop_settings(image: Image.Image, settings: AppSettings, viewer_width: int, *, deps: dict[str, Any]) -> AppSettings:
    replace = deps["replace"]
    """Return review settings unchanged; geometry is already source pixels."""
    return replace(settings)

def _review_crop_context(
    image: Image.Image,
    settings: AppSettings,
    viewer_width: int,
    page_index: int = 0,
 *, deps: dict[str, Any]):
    effective_page_settings = deps["effective_page_settings"]
    page_template_analysis_image = deps["page_template_analysis_image"]
    _review_crop_settings = deps["_review_crop_settings"]
    derive_geometry = deps["derive_geometry"]
    """Return review crop settings plus the same per-page Profile geometry as detection."""
    effective = effective_page_settings(settings, image.size, page_index)
    analysis_image = page_template_analysis_image(image, effective, page_index)
    return (
        _review_crop_settings(image, effective, viewer_width),
        derive_geometry(analysis_image, effective),
    )

def _is_cjk_review_index(settings: AppSettings, *, deps: dict[str, Any]) -> bool:
    """Return whether the active index/profile is Chinese-oriented."""
    language = str(getattr(settings, "ocr_language", "") or "").strip().lower()
    profile = str(getattr(settings, "dictionary_profile_id", "") or "").strip().lower()
    return language.startswith("chi_") or profile.startswith("cjk_")

def _effective_review_single_cjk_line_height(settings: AppSettings, *, deps: dict[str, Any]) -> int:
    _is_cjk_review_index = deps["_is_cjk_review_index"]
    """Resolve the review-only height for one-character CJK headwords.

    An explicit project value wins. New/older projects with value 0 use a
    language-aware default: Chinese index/profile = 2.5× the shared single-line
    height; other profiles retain a smaller legacy-like expansion.
    """
    try:
        explicit = int(getattr(settings, "review_single_cjk_line_height", 0) or 0)
    except (TypeError, ValueError):
        explicit = 0
    if explicit > 0:
        return max(1, explicit)
    base = max(1, int(getattr(settings, "character_height", 1) or 1))
    multiplier = 2.5 if _is_cjk_review_index(settings) else 1.6
    return max(base, round(base * multiplier))

def _effective_review_regular_crop_height(settings: AppSettings, *, deps: dict[str, Any]) -> int:
    """Resolve ordinary proofreading crop height in parameter pixels."""
    try:
        explicit = int(getattr(settings, "review_regular_crop_height", 0) or 0)
    except (TypeError, ValueError):
        explicit = 0
    if explicit > 0:
        return max(1, explicit)
    line_height = max(1, int(getattr(settings, "character_height", 1) or 1))
    row_padding = max(0, int(getattr(settings, "row_padding", 0) or 0))
    return max(1, line_height + row_padding)

def _review_line_box(
    entry: WordEntry,
    geometry,
    image: Image.Image,
    settings: AppSettings,
    next_entry: WordEntry | None = None,
    *,
    ordinary_height_only: bool = False,
    editor_text: str | None = None,
 deps: dict[str, Any]) -> tuple[int, int, int, int]:
    replace = deps["replace"]
    line_box = deps["line_box"]
    _effective_review_regular_crop_height = deps["_effective_review_regular_crop_height"]
    _effective_review_single_cjk_line_height = deps["_effective_review_single_cjk_line_height"]
    _focused_review_is_single_character = deps["_focused_review_is_single_character"]
    """Review crop height is based only on the actual edited headword text.

    A single character uses the explicitly configured large-head crop height;
    multiple characters use the ordinary height. Deprecated classification,
    OCR visual-run height and manual scale flags do not influence review crops.
    """
    configured_regular = max(
        0, int(getattr(settings, "entry_regular_crop_height", 0) or 0)
    )
    configured_oversized = max(
        0, int(getattr(settings, "entry_oversized_crop_height", 0) or 0)
    )
    regular_height = (
        configured_regular or _effective_review_regular_crop_height(settings)
    )
    oversized_height = (
        configured_oversized or _effective_review_single_cjk_line_height(settings)
    )
    displayed_text = entry.word if editor_text is None else editor_text
    height = (
        regular_height if ordinary_height_only
        else oversized_height if _focused_review_is_single_character(displayed_text)
        else regular_height
    )
    if geometry.transform.kind != "identity":
        classified_settings = replace(settings)
        classified_settings.character_height = int(height)
        return line_box(entry, geometry, image, classified_settings)

    left, _old_top, right, _bottom = line_box(
        entry, geometry, image, settings
    )
    row_padding = max(0, int(getattr(settings, "row_padding", 0) or 0))
    half_spacing = round(0.5 * row_padding)
    top = max(int(geometry.top), int(entry.y) - half_spacing)
    return left, top, right, min(
        int(image.height),
        top + max(1, int(height)),
    )
