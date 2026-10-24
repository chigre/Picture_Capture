"""Legacy text-only OCR reading of sorted marker entry crops with shared bracket policy.

Core implementation is delegated here, with live historical collaborators
injected at invocation and with persisted classes remaining in their owners.
"""
from __future__ import annotations
from PIL import Image
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import Entry, AppSettings
    from ..persistence.page_sections import PageSection


def ocr_entries_impl(
    image: Image.Image,
    entries: list[Entry],
    settings: AppSettings,
    replace_rules: list[tuple[str, str, str]],
    *,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
    deps: dict[str, Any],
) -> list[str]:
    _page_geometry_context = deps["_page_geometry_context"]
    sort_entries_reading_order = deps["sort_entries_reading_order"]
    line_box = deps["line_box"]
    run_tesseract = deps["run_tesseract"]
    resolved_tesseract_language = deps["resolved_tesseract_language"]
    process_ocr_text = deps["process_ocr_text"]
    source, effective, _analysis_source, geometry = _page_geometry_context(
        image, settings, profile_page_index,
    )
    results: list[str] = []
    # The legacy text-only OCR consumer must use the same bracketed-lemma
    # boundary as ordinary drawn-marker OCR. A concrete CJK Profile and the
    # user's bracket-structure toggle are both required.
    from ..profile.dictionary import effective_project_profile_id, load_dictionary_profile
    from ..ordinary.marker_ocr_text import bracketed_ocr_lemma
    profile = load_dictionary_profile(
        None,
        preset=effective_project_profile_id(effective, None),
        language=effective.ocr_language,
    )
    bracket_profile = bool(
        getattr(effective, "profile_cjk_allow_bracketed_headword", False)
        and profile.uses_parser("cjk_bracketed")
    )
    paddle_engine = None
    if effective.ocr_engine == "paddleocr":
        from ..paddle_headwords import get_paddle_engine
        paddle_engine = get_paddle_engine(effective)
    for entry in sort_entries_reading_order(entries, geometry, page_sections):
        crop = source.crop(line_box(entry, geometry, source, effective))
        if effective.ocr_engine == "paddleocr":
            from ..paddle_headwords import recognize_paddle_text
            raw = recognize_paddle_text(crop, effective, engine=paddle_engine)
        else:
            psm = 5 if str(getattr(effective, "layout_writing_mode", "")).startswith("vertical") else 7
            raw = run_tesseract(
                crop, resolved_tesseract_language(effective), effective.ocr_executable, psm=psm
            )
        text = process_ocr_text(
            raw, replace_rules, effective.lowercase_ocr,
        ) if effective.ocr_replace else str(raw or "").strip()
        # Clean after replacement as well: user rules may preserve or rewrite
        # delimiters. Otherwise use the same untouched result as before.
        lemma = bracketed_ocr_lemma(text, enabled=bracket_profile)
        results.append(lemma if lemma is not None else text)
    return results
