"""Guard against a mutable PDIC writer changing Entry objects after OCR."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr.batch_existing_entries import process_existing_pdic_page
from picture_capture.ocr.text_io import export_ocred, render_ocred_bytes
from picture_capture.persistence.page_sections import read_page_sections


@pytest.mark.parametrize("mutation", ["before_write", "after_write", "none"])
def test_pdic_writer_mutation_cannot_redefine_intended_ocr_result(tmp_path, mutation):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (100, 120), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    pages = ("001", "@", "@")
    write_pdic(pdic, [Entry("old", 17, 43)], 100, pages)
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"old")

    def mutable_writer(path, entries, width, links):
        if mutation == "before_write":
            entries[0].word = "tampered"
            entries[0].x = 33
        write_pdic(path, entries, width, links)
        if mutation == "after_write":
            entries[0].word = "tampered"
            entries[0].x = 33

    deps = {
        "pdic_path": lambda p: p.with_suffix(".PDIC"),
        "read_pdic": read_pdic,
        "Image": Image,
        "normalize_page_rgb": lambda opened: opened.copy().convert("RGB"),
        "effective_page_settings": lambda s, _size, _index: s,
        "page_template_analysis_image": lambda image, _s, _i: image,
        "read_page_sections": read_page_sections,
        "sort_entries_reading_order": lambda entries, _geo, _sections: entries,
        "derive_geometry": lambda *_: object(),
        "ocr_entries": lambda *_args, **_kwargs: ["recognized"],
        "qt_root": lambda root: root / "QT",
        "export_ocred": export_ocred,
        "write_pdic": mutable_writer,
    }
    def run():
        return process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], pages, deps=deps,
        )

    if mutation == "before_write":
        with pytest.raises(RuntimeError, match="磁盘词条与本次 OCR 结果不一致"):
            run()
        assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [("tampered", 33, 43)]
    else:
        assert run() == 1
        assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [("recognized", 17, 43)]
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))
