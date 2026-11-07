"""Round 103: a post-save PDIC parse must not mask a late OCRed edit.

Publication guards run before the worker reopens persisted PDIC records.
A concurrent proofreader can edit/delete OCRed while that parse is running.
The page must report a conflict, preserving both on-disk artifacts.
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
MANUAL_OCRED = b"\xef\xbb\xbf000|`manual-late-edit\r\n"


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
def test_ocred_version_after_pdic_reopen(tmp_path, monkeypatch, fault):
    page, pdic, ocred, original_image, deps = _page_fixture(tmp_path)
    original_read_bytes = Path.read_bytes
    state = {"calls": 0, "deny": False}

    def read_with_late_edit(path):
        result = read_pdic(path)
        state["calls"] += 1
        if state["calls"] == 2:
            # First read loads the input markers; second read is the slow
            # post-commit persistence verification. Inject at its end.
            if fault == "edit":
                ocred.write_bytes(MANUAL_OCRED)
            elif fault == "remove":
                ocred.unlink()
            elif fault == "read_denied":
                state["deny"] = True
        return result

    def guarded_read_bytes(path):
        if state["deny"] and path == ocred:
            raise PermissionError("injected late OCRed read denial")
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
                "无法再次读取 OCRed" if fault == "read_denied"
                else "OCRed 被修改或移除"
            )
            with pytest.raises(RuntimeError, match=message):
                process_existing_pdic_page(
                    page, 0, tmp_path, SimpleNamespace(), [], PAGES, deps=deps,
                )
    finally:
        state["deny"] = False

    assert state["calls"] == 2
    assert [
        (e.word, e.x, e.y, e.current_page, e.previous_page, e.next_page)
        for e in read_pdic(pdic)
    ] == [("recognized", 17, 43, *PAGES)]
    if fault == "edit":
        assert ocred.read_bytes() == MANUAL_OCRED
    elif fault == "remove":
        assert not ocred.exists()
    else:
        assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
    assert page.read_bytes() == original_image
    assert read_page_sections(page) == [PageSection(0, 75)]
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))
