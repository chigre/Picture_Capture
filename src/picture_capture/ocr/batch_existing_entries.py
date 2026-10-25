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

from .batch_publication import publish_existing_pdic_ocr


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
    pdic_file = deps["pdic_path"](page)
    # Snapshot disk bytes before inference. External/manual proofreading may
    # replace PDIC while OCR runs; never overwrite that newer edit with the
    # markers loaded at worker start. The batch UI also locks worker-owned
    # pages, but this protects edits made outside that Tk ownership protocol.
    try:
        source_pdic_bytes = pdic_file.read_bytes()
    except FileNotFoundError:
        source_pdic_bytes = None
    entries = deps["read_pdic"](pdic_file)
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
    try:
        current_pdic_bytes = pdic_file.read_bytes()
    except FileNotFoundError:
        current_pdic_bytes = None
    if current_pdic_bytes != source_pdic_bytes:
        raise RuntimeError(
            "批量 OCR 处理期间 PDIC 已被其他操作修改；"
            "已跳过当前页保存，避免覆盖人工校对内容"
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
    publish_existing_pdic_ocr(
        deps["qt_root"](project_root) / f"{page.stem}.OCRed",
        pdic_file,
        texts, entries, image.width, pages_info,
        export_ocred=deps["export_ocred"],
        write_pdic=deps["write_pdic"],
        expected_pdic_bytes=source_pdic_bytes,
    )
    return len(texts)
