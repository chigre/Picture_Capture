"""Round 91: source scan edits must not publish stale OCR or marker geometry.

Streaming SHA-256 catches same-size rewrites that stat-only checks miss.
The checks remain optimistic, not cross-process compare-and-swap.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr.batch_existing_entries import (
    _source_image_sha256, process_existing_pdic_page,
)
from picture_capture.ocr.text_io import export_ocred, import_ocred
from picture_capture.persistence.page_sections import (
    PageSection, read_page_sections, write_page_sections,
)


def _page(tmp_path):
    # BMP has fixed-size pixel payloads; pixel edits need not alter file size.
    page = tmp_path / "001.bmp"
    Image.new("RGB", (100, 120), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("original", 13, 37)], 100, ("001", "@", "@"))
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    return page, pdic, ocred


def _repaint(page):
    with Image.open(page) as image:
        altered = image.copy()
    altered.putpixel((0, 0), (0, 0, 0))
    altered.save(page)


def _run(page, ocr, *, export=export_ocred, save=None, normalize=None):
    deps = {
        "pdic_path": lambda p: p.with_suffix(".PDIC"),
        "read_pdic": read_pdic,
        "Image": Image,
        "normalize_page_rgb": normalize or (lambda opened: opened.copy().convert("RGB")),
        "effective_page_settings": lambda settings, _size, _index: settings,
        "page_template_analysis_image": lambda image, _settings, _index: image,
        "read_page_sections": read_page_sections,
        "sort_entries_reading_order": lambda entries, _geo, _sections: entries,
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": ocr,
        "qt_root": lambda root: root / "QT",
        "export_ocred": export,
        "write_pdic": save or write_pdic,
    }
    return process_existing_pdic_page(
        page, 0, page.parent, SimpleNamespace(), [],
        ("001", "@", "@"), deps=deps,
    )


@pytest.mark.parametrize("change", ["rewrite", "remove"])
def test_image_changed_during_inference_blocks_all_publication(tmp_path, change):
    page, pdic, ocred = _page(tmp_path)
    ocred.write_bytes(b"\xef\xbb\xbfmanual\r\n")
    before_pdic, before_ocred = pdic.read_bytes(), ocred.read_bytes()
    original_size = page.stat().st_size
    calls = []

    def ocr(image, entries, _settings, _rules, **_kwargs):
        assert image.size == (100, 120)
        assert [(e.x, e.y) for e in entries] == [(13, 37)]
        if change == "rewrite":
            _repaint(page)
            assert page.stat().st_size == original_size
        else:
            page.unlink()
        return ["stale-text"]

    with pytest.raises(RuntimeError, match="原始图像已被"):
        _run(page, ocr,
             export=lambda *_args: calls.append("ocred"),
             save=lambda *_args: calls.append("pdic"))
    assert calls == []
    assert pdic.read_bytes() == before_pdic
    assert ocred.read_bytes() == before_ocred


def test_image_changed_between_fingerprint_and_decode_is_rejected(tmp_path):
    page, pdic, ocred = _page(tmp_path)
    before_pdic = pdic.read_bytes()
    calls = []

    def decode_then_rewrite(opened):
        image = opened.copy().convert("RGB")
        _repaint(page)
        return image

    with pytest.raises(RuntimeError, match="原始图像已被其他操作修改"):
        _run(page, lambda *_args, **_kwargs: calls.append("ocr"),
             normalize=decode_then_rewrite,
             export=lambda *_args: calls.append("export"),
             save=lambda *_args: calls.append("pdic"))
    assert calls == []
    assert pdic.read_bytes() == before_pdic
    assert not ocred.exists()


@pytest.mark.parametrize("old_ocred", [None, b"\xef\xbb\xbfmanual-proofread\r\n"])
def test_image_replaced_during_export_compensates_ocred_exactly(
    tmp_path, old_ocred,
):
    page, pdic, ocred = _page(tmp_path)
    if old_ocred is not None:
        ocred.write_bytes(old_ocred)
    before_pdic = pdic.read_bytes()
    calls = []

    def export_then_edit_scan(path, texts):
        export_ocred(path, texts)
        calls.append("export")
        _repaint(page)

    with pytest.raises(RuntimeError, match="原始图像已被其他操作修改"):
        _run(page, lambda *_args, **_kwargs: ["new-text"],
             export=export_then_edit_scan,
             save=lambda *_args: calls.append("pdic"))
    assert calls == ["export"]
    assert pdic.read_bytes() == before_pdic
    assert (ocred.read_bytes() if ocred.exists() else None) == old_ocred
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


def test_image_and_ocred_both_modified_during_export_preserves_manual_ocred(
    tmp_path,
):
    page, pdic, ocred = _page(tmp_path)
    ocred.write_bytes(b"original")
    before_pdic = pdic.read_bytes()
    latest = b"000|`latest-human-proofreading\r\n"
    calls = []

    def export_then_two_edits(path, texts):
        export_ocred(path, texts)
        _repaint(page)
        path.write_bytes(latest)

    with pytest.raises(RuntimeError, match="OCRed 导出后内容与预期不符"):
        _run(page, lambda *_args, **_kwargs: ["stale"],
             export=export_then_two_edits,
             save=lambda *_args: calls.append("pdic"))
    assert calls == []
    assert ocred.read_bytes() == latest
    assert pdic.read_bytes() == before_pdic


def test_unchanged_scan_section_and_marker_xy_publish_normally(tmp_path):
    page, pdic, ocred = _page(tmp_path)
    write_page_sections(page, [PageSection(0, 75)])
    digest = _source_image_sha256(page)
    calls = []

    def ocr(image, entries, _settings, _rules, **kwargs):
        assert image.size == (100, 120)
        assert kwargs["page_sections"] == [PageSection(0, 75)]
        assert [(e.x, e.y) for e in entries] == [(13, 37)]
        return ["recognized"]

    def save(path, entries, width, pages):
        calls.append("pdic")
        assert width == 100
        return write_pdic(path, entries, width, pages)

    assert _run(page, ocr, save=save) == 1
    assert calls == ["pdic"]
    assert _source_image_sha256(page) == digest
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("recognized", 13, 37)
    ]
    assert import_ocred(ocred) == ["recognized"]


def test_source_scan_guards_surround_decode_inference_and_publication():
    source = (
        Path(__file__).resolve().parents[1]
        / "src/picture_capture/ocr/batch_existing_entries.py"
    ).read_text(encoding="utf-8")
    assert "source_image_hash = _source_image_sha256(page)" in source
    assert "verify_page_sources()" in source
    assert "validate_page_context=verify_page_sources" in source
    assert source.index("verify_page_sources()\n    effective_settings") < source.index(
        'texts = deps["ocr_entries"]('
    )
