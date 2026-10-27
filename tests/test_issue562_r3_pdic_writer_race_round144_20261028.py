"""Round 144: R3 quarantine must survive the PDIC writer and rollback window.

A pending R3 review transaction owns the page bundle even when PDIC bytes
still match the OCR worker's old snapshot. Never unilaterally undo OCRed
against that transaction. These tests use real files and injected callbacks.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


OLD_PDIC = b"manual PDIC before OCR"
OLD_OCRED = b"manual OCRed before OCR"
NEW_PDIC = b"PDIC saved by callback"
NEW_OCRED = b"OCR result from batch"


def _paths(tmp_path: Path, previous: bytes | None):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    marker = tmp_path / ".001.PDIC.r3-inflight.json"
    pdic.write_bytes(OLD_PDIC)
    if previous is not None:
        ocred.write_bytes(previous)
    return pdic, ocred, marker


def _publish(pdic, ocred, previous, save):
    return publication.publish_existing_pdic_ocr(
        ocred, pdic, ["recognized"], [], 100, ("001", "@", "@"),
        export_ocred=lambda path, _texts: path.write_bytes(NEW_OCRED),
        write_pdic=save,
        expected_pdic_bytes=OLD_PDIC,
        expected_ocred_bytes=previous,
        expected_exported_ocred_bytes=NEW_OCRED,
    )


@pytest.mark.parametrize("previous", [None, OLD_OCRED])
def test_failed_pdic_writer_stages_r3_and_refuses_ocred_only_rollback(
    tmp_path, previous,
):
    pdic, ocred, marker = _paths(tmp_path, previous)
    save_error = OSError("injected PDIC writer failure")
    calls = []

    def save(*_args):
        calls.append("save")
        marker.write_bytes(b"pending R3 review")
        raise save_error

    with pytest.raises(RuntimeError, match="PDIC 保存失败且 R3") as caught:
        _publish(pdic, ocred, previous, save)

    assert calls == ["save"]
    assert caught.value.publication_error is save_error
    assert caught.value.__cause__ is caught.value.verification_error
    assert pdic.read_bytes() == OLD_PDIC
    assert ocred.read_bytes() == NEW_OCRED
    assert marker.read_bytes() == b"pending R3 review"
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, OLD_OCRED])
def test_successful_pdic_writer_leaving_r3_marker_cannot_report_clean_pair(
    tmp_path, previous,
):
    pdic, ocred, marker = _paths(tmp_path, previous)

    def save(*_args):
        pdic.write_bytes(NEW_PDIC)
        marker.write_bytes(b"pending R3 review")

    with pytest.raises(RuntimeError, match="R3 页面恢复事务"):
        _publish(pdic, ocred, previous, save)

    # The PDIC writer already committed. Neither sidecar may be rolled back
    # unilaterally while the R3 review transaction is unresolved.
    assert pdic.read_bytes() == NEW_PDIC
    assert ocred.read_bytes() == NEW_OCRED
    assert marker.read_bytes() == b"pending R3 review"
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, OLD_OCRED])
def test_r3_marker_appearing_during_rollback_staging_prevents_mutation(
    tmp_path, monkeypatch, previous,
):
    pdic, ocred, marker = _paths(tmp_path, previous)
    save_error = OSError("injected PDIC writer failure")
    real_guard = publication._reject_unresolved_r3_marker
    guard_calls = []

    def guard(path):
        guard_calls.append(True)
        # Startup, pre-PDIC writer, failed-writer verification, then the
        # callback immediately before OCRed rollback mutation.
        if len(guard_calls) == 4:
            marker.write_bytes(b"R3 appeared during compensation")
        return real_guard(path)

    monkeypatch.setattr(publication, "_reject_unresolved_r3_marker", guard)

    def save(*_args):
        raise save_error

    with pytest.raises(RuntimeError, match="PDIC 保存失败，OCRed 回滚也失败") as caught:
        _publish(pdic, ocred, previous, save)

    assert len(guard_calls) == 4
    assert caught.value.publication_error is save_error
    assert caught.value.__cause__ is caught.value.rollback_error
    assert "R3 页面恢复事务" in str(caught.value.rollback_error)
    assert pdic.read_bytes() == OLD_PDIC
    assert ocred.read_bytes() == NEW_OCRED
    assert marker.read_bytes() == b"R3 appeared during compensation"
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
