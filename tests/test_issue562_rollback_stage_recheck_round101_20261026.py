"""Round 101: a manual OCRed edit during rollback staging must survive.

The first optimistic ownership read is not enough: writing/fsyncing the
rollback temp file leaves time for another window to publish new OCRed bytes.
Fault injection targets that precise interval, not an already-detected edit.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr import batch_publication
from picture_capture.ocr.batch_publication import (
    _restore_ocred_bytes,
    _restore_ocred_if_unchanged,
    publish_existing_pdic_ocr,
)
from picture_capture.ocr.text_io import export_ocred, render_ocred_bytes


OLD = b"\xef\xbb\xbf000|`reviewed-before\r\n"
MANUAL = b"\xef\xbb\xbf000|`reviewed-during-rollback\r\n"
PUBLISHED = render_ocred_bytes(["recognized"])
PAGES = ("001", "@", "@")


def test_edit_during_rollback_fsync_is_not_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "001.OCRed"
    path.write_bytes(PUBLISHED)
    real_fsync = batch_publication.os.fsync
    calls = []

    def fsync_then_manual_edit(fd):
        real_fsync(fd)
        calls.append(True)
        path.write_bytes(MANUAL)

    monkeypatch.setattr(batch_publication.os, "fsync", fsync_then_manual_edit)
    with pytest.raises(RuntimeError, match="回滚暂存期间被其他操作修改"):
        _restore_ocred_if_unchanged(path, OLD, PUBLISHED)

    assert calls == [True]
    assert path.read_bytes() == MANUAL
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


def test_edit_between_first_read_and_unlink_is_not_deleted(
    tmp_path, monkeypatch,
):
    path = tmp_path / "001.OCRed"
    path.write_bytes(PUBLISHED)
    real_read = Path.read_bytes
    reads = []

    def read_with_intervening_edit(file):
        if file == path:
            reads.append(True)
            if len(reads) == 2:
                path.write_bytes(MANUAL)
        return real_read(file)

    monkeypatch.setattr(Path, "read_bytes", read_with_intervening_edit)
    with pytest.raises(RuntimeError, match="回滚前被其他操作修改"):
        _restore_ocred_if_unchanged(path, None, PUBLISHED)

    assert len(reads) == 2
    assert real_read(path) == MANUAL
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, OLD])
def test_uncontended_rollback_restores_exact_bytes(tmp_path, previous):
    path = tmp_path / "001.OCRed"
    path.write_bytes(PUBLISHED)
    _restore_ocred_if_unchanged(path, previous, PUBLISHED)
    assert (path.read_bytes() if path.exists() else None) == previous
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


def test_direct_restorer_legacy_signature_is_unchanged(tmp_path):
    path = tmp_path / "001.OCRed"
    path.write_bytes(PUBLISHED)
    _restore_ocred_bytes(path, OLD)
    assert path.read_bytes() == OLD


def test_failed_pdic_save_preserves_edit_during_rollback_fsync(
    tmp_path, monkeypatch,
):
    pdic = tmp_path / "001.PDIC"
    write_pdic(pdic, [Entry("before", 19, 57)], 120, PAGES)
    original_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(OLD)
    failed = []
    real_fsync = batch_publication.os.fsync

    def fail_pdic(*_args):
        failed.append(True)
        raise OSError("injected PDIC save error")

    def fsync_with_intervening_manual_edit(fd):
        real_fsync(fd)
        if failed:
            ocred.write_bytes(MANUAL)

    monkeypatch.setattr(batch_publication.os, "fsync", fsync_with_intervening_manual_edit)
    with pytest.raises(RuntimeError, match="PDIC 保存失败，OCRed 回滚也失败"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["recognized"],
            [Entry("recognized", 19, 57)], 120, PAGES,
            export_ocred=export_ocred,
            write_pdic=fail_pdic,
            expected_pdic_bytes=original_pdic,
            expected_ocred_bytes=OLD,
            expected_exported_ocred_bytes=PUBLISHED,
            validate_page_context=lambda: None,
        )

    assert failed == [True]
    assert pdic.read_bytes() == original_pdic
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("before", 19, 57),
    ]
    assert ocred.read_bytes() == MANUAL
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))
