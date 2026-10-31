"""Round 83: preserve external PDIC edits made during an OCR page worker.

The foreground batch UI also claims pages for manual editing. This disk-byte
guard protects edits from another window/process outside that Tk state machine.
It is a pre-publication conflict check, not a cross-process filesystem lock.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.models import Entry
from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.ocr.batch_existing_entries import process_existing_pdic_page
from picture_capture.ocr.text_io import export_ocred


def _deps(root, ocr_fn, events):
    return {
        "read_pdic": read_pdic,
        "pdic_path": lambda page: page.with_suffix(".PDIC"),
        "Image": Image,
        "normalize_page_rgb": lambda opened: opened.copy().convert("RGB"),
        "effective_page_settings": lambda s, _size, _index: s,
        "page_template_analysis_image": lambda image, _settings, _index: image,
        "read_page_sections": lambda _page: [],
        "sort_entries_reading_order": lambda entries, _geo, _sections: entries,
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": ocr_fn,
        "qt_root": lambda _root: root / "QT",
        "export_ocred": lambda path, texts: events.append("ocred") or export_ocred(path, texts),
        "write_pdic": lambda path, entries, width, pages: (
            events.append("pdic") or write_pdic(path, entries, width, pages)
        ),
    }


@pytest.mark.parametrize("interference", ["rewrite", "remove"])
def test_external_manual_edit_during_ocr_blocks_all_batch_publication(
    tmp_path, interference,
):
    page = tmp_path / "001.png"
    Image.new("RGB", (90, 130), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("initial", 12, 37)], 90, ("001", "@", "@"))
    old_ocred = tmp_path / "QT" / "001.OCRed"
    export_ocred(old_ocred, ["manually-reviewed"])
    original_ocred = old_ocred.read_bytes()
    events = []

    def ocr(_image, entries, _settings, _rules, **_kwargs):
        assert [(e.word, e.x, e.y) for e in entries] == [("initial", 12, 37)]
        if interference == "rewrite":
            write_pdic(pdic, [Entry("user-correction", 16, 42)], 90, ("001", "@", "@"))
        else:
            pdic.unlink()
        return ["stale-ocr"]

    with pytest.raises(RuntimeError, match="PDIC 已被其他操作修改"):
        process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"),
            deps=_deps(tmp_path, ocr, events),
        )
    assert events == []
    assert old_ocred.read_bytes() == original_ocred
    if interference == "rewrite":
        assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
            ("user-correction", 16, 42)
        ]
    else:
        assert not pdic.exists()


def test_pdic_created_while_empty_page_is_processing_is_not_overwritten(tmp_path):
    page = tmp_path / "002.png"
    Image.new("RGB", (75, 110), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    events = []

    def ocr(_image, entries, _settings, _rules, **_kwargs):
        assert entries == []
        write_pdic(pdic, [Entry("user-created", 8, 15)], 75, ("002", "@", "@"))
        return []

    with pytest.raises(RuntimeError, match="PDIC 已被其他操作修改"):
        process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], ("002", "@", "@"),
            deps=_deps(tmp_path, ocr, events),
        )
    assert events == []
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("user-created", 8, 15)
    ]
    assert not (tmp_path / "QT" / "002.OCRed").exists()


def test_unchanged_original_pdic_is_published_normally(tmp_path):
    page = tmp_path / "003.png"
    Image.new("RGB", (90, 120), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("old", 19, 45)], 90, ("003", "@", "@"))
    events = []
    count = process_existing_pdic_page(
        page, 0, tmp_path, SimpleNamespace(), [], ("003", "@", "@"),
        deps=_deps(
            tmp_path,
            lambda _img, _entries, _settings, _rules, **kwargs: ["recognized"],
            events,
        ),
    )
    assert count == 1
    assert events == ["ocred", "pdic"]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("recognized", 19, 45)
    ]
    assert (tmp_path / "QT" / "003.OCRed").read_text(
        encoding="utf-8"
    ) == "000|`recognized\n"


def test_conflict_check_precedes_sidecar_and_pdic_writes():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture/ocr"
    source = (root / "batch_existing_entries.py").read_text(encoding="utf-8")
    assert "source_pdic_bytes = pdic_file.read_bytes()" in source
    assert "current_pdic_bytes = pdic_file.read_bytes()" in source
    assert source.index("if current_pdic_bytes != source_pdic_bytes:") < source.index(
        "publish_existing_pdic_ocr("
    )
