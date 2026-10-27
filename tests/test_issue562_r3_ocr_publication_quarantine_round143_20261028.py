"""Round 143: batch OCR must not cross an unresolved R3 review transaction.

The R3 marker is scoped to the PDIC sidecar. Its presence must stop OCR
publication before exporting, and a marker created during an exporter or
page-context callback must prevent a later PDIC write or unsafe OCRed undo.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


OLD_PDIC = b"human PDIC snapshot"
OLD_OCRED = b"human OCRed snapshot"
NEW_OCRED = b"batch OCRed result"


def _setup(tmp_path, previous):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    marker = tmp_path / ".001.PDIC.r3-inflight.json"
    pdic.write_bytes(OLD_PDIC)
    if previous is not None:
        ocred.write_bytes(previous)
    return pdic, ocred, marker


def _publish(ocred, pdic, *, export, save, validate=None, previous=None):
    return publication.publish_existing_pdic_ocr(
        ocred, pdic, ["word"], [], 100, ("001", "@", "@"),
        export_ocred=export, write_pdic=save,
        expected_pdic_bytes=OLD_PDIC,
        expected_ocred_bytes=previous,
        expected_exported_ocred_bytes=NEW_OCRED,
        validate_page_context=validate,
    )


@pytest.mark.parametrize("previous", [None, OLD_OCRED])
@pytest.mark.parametrize("marker_type", ["file", "directory"])
def test_preexisting_r3_marker_blocks_export_before_any_disk_write(
    tmp_path, previous, marker_type,
):
    pdic, ocred, marker = _setup(tmp_path, previous)
    if marker_type == "file":
        marker.write_bytes(b"unresolved marker")
    else:
        marker.mkdir()
    calls = []

    with pytest.raises(RuntimeError, match="R3 页面恢复事务"):
        _publish(
            ocred, pdic, previous=previous,
            export=lambda *_args: calls.append("export"),
            save=lambda *_args: calls.append("pdic"),
        )
    assert calls == []
    assert pdic.read_bytes() == OLD_PDIC
    assert (ocred.read_bytes() if ocred.exists() else None) == previous
    assert marker.exists()
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, OLD_OCRED])
def test_marker_appears_during_successful_export_and_prevents_pdic_save(
    tmp_path, previous,
):
    pdic, ocred, marker = _setup(tmp_path, previous)
    calls = []

    def export(path, _texts):
        calls.append("export")
        path.write_bytes(NEW_OCRED)
        marker.write_bytes(b"new R3 transaction")

    with pytest.raises(RuntimeError, match="R3 页面恢复事务"):
        _publish(
            ocred, pdic, previous=previous, export=export,
            save=lambda *_args: calls.append("pdic"),
        )

    assert calls == ["export"]
    assert pdic.read_bytes() == OLD_PDIC
    assert ocred.read_bytes() == NEW_OCRED
    assert marker.read_bytes() == b"new R3 transaction"
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, OLD_OCRED])
def test_marker_during_failed_export_forbids_single_side_rollback_and_preserves_errors(
    tmp_path, previous,
):
    pdic, ocred, marker = _setup(tmp_path, previous)
    export_failure = OSError("export callback aborted")
    calls = []

    def export(path, _texts):
        calls.append("export")
        path.write_bytes(NEW_OCRED)
        marker.write_bytes(b"pending R3")
        raise export_failure

    with pytest.raises(RuntimeError, match="导出失败且 R3") as caught:
        _publish(
            ocred, pdic, previous=previous, export=export,
            save=lambda *_args: calls.append("pdic"),
        )

    assert caught.value.publication_error is export_failure
    assert caught.value.__cause__ is caught.value.verification_error
    assert calls == ["export"]
    assert pdic.read_bytes() == OLD_PDIC
    assert ocred.read_bytes() == NEW_OCRED
    assert marker.exists()
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, OLD_OCRED])
def test_marker_during_final_context_check_stops_custom_pdic_writer(
    tmp_path, previous,
):
    pdic, ocred, marker = _setup(tmp_path, previous)
    calls = []
    validations = []

    def export(path, _texts):
        calls.append("export")
        path.write_bytes(NEW_OCRED)

    def validate():
        validations.append(True)
        if len(validations) == 2:
            marker.write_bytes(b"pending R3 after context hashing")

    with pytest.raises(RuntimeError, match="R3 页面恢复事务"):
        _publish(
            ocred, pdic, previous=previous, export=export, validate=validate,
            save=lambda *_args: calls.append("pdic"),
        )

    assert validations == [True, True]
    assert calls == ["export"]
    assert pdic.read_bytes() == OLD_PDIC
    assert ocred.read_bytes() == NEW_OCRED
    assert marker.exists()
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, OLD_OCRED])
def test_no_r3_marker_preserves_legacy_publication_order(tmp_path, previous):
    pdic, ocred, marker = _setup(tmp_path, previous)
    calls = []

    def export(path, _texts):
        calls.append("export")
        path.write_bytes(NEW_OCRED)

    def save(*_args):
        calls.append("pdic")

    _publish(ocred, pdic, previous=previous, export=export, save=save)
    assert calls == ["export", "pdic"]
    assert pdic.read_bytes() == OLD_PDIC
    assert ocred.read_bytes() == NEW_OCRED
    assert not marker.exists()


def test_marker_read_permission_failure_blocks_publication_before_export(
    tmp_path, monkeypatch,
):
    pdic, ocred, marker = _setup(tmp_path, OLD_OCRED)
    denied = PermissionError("R3 marker status cannot be determined")
    original_lstat = Path.lstat
    calls = []

    def fail_marker_read(path):
        if path == marker:
            raise denied
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fail_marker_read)
    with pytest.raises(PermissionError) as caught:
        _publish(
            ocred, pdic, previous=OLD_OCRED,
            export=lambda *_args: calls.append("export"),
            save=lambda *_args: calls.append("pdic"),
        )

    assert caught.value is denied
    assert calls == []
    assert pdic.read_bytes() == OLD_PDIC
    assert ocred.read_bytes() == OLD_OCRED


def test_failed_export_and_unreadable_marker_retains_both_errors(
    tmp_path, monkeypatch,
):
    pdic, ocred, marker = _setup(tmp_path, OLD_OCRED)
    denied = PermissionError("R3 marker lstat denied after export")
    export_error = OSError("OCRed exporter failed")
    original_lstat = Path.lstat
    finished = []
    calls = []

    def delayed_denial(path):
        if path == marker and finished:
            raise denied
        return original_lstat(path)

    def export(path, _texts):
        path.write_bytes(NEW_OCRED)
        finished.append(True)
        raise export_error

    monkeypatch.setattr(Path, "lstat", delayed_denial)
    with pytest.raises(RuntimeError, match="导出失败且 R3") as caught:
        _publish(
            ocred, pdic, previous=OLD_OCRED,
            export=export, save=lambda *_args: calls.append("pdic"),
        )
    assert caught.value.publication_error is export_error
    assert caught.value.verification_error is denied
    assert caught.value.__cause__ is denied
    assert calls == []
    assert pdic.read_bytes() == OLD_PDIC
    assert ocred.read_bytes() == NEW_OCRED
    assert not marker.exists()
