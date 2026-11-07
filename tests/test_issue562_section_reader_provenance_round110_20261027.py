"""Reject stale SECTION/source data immediately after a patchable SECTION reader."""
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
from picture_capture.persistence.project_storage import page_sections_read_path_for_image


@pytest.mark.parametrize("fault", ["section_edit", "section_remove", "none"])
def test_section_reader_source_change_rejected_before_ocr(tmp_path, fault):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (100, 120), "white").save(page)
    write_page_sections(page, [PageSection(0, 75)])
    section_path = page_sections_read_path_for_image(page)
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("before", 17, 43)], 100, ("001", "@", "@"))
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"reviewed before")
    original_pdic = pdic.read_bytes()
    ocr_calls = []

    def read_with_fault(path):
        sections = read_page_sections(path)
        if fault == "section_edit":
            write_page_sections(page, [PageSection(0, 60)])
        elif fault == "section_remove":
            section_path.unlink()
        return sections

    def recognize(*args, **kwargs):
        ocr_calls.append(True)
        return ["recognized"]

    deps = {
        "pdic_path": lambda p: p.with_suffix(".PDIC"),
        "read_pdic": read_pdic,
        "Image": Image,
        "normalize_page_rgb": lambda opened: opened.copy().convert("RGB"),
        "effective_page_settings": lambda s, _size, _index: s,
        "page_template_analysis_image": lambda image, _s, _i: image,
        "read_page_sections": read_with_fault,
        "sort_entries_reading_order": lambda entries, _geo, _sections: entries,
        "derive_geometry": lambda *_: object(),
        "ocr_entries": recognize,
        "qt_root": lambda root: root / "QT",
        "export_ocred": export_ocred,
        "write_pdic": write_pdic,
    }
    def run():
        return process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"), deps=deps,
        )

    if fault == "none":
        assert run() == 1
        assert ocr_calls == [True]
        assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
    else:
        with pytest.raises(RuntimeError, match="批量 OCR 处理期间"):
            run()
        assert ocr_calls == []
        assert pdic.read_bytes() == original_pdic
        assert ocred.read_bytes() == b"reviewed before"
    if fault == "section_edit":
        assert read_page_sections(page) == [PageSection(0, 60)]
    elif fault == "section_remove":
        assert not section_path.exists()
    else:
        assert read_page_sections(page) == [PageSection(0, 75)]
