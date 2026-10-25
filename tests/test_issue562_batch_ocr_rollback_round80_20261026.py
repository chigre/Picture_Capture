"""Round 80: rollback of OCRed sidecars on PDIC save failure.

The guarantees are for catchable errors only, not power loss or concurrent
external writers: both artifacts are individually atomic but not one
filesystem transaction.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.models import Entry
from picture_capture.io.formats import write_pdic
from picture_capture.ocr.batch_existing_entries import process_existing_pdic_page
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import export_ocred, import_ocred
import picture_capture.ocr.batch_publication as publication


@pytest.mark.parametrize("old", [None, b"000|`old-text\n", b"\xef\xbb\xbf000|`older\r\n"])
def test_failed_pdic_commit_restores_exact_original_ocred_bytes(tmp_path, old):
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir()
    if old is not None:
        ocred.write_bytes(old)
    pdic = tmp_path / "001.PDIC"
    pdic.write_bytes(b"original PDIC bytes\n")
    calls = []

    def failed_write(path, entries, width, pages):
        calls.append((path, [(e.word, e.x, e.y) for e in entries]))
        raise OSError("simulated PDIC write failure")

    with pytest.raises(OSError, match="simulated PDIC write failure"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["new-value"], [Entry("new-value", 12, 19)], 90,
            ("001", "@", "@"),
            export_ocred=export_ocred,
            write_pdic=failed_write,
        )
    assert calls == [(pdic, [("new-value", 12, 19)])]
    assert pdic.read_bytes() == b"original PDIC bytes\n"
    if old is None:
        assert not ocred.exists()
    else:
        assert ocred.read_bytes() == old
    assert list(ocred.parent.glob(".001.OCRed.*.tmp")) == []


def test_successful_publication_preserves_ocred_before_pdic_and_source_xy(tmp_path):
    ocred = tmp_path / "QT" / "001.OCRed"
    pdic = tmp_path / "001.PDIC"
    entries = [Entry("苹果", 15, 20), Entry("香蕉", 70, 95)]
    observed = []

    def recorded_export(path, texts):
        observed.append("export")
        export_ocred(path, texts)

    def recorded_pdic(path, entries, width, pages):
        observed.append("pdic")
        return write_pdic(path, entries, width, pages)

    publish_existing_pdic_ocr(
        ocred, pdic, ["苹果", "香蕉"], entries, 100,
        ("001", "@", "@"),
        export_ocred=recorded_export,
        write_pdic=recorded_pdic,
    )
    assert observed == ["export", "pdic"]
    assert import_ocred(ocred) == ["苹果", "香蕉"]
    assert [(r.split("#")[0], r.split("#")[1:3]) for r in
            pdic.read_text(encoding="utf-8").splitlines()] == [
        ("苹果", ["15", "20"]), ("香蕉", ["70", "95"])
    ]


def test_ocred_export_failure_never_calls_pdic_writer(tmp_path):
    ocred = tmp_path / "QT" / "001.OCRed"
    pdic = tmp_path / "001.PDIC"
    ocred.parent.mkdir()
    ocred.write_bytes(b"old")
    called = []

    def export_failure(_path, _texts):
        raise OSError("export failed")

    with pytest.raises(OSError, match="export failed"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 1, 2)], 100, ("001", "@", "@"),
            export_ocred=export_failure,
            write_pdic=lambda *_args: called.append("write"),
        )
    assert called == []
    assert ocred.read_bytes() == b"old"


def test_failed_compensation_reports_both_pdic_and_rollback_errors(
    tmp_path, monkeypatch,
):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(b"old")

    def replacing_fails(_source, _destination):
        raise OSError("restore blocked")

    monkeypatch.setattr(publication.os, "replace", replacing_fails)
    with pytest.raises(RuntimeError, match="PDIC 保存失败，OCRed 回滚也失败") as exc:
        publish_existing_pdic_ocr(
            ocred, tmp_path / "001.PDIC", ["new"],
            [Entry("new", 1, 2)], 100, ("001", "@", "@"),
            # This fake intentionally avoids os.replace during export;
            # the simulated fault is specifically in the rollback path.
            export_ocred=lambda path, _texts: path.write_bytes(b"new"),
            write_pdic=lambda *_args: (_ for _ in ()).throw(OSError("pdic blocked")),
        )
    assert "pdic blocked" in str(exc.value)
    assert "restore blocked" in str(exc.value)
    assert ocred.read_bytes() == b"new"
    assert list(tmp_path.glob(".001.OCRed.*.tmp")) == []


def test_real_batch_page_pdic_failure_restores_existing_sidecar(tmp_path):
    page = tmp_path / "001.png"
    Image.new("RGB", (96, 120), "white").save(page)
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir()
    export_ocred(ocred, ["proofread-before"])
    old_ocred = ocred.read_bytes()
    old_pdic = b"proofread-before#12#30#12.5#25#001#@#@\n"
    page.with_suffix(".PDIC").write_bytes(old_pdic)

    deps = {
        "read_pdic": lambda _path: [Entry("proofread-before", 12, 30)],
        "pdic_path": lambda path: path.with_suffix(".PDIC"),
        "Image": Image,
        "normalize_page_rgb": lambda image: image.copy().convert("RGB"),
        "effective_page_settings": lambda settings, _size, _index: settings,
        "page_template_analysis_image": lambda image, _settings, _index: image,
        "read_page_sections": lambda _path: [],
        "sort_entries_reading_order": lambda entries, _geometry, _sections: entries,
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": lambda *_args, **_kwargs: ["fresh-OCR"],
        "qt_root": lambda root: root / "QT",
        "export_ocred": export_ocred,
        "write_pdic": lambda *_args: (_ for _ in ()).throw(OSError("PDIC denied")),
    }
    with pytest.raises(OSError, match="PDIC denied"):
        process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"),
            deps=deps,
        )
    assert ocred.read_bytes() == old_ocred
    assert page.with_suffix(".PDIC").read_bytes() == old_pdic
