"""Round 106: detect late SECTION/source edits during post-save PDIC parsing.

The publisher checks provenance after PDIC commit, but the page worker then
reopens and validates persisted records. A slow parser can outlast a manual
SECTION edit or source-image replacement. Report a conflict, preserving both
already committed sidecars and any external edits.
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
from picture_capture.persistence.project_storage import page_sections_read_path_for_image


PAGES = ("001", "@", "@")


@pytest.mark.parametrize(
    "fault", ["section_edit", "section_remove", "image_replace", "image_remove", "none"],
)
def test_page_source_change_during_persisted_pdic_reopen(tmp_path, fault):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (100, 120), "white").save(page)
    original_image = page.read_bytes()
    write_page_sections(page, [PageSection(0, 75)])
    section_path = page_sections_read_path_for_image(page)
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("before", 17, 43)], 100, PAGES)
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"000|`reviewed-before\\r\\n")
    state = {"reads": 0}

    def reopen_with_late_source_change(path):
        result = read_pdic(path)
        state["reads"] += 1
        if state["reads"] == 2:
            # The first read is the input; the second occurs after both
            # sidecars have been published and the publisher's source check.
            if fault == "section_edit":
                write_page_sections(page, [PageSection(0, 60)])
            elif fault == "section_remove":
                section_path.unlink()
            elif fault == "image_replace":
                Image.new("RGB", (100, 120), "black").save(page)
            elif fault == "image_remove":
                page.unlink()
        return result

    def recognize(_image, entries, _settings, _rules, **kwargs):
        assert kwargs["page_sections"] == [PageSection(0, 75)]
        assert [(entry.x, entry.y) for entry in entries] == [(17, 43)]
        return ["recognized"]

    deps = {
        "pdic_path": lambda path: path.with_suffix(".PDIC"),
        "read_pdic": reopen_with_late_source_change,
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
        "write_pdic": write_pdic,
    }
    def run():
        return process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], PAGES, deps=deps,
        )

    if fault == "none":
        assert run() == 1
    else:
        with pytest.raises(RuntimeError, match="保存后词条复核期间页面来源"):
            run()

    assert state["reads"] == 2
    assert [
        (entry.word, entry.x, entry.y, entry.current_page,
         entry.previous_page, entry.next_page)
        for entry in read_pdic(pdic)
    ] == [("recognized", 17, 43, *PAGES)]
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
    if fault == "section_edit":
        assert read_page_sections(page) == [PageSection(0, 60)]
    elif fault == "section_remove":
        assert not section_path.exists()
    else:
        assert read_page_sections(page) == [PageSection(0, 75)]
    if fault == "image_replace":
        assert page.read_bytes() != original_image
    elif fault == "image_remove":
        assert not page.exists()
    else:
        assert page.read_bytes() == original_image
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))
