from __future__ import annotations

"""Single-page batch OCR over existing PDIC markers.

This leaf owns the page's decode, source-coordinate-preserving OCR text fill,
OCRed export and PDIC publication. The Tk controller still owns prompts, page
selection, foreground edit permissions, workers and completion UI.

The explicit live dependency map preserves the historical controller's
monkeypatch behavior (including on Windows spawn workers).
"""

import hashlib
from pathlib import Path
from typing import Any, Mapping

from .batch_publication import publish_existing_pdic_ocr
from .text_io import render_ocred_bytes
from ..persistence.project_storage import page_sections_read_path_for_image


def _source_image_sha256(path: Path) -> bytes:
    """Hash original on-disk image bytes without loading the scan into RAM.

    OCR works on decoded pixels, but a replaced source image can invalidate
    both recognized text and source-pixel marker coordinates. Use streaming
    bytes instead of file size/mtime (which miss same-size rewrites).
    """
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


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
    # OCRed/PDIC/SECTION alone do not identify the scan whose pixels were
    # decoded. Preserve its content identity before opening the image.
    source_image_hash = _source_image_sha256(page)
    # Snapshot disk bytes before inference. External/manual proofreading may
    # replace PDIC while OCR runs; never overwrite that newer edit with the
    # markers loaded at worker start. The batch UI also locks worker-owned
    # pages, but this protects edits made outside that Tk ownership protocol.
    try:
        source_pdic_bytes = pdic_file.read_bytes()
    except FileNotFoundError:
        source_pdic_bytes = None
    # OCRed can also be manually proofread while the inference worker runs.
    # Snapshot before inference and pass the original bytes to publication.
    ocred_file = deps["qt_root"](project_root) / f"{page.stem}.OCRed"
    try:
        source_ocred_bytes = ocred_file.read_bytes()
    except FileNotFoundError:
        source_ocred_bytes = None
    # SECTION determines marker reading order and OCR page lanes. Its canonical
    # location can change when a managed-v2 project supersedes a migrated QT
    # copy. Capture both the resolved source path and its exact bytes.
    section_source_path = page_sections_read_path_for_image(page)
    try:
        section_source_bytes = section_source_path.read_bytes()
    except FileNotFoundError:
        section_source_bytes = None

    def verify_section_source() -> None:
        current_path = page_sections_read_path_for_image(page)
        try:
            current_bytes = current_path.read_bytes()
        except FileNotFoundError:
            current_bytes = None
        if current_path != section_source_path or current_bytes != section_source_bytes:
            raise RuntimeError(
                "批量 OCR 处理期间 SECTION 已被其他操作修改或切换来源；"
                "已跳过当前页保存，避免使用过期的分区阅读顺序"
            )

    def verify_page_sources() -> None:
        verify_section_source()
        try:
            current_image_hash = _source_image_sha256(page)
        except FileNotFoundError as error:
            raise RuntimeError(
                "批量 OCR 处理期间原始图像已被移除；"
                "已跳过当前页保存，避免写入过期 OCR 与像素坐标"
            ) from error
        if current_image_hash != source_image_hash:
            raise RuntimeError(
                "批量 OCR 处理期间原始图像已被其他操作修改；"
                "已跳过当前页保存，避免写入过期 OCR 与像素坐标"
            )

    entries = deps["read_pdic"](pdic_file)
    with deps["Image"].open(page) as opened:
        image = deps["normalize_page_rgb"](opened)
    # A scan replaced between the initial fingerprint and decoding is
    # already stale, even if no subsequent edit occurs during inference.
    verify_page_sources()
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
        ocred_file,
        pdic_file,
        texts, entries, image.width, pages_info,
        export_ocred=deps["export_ocred"],
        write_pdic=deps["write_pdic"],
        expected_pdic_bytes=source_pdic_bytes,
        expected_ocred_bytes=source_ocred_bytes,
        expected_exported_ocred_bytes=render_ocred_bytes(texts),
        validate_page_context=verify_page_sources,
    )
    return len(texts)
