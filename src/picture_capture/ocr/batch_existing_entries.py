from __future__ import annotations

"""Single-page batch OCR over existing PDIC markers.

This leaf owns the page's decode, source-coordinate-preserving OCR text fill,
OCRed export and PDIC publication. The Tk controller still owns prompts, page
selection, foreground edit permissions, workers and completion UI.

The explicit live dependency map preserves the historical controller's
monkeypatch behavior (including on Windows spawn workers).
"""

from pathlib import Path
from typing import Any, Mapping


def process_existing_pdic_page(
    page: Path,
    index: int,
    project_root: Path,
    settings: Any,
    rules: Any,
    pages_info: tuple[str, str, str],
    *,
    deps: Mapping[str, Any],
) -> int:
    """Run one existing-PDIC OCR job with the original publication order."""
    entries = deps["read_pdic"](deps["pdic_path"](page))
    with deps["Image"].open(page) as opened:
        image = deps["normalize_page_rgb"](opened)
    effective_settings = deps["effective_page_settings"](
        settings, image.size, index,
    )
    analysis_image = deps["page_template_analysis_image"](
        image, effective_settings, index,
    )
    sections = deps["read_page_sections"](page)
    entries = deps["sort_entries_reading_order"](
        entries,
        deps["derive_geometry"](analysis_image, effective_settings),
        sections,
    )
    texts = deps["ocr_entries"](
        image,
        entries,
        settings,
        rules,
        profile_page_index=index,
        page_sections=sections,
    )
    # A one-to-one OCR text result is required to preserve every original
    # PDIC marker. zip() alone silently leaves trailing entries unchanged or
    # drops surplus results, producing mismatched PDIC/OCRed output.
    if len(texts) != len(entries):
        raise ValueError(
            f"批量 OCR 返回词条数不一致：PDIC {len(entries)} 条，OCR {len(texts)} 条"
        )
    for entry, text in zip(entries, texts):
        entry.word = text
    deps["export_ocred"](
        deps["qt_root"](project_root) / f"{page.stem}.OCRed",
        texts,
    )
    deps["write_pdic"](
        deps["pdic_path"](page),
        entries,
        image.width,
        pages_info,
    )
    return len(texts)
