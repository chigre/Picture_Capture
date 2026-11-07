"""Round 90: SECTION edits cannot silently invalidate batch OCR reading order.

A SECTION edit can change both marker sort order and OCR page lanes while
leaving PDIC untouched. This guards the worker's SECTION source path/bytes
at both sides of OCRed export; it is not a cross-process filesystem lock.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr.batch_existing_entries import process_existing_pdic_page
from picture_capture.ocr.text_io import export_ocred, import_ocred
from picture_capture.persistence.page_sections import (
    PageSection, read_page_sections, write_page_sections,
)
from picture_capture.persistence.project_storage import page_sections_read_path_for_image


def _page(tmp_path):
    page = tmp_path / "001.png"
    Image.new("RGB", (100, 120), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("old", 12, 37)], 100, ("001", "@", "@"))
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"\xef\xbb\xbfmanual-review\r\n")
    return page, pdic, ocred


def _run(page, ocr_fn, *, export=export_ocred, pdic_writes=None):
    writes = [] if pdic_writes is None else pdic_writes

    def save(path, entries, width, pages):
        writes.append("pdic")
        return write_pdic(path, entries, width, pages)

    deps = {
        "pdic_path": lambda p: p.with_suffix(".PDIC"),
        "read_pdic": read_pdic,
        "Image": Image,
        "normalize_page_rgb": lambda opened: opened.copy().convert("RGB"),
        "effective_page_settings": lambda settings, _size, _index: settings,
        "page_template_analysis_image": lambda image, _settings, _index: image,
        "read_page_sections": read_page_sections,
        "sort_entries_reading_order": lambda entries, _geo, _sections: entries,
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": ocr_fn,
        "qt_root": lambda root: root / "QT",
        "export_ocred": export,
        "write_pdic": save,
    }
    return process_existing_pdic_page(
        page, 0, page.parent, SimpleNamespace(), [],
        ("001", "@", "@"), deps=deps,
    )


@pytest.mark.parametrize("change", ["edit", "remove", "create"])
def test_section_changed_during_inference_blocks_both_file_writers(
    tmp_path, change,
):
    page, pdic, ocred = _page(tmp_path)
    if change != "create":
        write_page_sections(page, [PageSection(0, 75)])
    before_pdic, before_ocred = pdic.read_bytes(), ocred.read_bytes()
    section_path = page_sections_read_path_for_image(page)
    writes = []

    def ocr(_image, entries, _settings, _rules, **kwargs):
        assert [(entry.x, entry.y) for entry in entries] == [(12, 37)]
        if change == "remove":
            section_path.unlink()
        else:
            write_page_sections(page, [PageSection(15, 90)])
        return ["new-ocr"]

    def unexpected_export(*_args):
        writes.append("ocred")

    with pytest.raises(RuntimeError, match="SECTION 已被其他操作修改或切换来源"):
        _run(page, ocr, export=unexpected_export, pdic_writes=writes)
    assert writes == []
    assert pdic.read_bytes() == before_pdic
    assert ocred.read_bytes() == before_ocred


@pytest.mark.parametrize("old_ocred", [None, b"\xef\xbb\xbfmanual-review\r\n"])
def test_section_changed_inside_ocred_export_restores_exact_sidecar(
    tmp_path, old_ocred,
):
    page, pdic, ocred = _page(tmp_path)
    write_page_sections(page, [PageSection(0, 75)])
    if old_ocred is None:
        ocred.unlink()
    original_pdic = pdic.read_bytes()
    calls = []

    def export_then_change_section(path, texts):
        calls.append("export")
        export_ocred(path, texts)
        write_page_sections(page, [PageSection(20, 90)])

    with pytest.raises(RuntimeError, match="SECTION 已被其他操作修改或切换来源"):
        _run(
            page,
            lambda *_args, **_kwargs: ["fresh"],
            export=export_then_change_section,
            pdic_writes=calls,
        )
    assert calls == ["export"]
    assert pdic.read_bytes() == original_pdic
    assert (ocred.read_bytes() if ocred.exists() else None) == old_ocred
    assert read_page_sections(page) == [PageSection(20, 90)]
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


def test_section_source_path_switch_is_conflict_even_when_bytes_match(
    tmp_path, monkeypatch,
):
    import picture_capture.ocr.batch_existing_entries as worker

    page, pdic, ocred = _page(tmp_path)
    write_page_sections(page, [PageSection(0, 75)])
    initial = page_sections_read_path_for_image(page)
    alternative = tmp_path / "migrated" / "001.json"
    alternative.parent.mkdir()
    alternative.write_bytes(initial.read_bytes())
    switched = [False]
    monkeypatch.setattr(
        worker, "page_sections_read_path_for_image",
        lambda _page: alternative if switched[0] else initial,
    )
    before_pdic, before_ocred = pdic.read_bytes(), ocred.read_bytes()
    calls = []

    def ocr(*_args, **_kwargs):
        switched[0] = True
        return ["new-ocr"]

    with pytest.raises(RuntimeError, match="SECTION 已被其他操作修改或切换来源"):
        _run(page, ocr, export=lambda *_args: calls.append("export"),
             pdic_writes=calls)
    assert calls == []
    assert pdic.read_bytes() == before_pdic
    assert ocred.read_bytes() == before_ocred


def test_manual_ocred_edit_during_final_section_check_survives_rollback(
    tmp_path, monkeypatch,
):
    page, pdic, ocred = _page(tmp_path)
    write_page_sections(page, [PageSection(0, 75)])
    section_path = page_sections_read_path_for_image(page)
    old_pdic = pdic.read_bytes()
    latest = b"new-human-proofread"
    real_read = Path.read_bytes
    section_reads = [0]
    writes = []

    def interleaved_read(path):
        if path == section_path:
            section_reads[0] += 1
            # Snapshot (1), post-decode (2-3), post-reader (4),
            # pre-export (5-6), then final pre-PDIC (7-8).
            # Round 100 rechecks SECTION after each slow image hash.
            if section_reads[0] == 7:
                ocred.write_bytes(latest)
                write_page_sections(page, [PageSection(10, 85)])
        return real_read(path)

    monkeypatch.setattr(Path, "read_bytes", interleaved_read)
    with pytest.raises(RuntimeError, match="SECTION 发布前核验失败，且 OCRed 回滚失败") as exc:
        _run(page, lambda *_args, **_kwargs: ["fresh"], pdic_writes=writes)
    assert "OCRed 在批量 OCR 发布后被其他操作修改" in str(exc.value)
    assert writes == []
    assert section_reads[0] == 7
    assert ocred.read_bytes() == latest
    assert pdic.read_bytes() == old_pdic



@pytest.mark.parametrize("old_ocred", [None, b"\\xef\\xbb\\xbfmanual-review\\r\\n"])
def test_section_edit_at_final_pre_pdic_check_restores_only_batch_ocred(
    tmp_path, monkeypatch, old_ocred,
):
    """A final SECTION conflict after OCRed export compensates exact bytes."""
    page, pdic, ocred = _page(tmp_path)
    write_page_sections(page, [PageSection(0, 75)])
    if old_ocred is None:
        ocred.unlink()
    else:
        ocred.write_bytes(old_ocred)
    original_pdic = pdic.read_bytes()
    section_path = page_sections_read_path_for_image(page)
    real_read = Path.read_bytes
    section_reads = [0]
    writes = []

    def edit_section_on_final_validation(path):
        if path == section_path:
            section_reads[0] += 1
            if section_reads[0] == 7:
                write_page_sections(page, [PageSection(21, 90)])
        return real_read(path)

    monkeypatch.setattr(Path, "read_bytes", edit_section_on_final_validation)
    with pytest.raises(RuntimeError, match="SECTION 已被其他操作修改或切换来源"):
        _run(page, lambda *_args, **_kwargs: ["fresh"], pdic_writes=writes)
    assert section_reads[0] == 7
    assert writes == []
    assert pdic.read_bytes() == original_pdic
    assert (ocred.read_bytes() if ocred.exists() else None) == old_ocred
    assert read_page_sections(page) == [PageSection(21, 90)]
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


def test_uncontended_section_preserves_ocr_lane_and_original_marker_xy(tmp_path):
    page, pdic, ocred = _page(tmp_path)
    write_page_sections(page, [PageSection(0, 80)])
    seen = []

    def ocr(_image, entries, _settings, _rules, **kwargs):
        seen.append((kwargs["page_sections"], [(e.x, e.y) for e in entries]))
        return ["recognized"]

    assert _run(page, ocr) == 1
    assert seen == [([PageSection(0, 80)], [(12, 37)])]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("recognized", 12, 37)
    ]
    assert import_ocred(ocred) == ["recognized"]


def test_source_and_publisher_guards_are_both_wired():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture/ocr"
    worker = (root / "batch_existing_entries.py").read_text(encoding="utf-8")
    publisher = (root / "batch_publication.py").read_text(encoding="utf-8")
    assert "section_source_path = page_sections_read_path_for_image(page)" in worker
    assert "current_path != section_source_path" in worker
    assert "validate_page_context=verify_page_sources" in worker
    assert "verify_section_source()" in worker
    # Round 94 adds a third provenance check after a successful PDIC
    # commit. Keep both pre-commit checks and verify the new post-commit one.
    assert publisher.count("validate_page_context()") == 3
    export_at = publisher.index("export_ocred(ocred_path, texts)")
    save_at = publisher.index(
        "write_pdic(pdic_path, entries, image_width, pages_info)"
    )
    assert publisher.index("validate_page_context()") < export_at
    assert export_at < publisher.index("validate_page_context()", export_at) < save_at
    assert publisher.rindex("validate_page_context()") > save_at
