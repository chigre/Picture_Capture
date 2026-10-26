"""Round 102: a successful PDIC callback must persist the requested markers.

A writer that silently does nothing can leave a pre-existing PDIC on disk.
An existence-only post-commit check then accepts a mismatched OCRed/PDIC pair.
Use the real page worker and serializers to verify text, row count, order,
original image-pixel X/Y and page links after the writer returns.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr.batch_existing_entries import process_existing_pdic_page
from picture_capture.ocr.text_io import export_ocred, render_ocred_bytes
from picture_capture.persistence.page_sections import (
    PageSection, read_page_sections, write_page_sections,
)


PAGES = ("001", "@", "@")
OLD_OCRED = b"\\xef\\xbb\\xbf000|\x60reviewed-before\\r\\n"


def _setup(tmp_path, writer):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (100, 120), "white").save(page)
    image_bytes = page.read_bytes()
    write_page_sections(page, [PageSection(0, 75)])
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("before", 17, 43)], 100, PAGES)
    original_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(OLD_OCRED)

    def recognize(_image, entries, _settings, _rules, **kwargs):
        assert kwargs["page_sections"] == [PageSection(0, 75)]
        assert [(entry.x, entry.y) for entry in entries] == [(17, 43)]
        return ["recognized"]

    deps = {
        "pdic_path": lambda path: path.with_suffix(".PDIC"),
        "read_pdic": read_pdic,
        "Image": Image,
        "normalize_page_rgb": lambda opened: opened.copy().convert("RGB"),
        "effective_page_settings": lambda s, _size, _index: s,
        "page_template_analysis_image": lambda image, _s, _i: image,
        "read_page_sections": read_page_sections,
        "sort_entries_reading_order": lambda entries, _geo, _sections: entries,
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": recognize,
        "qt_root": lambda root: root / "QT",
        "export_ocred": export_ocred,
        "write_pdic": writer,
    }
    return page, pdic, ocred, original_pdic, image_bytes, deps


@pytest.mark.parametrize("fault", [
    "silent_noop", "wrong_word", "wrong_xy", "wrong_page", "malformed",
])
def test_successful_writer_with_wrong_persisted_pdic_is_reported(
    tmp_path, fault,
):
    def faulty_writer(path, entries, width, pages):
        if fault == "silent_noop":
            return None
        if fault == "malformed":
            path.write_text("not-a-valid-record\\n", encoding="utf-8")
            return None
        if fault == "wrong_word":
            entries = [Entry("incorrect", 17, 43)]
        elif fault == "wrong_xy":
            entries = [Entry("recognized", 18, 43)]
        elif fault == "wrong_page":
            pages = ("999", "@", "@")
        return write_pdic(path, entries, width, pages)

    page, pdic, ocred, original_pdic, image_bytes, deps = _setup(
        tmp_path, faulty_writer,
    )
    expected_message = (
        "无法读取保存后的词条" if fault == "malformed"
        else "磁盘词条与本次 OCR 结果不一致"
    )
    with pytest.raises(RuntimeError, match=expected_message):
        process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], PAGES, deps=deps,
        )

    # The PDIC callback has returned; one-sided OCRed rollback is unsafe.
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
    assert page.read_bytes() == image_bytes
    assert read_page_sections(page) == [PageSection(0, 75)]
    if fault == "silent_noop":
        assert pdic.read_bytes() == original_pdic
        assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
            ("before", 17, 43),
        ]
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


def test_real_writer_persists_expected_text_coordinates_and_links(tmp_path):
    page, pdic, ocred, _original, image_bytes, deps = _setup(
        tmp_path, write_pdic,
    )
    assert process_existing_pdic_page(
        page, 0, tmp_path, SimpleNamespace(), [], PAGES, deps=deps,
    ) == 1
    assert [
        (e.word, e.x, e.y, e.current_page, e.previous_page, e.next_page)
        for e in read_pdic(pdic)
    ] == [("recognized", 17, 43, *PAGES)]
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
    assert page.read_bytes() == image_bytes
    assert read_page_sections(page) == [PageSection(0, 75)]
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))
