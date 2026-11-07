"""Round 82: an OCRed exporter may throw after atomic sidecar publication.

PDIC must never be started after an exporter failure. If OCRed was already
replaced, a catchable exception restores its previous byte-exact state.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.models import Entry
from picture_capture.ocr.batch_existing_entries import process_existing_pdic_page
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import export_ocred
import picture_capture.ocr.batch_publication as publication


@pytest.mark.parametrize("old", [
    None,
    b"000|`previous\n",
    b"\xef\xbb\xbf000|`legacy\r\n",
])
def test_post_commit_ocred_export_error_restores_exact_sidecar_without_pdic_write(
    tmp_path, old,
):
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir()
    if old is not None:
        ocred.write_bytes(old)
    pdic = tmp_path / "001.PDIC"
    pdic.write_bytes(b"previous PDIC\n")
    pdic_calls = []

    def export_then_fail(path, texts):
        export_ocred(path, texts)
        assert path.exists()
        raise OSError("export post-commit failure")

    with pytest.raises(OSError, match="export post-commit failure"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["new-text"], [Entry("new-text", 12, 20)], 100,
            ("001", "@", "@"),
            export_ocred=export_then_fail,
            write_pdic=lambda *_args: pdic_calls.append("called"),
        )
    assert pdic_calls == []
    assert pdic.read_bytes() == b"previous PDIC\n"
    if old is None:
        assert not ocred.exists()
    else:
        assert ocred.read_bytes() == old
    assert list(ocred.parent.glob(".001.OCRed.*.tmp")) == []


def test_pre_commit_ocred_error_propagates_without_rollback_or_pdic(tmp_path):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(b"old")
    pdic = tmp_path / "001.PDIC"
    calls = []

    def fail_before_write(_path, _texts):
        raise OSError("export pre-commit failure")

    with pytest.raises(OSError, match="export pre-commit failure"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 1, 2)], 100,
            ("001", "@", "@"),
            export_ocred=fail_before_write,
            write_pdic=lambda *_args: calls.append("pdic"),
        )
    assert calls == []
    assert ocred.read_bytes() == b"old"
    assert not pdic.exists()


def test_ocred_post_commit_rollback_error_reports_both_failures(
    tmp_path, monkeypatch,
):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(b"old")
    pdic = tmp_path / "001.PDIC"
    pdic_calls = []

    def exporter(path, _texts):
        # Simulates bytes already published by a third-party exporter;
        # the fault-injection patch below affects only rollback.
        path.write_bytes(b"new")
        raise OSError("post-export error")

    def fail_atomic_replace(_source, _destination):
        raise PermissionError("rollback blocked")

    monkeypatch.setattr(publication.os, "replace", fail_atomic_replace)
    with pytest.raises(RuntimeError, match="OCRed 导出失败，且原文件回滚也失败") as err:
        publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 1, 2)], 100,
            ("001", "@", "@"),
            export_ocred=exporter,
            write_pdic=lambda *_args: pdic_calls.append("pdic"),
        )
    assert "post-export error" in str(err.value)
    assert "rollback blocked" in str(err.value)
    assert ocred.read_bytes() == b"new"
    assert pdic_calls == []
    assert not pdic.exists()
    assert list(tmp_path.glob(".001.OCRed.*.tmp")) == []


def test_post_export_ocred_unreadable_reports_ambiguity_without_pdic(
    tmp_path, monkeypatch,
):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(b"old")
    pdic = tmp_path / "001.PDIC"
    calls = []
    real_read = Path.read_bytes
    post_export_reads = []
    exporter_finished = []

    def read_ocred_after_export(self):
        # Keep this fault tied to the failed-export ownership inspection.
        # The shared atomic writer legitimately re-reads OCRed to verify
        # its newly committed bytes; denying that earlier read would test
        # a different failure and obscure the original recovery contract.
        if self == ocred and exporter_finished:
            post_export_reads.append(True)
            raise PermissionError("sidecar unreadable")
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", read_ocred_after_export)

    def exporter(path, texts):
        export_ocred(path, texts)
        exporter_finished.append(True)
        raise OSError("late export error")

    with pytest.raises(RuntimeError, match="无法核验 OCRed 是否已写入") as err:
        publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 1, 2)], 100,
            ("001", "@", "@"),
            export_ocred=exporter,
            write_pdic=lambda *_args: calls.append("pdic"),
        )
    assert "late export error" in str(err.value)
    assert post_export_reads == [True]
    assert calls == []
    assert not pdic.exists()
    # Fail closed: retain the newly exported bytes until recoverable.
    # The canonical atomic text writer uses native newlines on Windows
    # (CRLF), while POSIX uses LF. Compare decoded logical text here;
    # byte-exact rollback is covered by separate old-file restoration tests.
    assert ocred.read_text(encoding="utf-8") == "000|`new\n"


def test_real_batch_page_export_post_commit_failure_does_not_modify_pdic(tmp_path):
    page = tmp_path / "001.png"
    Image.new("RGB", (96, 120), "white").save(page)
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir()
    export_ocred(ocred, ["manual-review"])
    old_ocred = ocred.read_bytes()
    pdic = page.with_suffix(".PDIC")
    old_pdic = b"manual-review#12#30#12.5#25#001#@#@\n"
    pdic.write_bytes(old_pdic)
    calls = []

    def export_then_fail(path, texts):
        export_ocred(path, texts)
        raise RuntimeError("post-export hook fault")

    deps = {
        "read_pdic": lambda _path: [Entry("manual-review", 12, 30)],
        "pdic_path": lambda path: path.with_suffix(".PDIC"),
        "Image": Image,
        "normalize_page_rgb": lambda image: image.copy().convert("RGB"),
        "effective_page_settings": lambda settings, _size, _index: settings,
        "page_template_analysis_image": lambda image, _settings, _index: image,
        "read_page_sections": lambda _page: [],
        "sort_entries_reading_order": lambda entries, _geometry, _sections: entries,
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": lambda *_args, **_kwargs: ["new-ocr"],
        "qt_root": lambda root: root / "QT",
        "export_ocred": export_then_fail,
        "write_pdic": lambda *_args: calls.append("write"),
    }
    with pytest.raises(RuntimeError, match="post-export hook fault"):
        process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"),
            deps=deps,
        )
    assert calls == []
    assert ocred.read_bytes() == old_ocred
    assert pdic.read_bytes() == old_pdic


def test_export_error_compensation_is_before_pdic_dispatch():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture/ocr"
    source = (root / "batch_publication.py").read_text(encoding="utf-8")
    assert "except Exception as export_error:" in source
    assert "if current_ocred != previous:" in source
    assert source.index("if current_ocred != previous:") < source.index(
        "write_pdic(pdic_path, entries, image_width, pages_info)"
    )
