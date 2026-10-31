from __future__ import annotations

"""Single-page batch OCR over existing PDIC markers.

This leaf owns the page's decode, source-coordinate-preserving OCR text fill,
OCRed export and PDIC publication. The Tk controller still owns prompts, page
selection, foreground edit permissions, workers and completion UI.

The explicit live dependency map preserves the historical controller's
monkeypatch behavior (including on Windows spawn workers).
"""

import hashlib
from collections import Counter
from copy import copy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from .batch_publication import publish_existing_pdic_ocr
from .text_io import render_ocred_bytes
from ..persistence.project_storage import page_sections_read_path_for_image
from ..text.encoding import decode_text_bytes


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



def _verify_pdic_serialized_rows(
    snapshot: bytes,
    entries: list[Any],
    image_width: int,
    pages_info: tuple[str, str, str],
) -> None:
    """Verify all eight persisted PDIC fields, including PicDic percentages.

    read_pdic intentionally ignores the percentage columns and tolerates
    extra fields. That is appropriate for imported legacy files, but a batch
    writer must not report success when it persisted stale/invalid index
    coordinates. Decode the already captured post-save bytes so this check
    cannot accidentally inspect a different file version.
    """
    actual = [
        line.split("#")
        for line in decode_text_bytes(snapshot)[0].splitlines()
        if line.strip()
    ]
    expected: list[list[str]] = []
    for entry in entries:
        x_percent = round(entry.x / image_width * 100, 2) if image_width else 0
        y_percent = round(entry.y / image_width * 100, 2) if image_width else 0
        word = entry.word.replace("\r", " ").replace("\n", " ").replace("#", "＃").strip()
        expected.append([
            word, str(entry.x), str(entry.y),
            f"{x_percent:g}", f"{y_percent:g}", *pages_info,
        ])
    if actual != expected:
        raise RuntimeError(
            "PDIC 序列化字段与本次 OCR 结果不一致"
            "（含 PicDic X/Y 比例、原图像素坐标及页面关联）；"
            "未单独回滚 OCRed，请人工核查两份文件"
        )


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

        # Hashing a large source scan can take significant time. SECTION
        # may be replaced *during* that hash, after the first SECTION read.
        # Recheck the resolved SECTION path and exact bytes once the image
        # digest completes so neither the pre-commit nor post-commit check
        # silently accepts stale reading lanes.
        verify_section_source()

    entries = deps["read_pdic"](pdic_file)
    # Reading-order sorting may reorder markers, but must not add, remove
    # or move any original PDIC pixel coordinate. Capture a multiset so
    # duplicate locations remain accounted for without relying on order.
    source_marker_coordinates = Counter((entry.x, entry.y) for entry in entries)
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
    # A custom SECTION reader may rewrite its own source while returning
    # stale lanes. Recheck canonical SECTION bytes before sorting/inference;
    # retain the established image-hash checkpoints and their timing.
    verify_section_source()
    entries = deps["sort_entries_reading_order"](
        entries,
        deps["derive_geometry"](analysis_image, effective_settings),
        sections,
    )
    if Counter((entry.x, entry.y) for entry in entries) != source_marker_coordinates:
        raise RuntimeError(
            "批量 OCR 排序期间词条数量或原图像素坐标被修改；"
            "已跳过当前页保存，避免覆盖原有 PDIC 标记"
        )
    # OCR callbacks receive mutable Entry objects to support the legacy
    # reading pipeline, but recognition is only authorized to supply text.
    # Freeze the sorted coordinate sequence, and reject any later move or
    # reorder before writing either OCRed or PDIC.
    sorted_marker_coordinates = [(entry.x, entry.y) for entry in entries]
    texts = deps["ocr_entries"](
        image,
        entries,
        settings,
        rules,
        profile_page_index=index,
        page_sections=sections,
    )
    if [(entry.x, entry.y) for entry in entries] != sorted_marker_coordinates:
        raise RuntimeError(
            "批量 OCR 识别期间词条原图像素坐标或顺序被修改；"
            "已跳过当前页保存，避免覆盖原有 PDIC 标记"
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
    # Capture the intended marker fields before invoking patchable exporters
    # and writers. A callback may mutate Entry objects in place: validating
    # against those changed objects would bless an unintended PDIC version
    # (or falsely reject a correct file after a post-write mutation).
    intended_entries = [
        SimpleNamespace(word=entry.word, x=entry.x, y=entry.y)
        for entry in entries
    ]
    # The exporter receives a mutable OCR text list. Freeze the intended
    # serialized bytes and count before calling patchable callbacks: a
    # callback can mutate texts *after* correctly exporting the sidecar.
    # Later checks must compare against the original OCR result, not that
    # mutated list (which would falsely report corruption or return zero).
    intended_ocred_bytes = render_ocred_bytes(texts)
    intended_entry_count = len(intended_entries)
    # Keep callback-owned mutable arguments separate from the validated
    # intended records. Exporters may rewrite their text list or mutate
    # Entry objects; the PDIC writer must receive the original OCR result.
    publication_texts = list(texts)
    publication_entries = [copy(entry) for entry in entries]
    publish_existing_pdic_ocr(
        ocred_file,
        pdic_file,
        publication_texts, publication_entries, image.width, pages_info,
        export_ocred=deps["export_ocred"],
        write_pdic=deps["write_pdic"],
        expected_pdic_bytes=source_pdic_bytes,
        expected_ocred_bytes=source_ocred_bytes,
        expected_exported_ocred_bytes=intended_ocred_bytes,
        validate_page_context=verify_page_sources,
    )

    # A PDIC writer can return normally without persisting the requested
    # markers (for example, a swallowed I/O error or a no-op writer spy).
    # Checking only that PDIC exists is insufficient when an older PDIC is
    # already present: OCRed would be new while marker text stayed stale.
    # Verify the saved records, original source-pixel coordinates, order and
    # page links before reporting this page as completed. PDIC has already
    # been committed at this point; never compensate OCRed alone on failure.
    # A large PDIC parse can outlast an external proofreader's atomic
    # replacement. Capture the committed bytes around the parse: a parser
    # may return the original records even though the on-disk file changed
    # before this worker reports success.
    try:
        pdic_before_reopen = pdic_file.read_bytes()
    except OSError as error:
        raise RuntimeError(
            "PDIC 已保存，但重新读取词条前无法核验磁盘版本；"
            "未单独回滚 OCRed，请人工核查两份文件"
        ) from error
    try:
        persisted = deps["read_pdic"](pdic_file)
    except Exception as error:
        raise RuntimeError(
            "PDIC 保存函数已返回，但无法读取保存后的词条；"
            "未单独回滚 OCRed，请人工核查两份文件"
        ) from error

    def record(entry: Any) -> tuple[Any, ...]:
        # Match write_pdic's historical text sanitization exactly. Do not
        # normalize X/Y: they must remain the original image-pixel values.
        word = entry.word.replace("\r", " ").replace("\n", " ").replace("#", "＃").strip()
        return (word, entry.x, entry.y, *pages_info)

    expected_records = [record(entry) for entry in intended_entries]
    actual_records = [
        (entry.word, entry.x, entry.y,
         entry.current_page, entry.previous_page, entry.next_page)
        for entry in persisted
    ]
    if actual_records != expected_records:
        raise RuntimeError(
            "PDIC 保存函数已返回，但磁盘词条与本次 OCR 结果不一致"
            "（文字、数量、顺序、原图像素坐标或页面关联）；"
            "未单独回滚 OCRed，请人工核查两份文件"
        )
    # The parser's returned records alone are not a stable file snapshot:
    # a concurrent writer can replace or remove PDIC while parsing. Compare
    # full bytes on both sides of that potentially slow operation. PDIC has
    # already been committed, so a conflict must not roll back OCRed alone.
    try:
        pdic_after_reopen = pdic_file.read_bytes()
    except OSError as error:
        raise RuntimeError(
            "PDIC 保存后重新读取词条期间无法再次核验 PDIC；"
            "未单独回滚 OCRed，请人工核查两份文件"
        ) from error
    if pdic_after_reopen != pdic_before_reopen:
        raise RuntimeError(
            "PDIC 保存后重新读取词条期间 PDIC 被其他操作修改；"
            "保留磁盘上的最新 PDIC 和 OCRed，未执行单侧回滚；"
            "请人工核查两份文件"
        )
    # read_pdic ignores percentage columns (used by downstream PicDic) and
    # accepts extra fields. Check the same captured PDIC version's full rows
    # against write_pdic's canonical eight-field serialization as well.
    _verify_pdic_serialized_rows(
        pdic_after_reopen, intended_entries, image.width, pages_info,
    )

    # Reopening/parsing a large PDIC can take time. An external proofreader
    # may change or remove OCRed after the publication helper's final guard
    # but before the page worker reports success. Verify the canonical
    # exported bytes once more after the persisted-record read. The PDIC
    # has already been committed, so do not roll back either side alone.
    try:
        final_ocred_bytes = ocred_file.read_bytes()
    except FileNotFoundError:
        final_ocred_bytes = None
    except OSError as error:
        raise RuntimeError(
            "PDIC 保存后核验词条期间无法再次读取 OCRed；"
            "未单独回滚，请人工核查 OCRed 与 PDIC"
        ) from error
    if final_ocred_bytes != intended_ocred_bytes:
        raise RuntimeError(
            "PDIC 保存后核验词条期间 OCRed 被修改或移除；"
            "保留磁盘上的最新 OCRed 与 PDIC，未执行单侧回滚；"
            "请人工核查两份文件"
        )

    # Parsing/validating a large persisted PDIC can outlast an external
    # SECTION edit or source-image replacement. The publisher checked page
    # provenance immediately after writing PDIC, but that check predates
    # this post-save parse. Do not report success using now-stale lanes or
    # source-pixel coordinates. Both sidecars are already committed, so
    # never roll back either one independently on a late source conflict.
    try:
        verify_page_sources()
    except Exception as source_error:
        raise RuntimeError(
            "PDIC 已保存，但保存后词条复核期间页面来源（SECTION/原始图像）"
            "已变化或无法核验；未执行单侧回滚，"
            "请人工核查 PDIC、OCRed 和页面来源"
        ) from source_error
    # The final provenance hash can be slow. Recheck both committed sidecars
    # after it returns so a concurrent proofreader cannot change either file
    # during that hash and still receive a successful batch completion.
    try:
        last_pdic_bytes = pdic_file.read_bytes()
    except OSError as error:
        raise RuntimeError(
            "页面来源最终核验后无法再次读取 PDIC；"
            "未执行单侧回滚，请人工核查两份文件"
        ) from error
    if last_pdic_bytes != pdic_after_reopen:
        raise RuntimeError(
            "页面来源最终核验期间 PDIC 被其他操作修改；"
            "保留磁盘上的最新 PDIC 和 OCRed，未执行单侧回滚"
        )
    try:
        last_ocred_bytes = ocred_file.read_bytes()
    except OSError as error:
        raise RuntimeError(
            "页面来源最终核验后无法再次读取 OCRed；"
            "未执行单侧回滚，请人工核查两份文件"
        ) from error
    if last_ocred_bytes != intended_ocred_bytes:
        raise RuntimeError(
            "页面来源最终核验期间 OCRed 被其他操作修改；"
            "保留磁盘上的最新 OCRed 和 PDIC，未执行单侧回滚"
        )
    return intended_entry_count
