"""PDIC changes during OCRed rollback staging must block one-sided restore.

The failed-PDIC-save branch previously checked PDIC *before* staging the
compensating OCRed bytes. A second process could commit PDIC while that temp
file was being fsynced, leaving a stale OCRed rollback paired with new PDIC.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import export_ocred, render_ocred_bytes

ORIGINAL_PDIC = b"original PDIC"
EDITED_PDIC = b"manual PDIC after failed save"
ORIGINAL_OCRED = b"\xef\xbb\xbf000|`proofread\r\n"
PUBLISHED_OCRED = render_ocred_bytes(["recognized"])


def _run(tmp_path, previous, writer):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(ORIGINAL_PDIC)
    if previous is not None:
        ocred.write_bytes(previous)
    return pdic, ocred, lambda: publish_existing_pdic_ocr(
        ocred, pdic, ["recognized"], [], 100, ("001", "@", "@"),
        export_ocred=export_ocred,
        write_pdic=writer,
        expected_pdic_bytes=ORIGINAL_PDIC,
        expected_ocred_bytes=previous,
        expected_exported_ocred_bytes=PUBLISHED_OCRED,
    )


@pytest.mark.parametrize("previous", [ORIGINAL_OCRED, b""])
def test_pdic_replaced_while_rollback_temp_is_fsynced_preserves_export(
    tmp_path, monkeypatch, previous,
):
    failed = []
    def fail_pdic(*_args):
        failed.append(True)
        raise OSError("injected PDIC failure")

    pdic, ocred, run = _run(tmp_path, previous, fail_pdic)
    real_fsync = publication.os.fsync
    injected = []

    def fsync_then_change_pdic(fd):
        real_fsync(fd)
        if failed and not injected:
            injected.append(True)
            pdic.write_bytes(EDITED_PDIC)

    monkeypatch.setattr(publication.os, "fsync", fsync_then_change_pdic)
    with pytest.raises(RuntimeError, match="回滚暂存期间 PDIC 已被其他操作修改"):
        run()
    assert failed == [True]
    assert injected == [True]
    assert pdic.read_bytes() == EDITED_PDIC
    assert ocred.read_bytes() == PUBLISHED_OCRED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


def test_pdic_changed_just_before_new_ocred_unlink_is_preserved(
    tmp_path, monkeypatch,
):
    pdic, ocred, run = _run(
        tmp_path, None,
        lambda *_args: (_ for _ in ()).throw(OSError("PDIC failed")),
    )
    original_read = publication._read_optional_ocred_bytes
    observed = []

    def read_then_change_pdic(path):
        value = original_read(path)
        observed.append(value)
        pdic.write_bytes(EDITED_PDIC)
        return value

    monkeypatch.setattr(publication, "_read_optional_ocred_bytes", read_then_change_pdic)
    with pytest.raises(RuntimeError, match="回滚暂存期间 PDIC 已被其他操作修改"):
        run()
    assert observed == [PUBLISHED_OCRED]
    assert pdic.read_bytes() == EDITED_PDIC
    assert ocred.read_bytes() == PUBLISHED_OCRED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


def test_pdic_unreadable_after_rollback_staging_refuses_one_sided_restore(
    tmp_path, monkeypatch,
):
    failed = []
    def fail_pdic(*_args):
        failed.append(True)
        raise OSError("PDIC failed")

    pdic, ocred, run = _run(tmp_path, ORIGINAL_OCRED, fail_pdic)
    real_fsync = publication.os.fsync
    real_read = Path.read_bytes
    staged = []

    def fsync_then_mark(fd):
        real_fsync(fd)
        if failed:
            staged.append(True)

    def read_with_late_permission_error(path):
        if path == pdic and staged:
            raise PermissionError("PDIC temporarily locked")
        return real_read(path)

    monkeypatch.setattr(publication.os, "fsync", fsync_then_mark)
    monkeypatch.setattr(Path, "read_bytes", read_with_late_permission_error)
    with pytest.raises(RuntimeError, match="回滚即将写入时无法核验 PDIC"):
        run()
    assert staged == [True]
    assert real_read(pdic) == ORIGINAL_PDIC
    assert real_read(ocred) == PUBLISHED_OCRED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, ORIGINAL_OCRED])
def test_uncontended_failed_pdic_save_still_restores_ocred(tmp_path, previous):
    pdic, ocred, run = _run(
        tmp_path, previous,
        lambda *_args: (_ for _ in ()).throw(OSError("PDIC failed")),
    )
    with pytest.raises(OSError, match="PDIC failed"):
        run()
    assert pdic.read_bytes() == ORIGINAL_PDIC
    assert (ocred.read_bytes() if ocred.exists() else None) == previous
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
