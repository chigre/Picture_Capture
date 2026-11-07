"""Export callbacks must not corrupt PDIC publication inputs."""
from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr.batch_existing_entries import process_existing_pdic_page
from picture_capture.ocr.text_io import export_ocred, render_ocred_bytes
from picture_capture.persistence.page_sections import read_page_sections


def test_export_mutating_texts_and_entries_does_not_corrupt_pdic(tmp_path):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (100, 120), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("before", 17, 43)], 100, ("001", "@", "@"))
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"old")
    writer_seen = []

    def export_then_mutate(path, texts):
        export_ocred(path, texts)
        texts[0] = "corrupted after export"
        texts.append("extra")

    def record_write(path, entries, width, pages):
        writer_seen.extend((type(entry), entry.word, entry.x, entry.y) for entry in entries)
        write_pdic(path, entries, width, pages)

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
        "write_pdic": record_write,
    }
    count = process_existing_pdic_page(
        page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"), deps=deps,
    )
    assert count == 1
    assert writer_seen == [(Entry, "recognized", 17, 43)]
    saved = read_pdic(pdic)
    assert [(e.word, e.x, e.y) for e in saved] == [("recognized", 17, 43)]
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
