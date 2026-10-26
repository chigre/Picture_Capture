"""Reject mutable callback changes to original PDIC source-pixel markers."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr.batch_existing_entries import process_existing_pdic_page
from picture_capture.ocr.text_io import export_ocred, render_ocred_bytes


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("sort_moves_marker", "排序期间"),
        ("sort_drops_marker", "排序期间"),
        ("ocr_moves_marker", "识别期间"),
        ("ocr_reorders_markers", "识别期间"),
    ],
)
def test_mutable_callbacks_cannot_publish_changed_marker_coordinates(
    tmp_path, fault, message,
):
    page = tmp_path / "001.png"
    Image.new("RGB", (80, 100), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    write_pdic(
        pdic, [Entry("old-one", 7, 19), Entry("old-two", 32, 71)],
        80, ("001", "@", "@"),
    )
    original_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(exist_ok=True)
    ocred.write_bytes(b"previously proofread OCRed bytes")
    original_ocred = ocred.read_bytes()
    calls = []

    def sort_entries(entries, _geometry, _sections):
        if fault == "sort_moves_marker":
            entries[0].x += 2
        elif fault == "sort_drops_marker":
            return entries[:-1]
        return entries

    def recognize(_image, entries, _settings, _rules, **_kwargs):
        calls.append("ocr")
        if fault == "ocr_moves_marker":
            entries[1].y += 3
        elif fault == "ocr_reorders_markers":
            entries.reverse()
        return ["first", "second"]

    deps = {
        "read_pdic": read_pdic,
        "pdic_path": lambda p: p.with_suffix(".PDIC"),
        "Image": Image,
        "normalize_page_rgb": lambda im: im.copy().convert("RGB"),
        "effective_page_settings": lambda s, _size, _index: s,
        "page_template_analysis_image": lambda im, _settings, _index: im,
        "read_page_sections": lambda _p: [],
        "sort_entries_reading_order": sort_entries,
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": recognize,
        "qt_root": lambda root: root / "QT",
        "export_ocred": lambda *_args: calls.append("export"),
        "write_pdic": lambda *_args: calls.append("write"),
    }
    with pytest.raises(RuntimeError, match=message):
        process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"),
            deps=deps,
        )
    assert pdic.read_bytes() == original_pdic
    assert ocred.read_bytes() == original_ocred
    assert "export" not in calls and "write" not in calls
    assert ("ocr" in calls) is fault.startswith("ocr_")


def test_sort_can_reorder_without_changing_source_pixel_coordinates(tmp_path):
    page = tmp_path / "001.png"
    Image.new("RGB", (80, 100), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    write_pdic(
        pdic, [Entry("old-one", 7, 19), Entry("old-two", 32, 71)],
        80, ("001", "@", "@"),
    )
    qt = tmp_path / "QT"
    qt.mkdir(exist_ok=True)
    ocred = qt / "001.OCRed"
    ocred.write_bytes(b"old OCRed")

    deps = {
        "read_pdic": read_pdic,
        "pdic_path": lambda p: p.with_suffix(".PDIC"),
        "Image": Image,
        "normalize_page_rgb": lambda im: im.copy().convert("RGB"),
        "effective_page_settings": lambda s, _size, _index: s,
        "page_template_analysis_image": lambda im, _settings, _index: im,
        "read_page_sections": lambda _p: [],
        "sort_entries_reading_order": lambda entries, *_: list(reversed(entries)),
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": lambda *_args, **_kwargs: ["first", "second"],
        "qt_root": lambda root: root / "QT",
        "export_ocred": export_ocred,
        "write_pdic": write_pdic,
    }
    count = process_existing_pdic_page(
        page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"),
        deps=deps,
    )
    assert count == 2
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("first", 32, 71), ("second", 7, 19),
    ]
    assert ocred.read_bytes() == render_ocred_bytes(["first", "second"])
