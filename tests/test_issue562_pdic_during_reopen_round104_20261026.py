"""Round 104: concurrent PDIC replacement during post-save record parsing.

A persisted-record parser may return the expected markers while another
process replaces/deletes PDIC during that slow parse. The page must report
an explicit conflict and must never roll back OCRed alone after PDIC commit.
"""
from __future__ import annotations

from pathlib import Path
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
OLD_OCRED = b"000|`reviewed-before\r\n"


def _page_fixture(tmp_path):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (100, 120), "white").save(page)
    original_image = page.read_bytes()
    write_page_sections(page, [PageSection(0, 75)])
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("before", 17, 43)], 100, PAGES)
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
        "write_pdic": write_pdic,
    }
    return page, pdic, ocred, original_image, deps


@pytest.mark.parametrize("fault", ["edit", "remove", "read_denied", "none"])
def test_pdic_version_during_persisted_reopen(tmp_path, monkeypatch, fault):
    page, pdic, ocred, original_image, deps = _page_fixture(tmp_path)
    original_read_bytes = Path.read_bytes
    state = {"calls": 0, "deny": False}

    def read_with_late_edit(path):
        result = read_pdic(path)
        state["calls"] += 1
        if state["calls"] == 2:
            # First read loads input markers; second read is the slow
            # post-commit parser. Mutate the PDIC after records were read
            # but before the worker's post-parse byte-identity guard.
            if fault == "edit":
                write_pdic(pdic, [Entry("manual-late", 17, 43)], 100, PAGES)
            elif fault == "remove":
                pdic.unlink()
            elif fault == "read_denied":
                state["deny"] = True
        return result

    def guarded_read_bytes(path):
        if state["deny"] and path == pdic:
            raise PermissionError("injected late PDIC read denial")
        return original_read_bytes(path)

    deps["read_pdic"] = read_with_late_edit
    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    try:
        if fault == "none":
            result = process_existing_pdic_page(
                page, 0, tmp_path, SimpleNamespace(), [], PAGES, deps=deps,
            )
            assert result == 1
        else:
            message = (
                "无法再次核验 PDIC" if fault in ("read_denied", "remove")
                else "PDIC 被其他操作修改"
            )
            with pytest.raises(RuntimeError, match=message):
                process_existing_pdic_page(
                    page, 0, tmp_path, SimpleNamespace(), [], PAGES, deps=deps,
                )
    finally:
        state["deny"] = False

    assert state["calls"] == 2
    if fault == "remove":
        assert not pdic.exists()
    else:
        expected_word = "manual-late" if fault == "edit" else "recognized"
        assert [
            (e.word, e.x, e.y, e.current_page, e.previous_page, e.next_page)
            for e in read_pdic(pdic)
        ] == [(expected_word, 17, 43, *PAGES)]
    # OCRed was committed before the late PDIC edit. Never revert it alone.
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
    assert page.read_bytes() == original_image
    assert read_page_sections(page) == [PageSection(0, 75)]
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))
