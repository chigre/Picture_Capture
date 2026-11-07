"""Mutable exporter callbacks must not rewrite OCRed expectations or counts."""
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


@pytest.mark.parametrize("mutation", ["clear", "replace", "append", "none"])
def test_exporter_mutates_ocr_list_after_correct_write(tmp_path, mutation):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (100, 120), "white").save(page)
    write_page_sections(page, [PageSection(0, 75)])
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("before", 17, 43)], 100, ("001", "@", "@"))
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"previous proofread OCRed")

    def export_then_mutate(path, texts):
        export_ocred(path, texts)
        if mutation == "clear":
            texts.clear()
        elif mutation == "replace":
            texts[0] = "callback-modified"
        elif mutation == "append":
            texts.append("unexpected extra")

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
        "export_ocred": export_then_mutate,
        "write_pdic": write_pdic,
    }
    assert process_existing_pdic_page(
        page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"), deps=deps,
    ) == 1
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
    persisted = read_pdic(pdic)
    assert len(persisted) == 1
    assert (persisted[0].word, persisted[0].x, persisted[0].y) == (
        "recognized", 17, 43,
    )
