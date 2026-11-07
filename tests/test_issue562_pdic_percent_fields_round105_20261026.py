"""Round 105: persisted PDIC percentages must match original image pixels.

read_pdic deliberately ignores X/Y percentage columns; a faulty batch writer
could save correct text and pixel coordinates but corrupt PicDic export data.
The post-save worker must detect that mismatch without a unilateral rollback.
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


@pytest.mark.parametrize("fault", [
    "wrong_x_percent", "wrong_y_percent", "invalid_percent",
    "extra_field", "wrong_width", "none",
])
def test_batch_reopen_verifies_full_pdic_serialization(tmp_path, fault):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (100, 120), "white").save(page)
    original_image = page.read_bytes()
    write_page_sections(page, [PageSection(0, 75)])
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("before", 17, 43)], 100, PAGES)
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"000|`reviewed-before\r\n")

    def writer(path, entries, width, pages):
        if fault == "wrong_width":
            return write_pdic(path, entries, width * 2, pages)
        result = write_pdic(path, entries, width, pages)
        if fault != "none":
            fields = path.read_text(encoding="utf-8").strip().split("#")
            if fault == "wrong_x_percent":
                fields[3] = "99"
            elif fault == "wrong_y_percent":
                fields[4] = "88"
            elif fault == "invalid_percent":
                fields[3] = "NaN"
            elif fault == "extra_field":
                fields.append("unexpected")
            path.write_text("#".join(fields) + "\n", encoding="utf-8")
        return result

    def recognize(_image, entries, _settings, _rules, **kwargs):
        assert kwargs["page_sections"] == [PageSection(0, 75)]
        assert [(e.x, e.y) for e in entries] == [(17, 43)]
        return ["recognized"]

    deps = {
        "pdic_path": lambda path: path.with_suffix(".PDIC"),
        "read_pdic": read_pdic,
        "Image": Image,
        "normalize_page_rgb": lambda opened: opened.copy().convert("RGB"),
        "effective_page_settings": lambda settings, _size, _index: settings,
        "page_template_analysis_image": lambda image, _settings, _index: image,
        "read_page_sections": read_page_sections,
        "sort_entries_reading_order": lambda entries, _geo, _sections: entries,
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": recognize,
        "qt_root": lambda root: root / "QT",
        "export_ocred": export_ocred,
        "write_pdic": writer,
    }

    def run():
        return process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], PAGES, deps=deps,
        )

    if fault == "none":
        assert run() == 1
        assert pdic.read_text(encoding="utf-8").strip() == (
            "recognized#17#43#17#43#001#@#@"
        )
    else:
        # The permissive legacy reader alone would not catch these faults.
        assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
            ("before", 17, 43),
        ]
        with pytest.raises(RuntimeError, match="PDIC 序列化字段与本次 OCR 结果不一致"):
            run()
        assert [(e.word, e.x, e.y, e.current_page) for e in read_pdic(pdic)] == [
            ("recognized", 17, 43, "001"),
        ]

    # Once the writer returns, never roll back OCRed alone.
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
    assert page.read_bytes() == original_image
    assert read_page_sections(page) == [PageSection(0, 75)]
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))
