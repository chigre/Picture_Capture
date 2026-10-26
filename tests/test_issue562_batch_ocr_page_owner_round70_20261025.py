"""Round 70: batch OCR page implementation lives in OCR, not the Tk controller."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from picture_capture.models import Entry
from picture_capture.io.formats import read_pdic as real_read_pdic, write_pdic as real_write_pdic
from picture_capture.ocr.batch_existing_entries import process_existing_pdic_page
from picture_capture.ocr.text_io import export_ocred as real_export_ocred


def _test_deps(tmp_path: Path, events: list, *, fail_ocr: bool = False):
    def ocr_entries(_image, entries, _settings, _rules, **kwargs):
        events.append(("ocr", [(e.word, e.x, e.y) for e in entries]))
        assert kwargs["profile_page_index"] == 1
        assert kwargs["page_sections"] == ["section"]
        if fail_ocr:
            raise RuntimeError("injected OCR failure")
        return ["alpha", "beta"]

    def export_ocred(path, texts):
        events.append(("export", path, list(texts)))
        real_export_ocred(path, texts)

    def write_pdic(path, entries, width, pages):
        events.append((
            "write", path, [(e.word, e.x, e.y) for e in entries], width, pages,
        ))
        # Exercise the real disk contract: a successful callback must publish
        # a PDIC file for the post-commit integrity checks to inspect.
        real_write_pdic(path, entries, width, pages)

    return {
        "read_pdic": lambda _path: [
            Entry("original-a", 9, 14),
            Entry("original-b", 42, 78),
        ],
        "pdic_path": lambda page: page.with_suffix(".PDIC"),
        "Image": Image,
        "normalize_page_rgb": lambda image: image.copy().convert("RGB"),
        "effective_page_settings": lambda settings, _size, _index: settings,
        "page_template_analysis_image": lambda image, _settings, _index: image,
        "read_page_sections": lambda _page: ["section"],
        "sort_entries_reading_order": lambda entries, _geometry, _sections: entries,
        "derive_geometry": lambda _image, _settings: object(),
        "ocr_entries": ocr_entries,
        "qt_root": lambda _root: tmp_path / "qt",
        "export_ocred": export_ocred,
        "write_pdic": write_pdic,
    }


def test_existing_pdic_batch_page_preserves_order_source_xy_and_file_contract(tmp_path):
    page = tmp_path / "001.png"
    Image.new("RGB", (80, 120), "white").save(page)
    events = []
    settings = object()

    count = process_existing_pdic_page(
        page, 1, tmp_path, settings, [], ("001", "@", "002"),
        deps=_test_deps(tmp_path, events),
    )

    assert count == 2
    assert [event[0] for event in events] == ["ocr", "export", "write"]
    assert events[0][1] == [
        ("original-a", 9, 14),
        ("original-b", 42, 78),
    ]
    assert events[1] == ("export", tmp_path / "qt" / "001.OCRed", ["alpha", "beta"])
    assert events[2] == (
        "write", page.with_suffix(".PDIC"),
        [("alpha", 9, 14), ("beta", 42, 78)],
        80, ("001", "@", "002"),
    )
    assert [(e.word, e.x, e.y) for e in real_read_pdic(page.with_suffix(".PDIC"))] == [
        ("alpha", 9, 14), ("beta", 42, 78),
    ]
    assert page.with_suffix(".PDIC").read_text(encoding="utf-8").splitlines()[0].endswith(
        "#001#@#002"
    )


def test_batch_page_ocr_failure_does_not_publish_ocred_or_pdic(tmp_path):
    page = tmp_path / "001.png"
    Image.new("RGB", (80, 120), "white").save(page)
    events = []
    with pytest.raises(RuntimeError, match="injected OCR failure"):
        process_existing_pdic_page(
            page, 1, tmp_path, object(), [], ("001", "@", "002"),
            deps=_test_deps(tmp_path, events, fail_ocr=True),
        )
    assert [event[0] for event in events] == ["ocr"]


def test_controller_delegates_to_physical_ocr_page_owner():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture"
    controller = (root / "ui/controllers/detection.py").read_text(encoding="utf-8")
    flow = (root / "ui/batch_ocr_flow.py").read_text(encoding="utf-8")
    leaf = (root / "ocr/batch_existing_entries.py").read_text(encoding="utf-8")
    assert "from ...ocr.batch_existing_entries import process_existing_pdic_page" in controller
    assert "return run_existing_pdic_batch(" in controller
    assert 'live["process_existing_pdic_page"](' in flow
    assert "foreground_page_edit=True, allow_pdic_edits=True," in flow
    assert "foreground_page_edit=True" not in leaf
    assert "def process_existing_pdic_page(" in leaf
    assert 'deps["ocr_entries"](' in leaf
    publication = (root / "ocr/batch_publication.py").read_text(encoding="utf-8")
    assert "publish_existing_pdic_ocr(" in leaf
    assert 'write_pdic=deps["write_pdic"]' in leaf
    assert "write_pdic(pdic_path, entries, image_width, pages_info)" in publication
