"""Round 86: refuse stale batch OCR publication after external OCRed proofreading.

The sidecar and PDIC snapshots are optimistic byte guards, not cross-process
locks or a two-file transaction.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr.batch_existing_entries import process_existing_pdic_page
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import export_ocred, import_ocred


def _deps(tmp_path, ocr, writes):
    def export(path, texts):
        writes.append("ocred")
        export_ocred(path, texts)

    def save(path, entries, width, pages):
        writes.append("pdic")
        write_pdic(path, entries, width, pages)

    return {
        "pdic_path": lambda page: page.with_suffix(".PDIC"),
        "read_pdic": read_pdic,
        "Image": Image,
        "normalize_page_rgb": lambda opened: opened.copy().convert("RGB"),
        "effective_page_settings": lambda settings, _size, _index: settings,
        "page_template_analysis_image": lambda image, _settings, _index: image,
        "read_page_sections": lambda _page: [],
        "sort_entries_reading_order": lambda entries, _geometry, _sections: entries,
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": ocr,
        "qt_root": lambda _root: tmp_path / "QT",
        "export_ocred": export,
        "write_pdic": save,
    }


@pytest.mark.parametrize("interference", ["replace", "delete", "create"])
def test_external_ocred_proofreading_during_inference_never_gets_overwritten(
    tmp_path, interference,
):
    page = tmp_path / "001.png"
    Image.new("RGB", (88, 122), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("old", 17, 43)], 88, ("001", "@", "@"))
    original_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    if interference != "create":
        ocred.write_bytes(b"\xef\xbb\xbf000|`prior\r\n")
    original_sidecar = ocred.read_bytes() if ocred.exists() else None
    writes = []

    def ocr(_image, entries, _settings, _rules, **_kwargs):
        assert [(e.word, e.x, e.y) for e in entries] == [("old", 17, 43)]
        if interference == "replace":
            ocred.write_bytes(b"\xef\xbb\xbf000|`proofread\r\n")
        elif interference == "delete":
            ocred.unlink()
        else:
            export_ocred(ocred, ["proofread-new"])
        return ["stale-recognition"]

    with pytest.raises(RuntimeError, match="发布前 OCRed 已被其他操作修改"):
        process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"),
            deps=_deps(tmp_path, ocr, writes),
        )
    assert writes == []
    assert pdic.read_bytes() == original_pdic
    if interference == "delete":
        assert not ocred.exists()
    elif interference == "replace":
        assert ocred.read_bytes() == b"\xef\xbb\xbf000|`proofread\r\n"
        assert ocred.read_bytes() != original_sidecar
    else:
        assert import_ocred(ocred) == ["proofread-new"]


@pytest.mark.parametrize("initial_sidecar", [None, b"\xef\xbb\xbf000|`old\r\n"])
def test_unmodified_ocred_snapshot_allows_original_coordinate_publication(
    tmp_path, initial_sidecar,
):
    page = tmp_path / "001.png"
    Image.new("RGB", (88, 122), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("old", 17, 43)], 88, ("001", "@", "@"))
    ocred = tmp_path / "QT" / "001.OCRed"
    if initial_sidecar is not None:
        ocred.parent.mkdir(parents=True, exist_ok=True)
        ocred.write_bytes(initial_sidecar)
    writes = []
    count = process_existing_pdic_page(
        page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"),
        deps=_deps(
            tmp_path,
            lambda *_args, **_kwargs: ["fresh-recognition"],
            writes,
        ),
    )
    assert count == 1
    assert writes == ["ocred", "pdic"]
    assert import_ocred(ocred) == ["fresh-recognition"]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("fresh-recognition", 17, 43)
    ]


def test_direct_publisher_rejects_changed_sidecar_without_touching_pdic(tmp_path):
    pdic = tmp_path / "001.PDIC"
    write_pdic(pdic, [Entry("original", 11, 22)], 88, ("001", "@", "@"))
    original_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True)
    ocred.write_bytes(b"000|`before\n")
    expected = ocred.read_bytes()
    ocred.write_bytes(b"000|`proofread\n")
    writes = []

    with pytest.raises(RuntimeError, match="发布前 OCRed 已被其他操作修改"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["stale"], [Entry("stale", 11, 22)],
            88, ("001", "@", "@"),
            export_ocred=lambda *_args: writes.append("ocred"),
            write_pdic=lambda *_args: writes.append("pdic"),
            expected_pdic_bytes=original_pdic,
            expected_ocred_bytes=expected,
        )
    assert writes == []
    assert pdic.read_bytes() == original_pdic
    assert ocred.read_bytes() == b"000|`proofread\n"


def test_round86_worker_passes_both_pre_inference_snapshots():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture/ocr"
    leaf = (root / "batch_existing_entries.py").read_text(encoding="utf-8")
    publisher = (root / "batch_publication.py").read_text(encoding="utf-8")
    assert "source_ocred_bytes = ocred_file.read_bytes()" in leaf
    assert leaf.index("source_ocred_bytes = ocred_file.read_bytes()") < leaf.index(
        'deps["ocr_entries"]('
    )
    assert "expected_ocred_bytes=source_ocred_bytes" in leaf
    assert "expected_pdic_bytes=source_pdic_bytes" in leaf
    assert "previous != expected_ocred_bytes" in publisher
    assert publisher.index("previous != expected_ocred_bytes") < publisher.index(
        "export_ocred(ocred_path, texts)"
    )
