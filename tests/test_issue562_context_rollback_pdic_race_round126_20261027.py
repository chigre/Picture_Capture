"""Round 126: a failed SECTION/source check cannot undo OCRed over newer PDIC.

Inject faults after OCRed export, inside the second (pre-PDIC) page-source
validation or during compensation staging. No PDIC writer may be invoked.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr

OLD_PDIC = b"old PDIC marker bytes"
NEW_PDIC = b"manual PDIC marker correction"
OLD_OCRED = b"\\xef\\xbb\\xbf000|`human reviewed\\r\\n"
EXPORTED_OCRED = b"\\xef\\xbb\\xbf000|`new OCR\\r\\n"


def _setup(tmp_path, previous):
    pdic, ocred = tmp_path / "001.PDIC", tmp_path / "001.OCRed"
    pdic.write_bytes(OLD_PDIC)
    if previous is not None:
        ocred.write_bytes(previous)
    return pdic, ocred


def _run(pdic, ocred, previous, validator, calls):
    def exporter(path, _texts):
        calls.append("export")
        path.write_bytes(EXPORTED_OCRED)

    def writer(*_args):
        calls.append("write")
        pdic.write_bytes(b"committed PDIC")

    return publish_existing_pdic_ocr(
        ocred, pdic, ["new OCR"], [], 100, ("001", "@", "@"),
        export_ocred=exporter,
        write_pdic=writer,
        expected_pdic_bytes=OLD_PDIC,
        expected_ocred_bytes=previous,
        expected_exported_ocred_bytes=EXPORTED_OCRED,
        validate_page_context=validator,
    )


@pytest.mark.parametrize("previous", [None, OLD_OCRED], ids=["new", "existing"])
@pytest.mark.parametrize("mutation", ["replace", "remove"])
def test_context_failure_with_concurrent_pdic_change_preserves_both(
    tmp_path, previous, mutation,
):
    pdic, ocred = _setup(tmp_path, previous)
    calls = []
    checks = []

    def validate():
        checks.append(True)
        if len(checks) == 2:
            if mutation == "replace":
                pdic.write_bytes(NEW_PDIC)
            else:
                pdic.unlink()
            raise RuntimeError("SECTION changed during image hash")

    with pytest.raises(RuntimeError, match="SECTION 发布前核验失败，且 OCRed 回滚失败") as error:
        _run(pdic, ocred, previous, validate, calls)
    assert "PDIC 已被其他操作修改" in str(error.value)
    assert calls == ["export"]
    assert len(checks) == 2
    assert (pdic.read_bytes() if pdic.exists() else None) == (
        NEW_PDIC if mutation == "replace" else None
    )
    assert ocred.read_bytes() == EXPORTED_OCRED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, OLD_OCRED], ids=["new", "existing"])
def test_context_failure_with_unreadable_pdic_preserves_ocred(
    tmp_path, monkeypatch, previous,
):
    pdic, ocred = _setup(tmp_path, previous)
    calls, checks = [], []
    original_read = Path.read_bytes

    def validate():
        checks.append(True)
        if len(checks) == 2:
            raise RuntimeError("source image changed")

    def read_with_lock(path):
        if path == pdic and len(checks) == 2:
            raise PermissionError("injected PDIC lock")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_with_lock)
    with pytest.raises(RuntimeError, match="回滚前无法确认 PDIC 版本"):
        _run(pdic, ocred, previous, validate, calls)
    assert calls == ["export"]
    assert original_read(pdic) == OLD_PDIC
    assert original_read(ocred) == EXPORTED_OCRED


def test_context_failure_pdic_changed_while_rollback_temp_fsyncs(
    tmp_path, monkeypatch,
):
    pdic, ocred = _setup(tmp_path, OLD_OCRED)
    calls, checks = [], []
    real_fsync = publication.os.fsync
    injected = []

    def validate():
        checks.append(True)
        if len(checks) == 2:
            raise RuntimeError("SECTION changed")

    def fsync_and_edit_pdic(fd):
        real_fsync(fd)
        if len(checks) == 2 and not injected:
            injected.append(True)
            pdic.write_bytes(NEW_PDIC)

    monkeypatch.setattr(publication.os, "fsync", fsync_and_edit_pdic)
    with pytest.raises(RuntimeError, match="PDIC 已被其他操作修改"):
        _run(pdic, ocred, OLD_OCRED, validate, calls)
    assert injected == [True]
    assert calls == ["export"]
    assert pdic.read_bytes() == NEW_PDIC
    assert ocred.read_bytes() == EXPORTED_OCRED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


def test_context_failure_pdic_changed_just_before_new_ocred_unlink(
    tmp_path, monkeypatch,
):
    pdic, ocred = _setup(tmp_path, None)
    calls, checks = [], []
    real_read = publication._read_optional_ocred_bytes

    def validate():
        checks.append(True)
        if len(checks) == 2:
            raise RuntimeError("SECTION changed")

    def ocred_read_then_pdic_edit(path):
        data = real_read(path)
        pdic.write_bytes(NEW_PDIC)
        return data

    monkeypatch.setattr(publication, "_read_optional_ocred_bytes", ocred_read_then_pdic_edit)
    with pytest.raises(RuntimeError, match="PDIC 已被其他操作修改"):
        _run(pdic, ocred, None, validate, calls)
    assert calls == ["export"]
    assert pdic.read_bytes() == NEW_PDIC
    assert ocred.read_bytes() == EXPORTED_OCRED


@pytest.mark.parametrize("previous", [None, OLD_OCRED], ids=["new", "existing"])
def test_uncontended_context_failure_still_restores_original_ocred(
    tmp_path, previous,
):
    pdic, ocred = _setup(tmp_path, previous)
    calls, checks = [], []

    def validate():
        checks.append(True)
        if len(checks) == 2:
            raise RuntimeError("SECTION changed")

    with pytest.raises(RuntimeError, match="SECTION changed"):
        _run(pdic, ocred, previous, validate, calls)
    assert calls == ["export"]
    assert len(checks) == 2
    assert pdic.read_bytes() == OLD_PDIC
    assert (ocred.read_bytes() if ocred.exists() else None) == previous
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


def test_unchanged_page_context_still_commits_both_sidecars(tmp_path):
    pdic, ocred = _setup(tmp_path, OLD_OCRED)
    calls, checks = [], []
    _run(pdic, ocred, OLD_OCRED, lambda: checks.append(True), calls)
    assert calls == ["export", "write"]
    assert len(checks) == 3
    assert pdic.read_bytes() == b"committed PDIC"
    assert ocred.read_bytes() == EXPORTED_OCRED
