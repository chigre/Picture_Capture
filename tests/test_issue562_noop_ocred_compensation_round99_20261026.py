"""Round 99: no-op OCRed compensation must not mutate the filesystem.

The version read is retained, but an identical before/after snapshot must
not trigger a replace or unlink. Inject an external edit immediately after
the version read to exercise that otherwise unnecessary race window.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr import batch_publication
from picture_capture.ocr.batch_publication import (
    _restore_ocred_if_unchanged,
    publish_existing_pdic_ocr,
)
from picture_capture.ocr.text_io import export_ocred, render_ocred_bytes


OLD_BYTES = b"\xef\xbb\xbf000|\x60reviewed-before\r\n"
MANUAL_BYTES = b"\xef\xbb\xbf000|\x60reviewed-during-check\r\n"
PAGES = ("001", "@", "@")


@pytest.mark.parametrize("previous", [None, OLD_BYTES])
def test_identical_snapshot_never_calls_restorer(tmp_path, monkeypatch, previous):
    ocred = tmp_path / "001.OCRed"
    if previous is not None:
        ocred.write_bytes(previous)

    def forbidden(*_args):
        raise AssertionError("no-op compensation must not replace or unlink")

    monkeypatch.setattr(batch_publication, "_restore_ocred_bytes", forbidden)
    _restore_ocred_if_unchanged(ocred, previous, previous)
    assert (ocred.read_bytes() if ocred.exists() else None) == previous


@pytest.mark.parametrize("previous", [None, OLD_BYTES])
def test_edit_after_noop_version_read_is_not_overwritten(
    tmp_path, monkeypatch, previous,
):
    ocred = tmp_path / "001.OCRed"
    if previous is not None:
        ocred.write_bytes(previous)
    real_read = Path.read_bytes
    reads = []

    def read_then_external_edit(path):
        if path == ocred:
            reads.append(True)
            # Return the old observation while an external writer creates
            # or replaces the file immediately after that observation.
            ocred.write_bytes(MANUAL_BYTES)
            if previous is None:
                raise FileNotFoundError("injected absent-at-read race")
            return previous
        return real_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_then_external_edit)
    _restore_ocred_if_unchanged(ocred, previous, previous)
    assert len(reads) == 1
    assert real_read(ocred) == MANUAL_BYTES


def test_noop_guard_still_rejects_changed_current_bytes(tmp_path):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(MANUAL_BYTES)
    with pytest.raises(RuntimeError, match="拒绝回滚覆盖人工校对内容"):
        _restore_ocred_if_unchanged(ocred, OLD_BYTES, OLD_BYTES)
    assert ocred.read_bytes() == MANUAL_BYTES


def test_real_change_still_restores_exact_bom_crlf_bytes(tmp_path):
    ocred = tmp_path / "001.OCRed"
    published = render_ocred_bytes(["recognized"])
    ocred.write_bytes(published)
    _restore_ocred_if_unchanged(ocred, OLD_BYTES, published)
    assert ocred.read_bytes() == OLD_BYTES
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


def test_pdic_failure_after_identical_export_needs_no_second_ocred_write(
    tmp_path, monkeypatch,
):
    pdic = tmp_path / "001.PDIC"
    write_pdic(pdic, [Entry("old", 19, 57)], 120, PAGES)
    original_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    expected = render_ocred_bytes(["recognized"])
    ocred.write_bytes(expected)

    def forbidden(*_args):
        raise AssertionError("identical OCRed must not be compensated")

    def failed_pdic(*_args):
        raise OSError("injected PDIC write failure")

    monkeypatch.setattr(batch_publication, "_restore_ocred_bytes", forbidden)
    with pytest.raises(OSError, match="injected PDIC write failure"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["recognized"],
            [Entry("recognized", 19, 57)], 120, PAGES,
            export_ocred=export_ocred,
            write_pdic=failed_pdic,
            expected_pdic_bytes=original_pdic,
            expected_ocred_bytes=expected,
            expected_exported_ocred_bytes=expected,
            validate_page_context=lambda: None,
        )
    assert ocred.read_bytes() == expected
    assert pdic.read_bytes() == original_pdic
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("old", 19, 57),
    ]
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))
