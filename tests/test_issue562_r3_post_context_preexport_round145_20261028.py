"""Round 145: initial page provenance validation must not cross new R3 ownership.

A pending R3 recovery marker may be created while a slow SECTION/image
validator hashes a page or while the subsequent PDIC/OCRed snapshots are
rechecked. It must be detected before the first OCRed export, not only at
the later pre-PDIC writer checkpoint.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


PDIC_OLD = b"previous PDIC bytes"
OCRED_OLD = b"prior OCRed proofreading"
OCRED_NEW = b"batch OCRed result"


def _setup(tmp_path, old_ocred):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    marker = tmp_path / ".001.PDIC.r3-inflight.json"
    pdic.write_bytes(PDIC_OLD)
    if old_ocred is not None:
        ocred.write_bytes(old_ocred)
    return pdic, ocred, marker


def _publish(pdic, ocred, old_ocred, validate, calls):
    def export(path, _texts):
        calls.append("export")
        path.write_bytes(OCRED_NEW)

    def save(*_args):
        calls.append("pdic")

    publication.publish_existing_pdic_ocr(
        ocred, pdic, ["recognized"], [], 100, ("001", "@", "@"),
        export_ocred=export,
        write_pdic=save,
        expected_pdic_bytes=PDIC_OLD,
        expected_ocred_bytes=old_ocred,
        expected_exported_ocred_bytes=OCRED_NEW,
        validate_page_context=validate,
    )


@pytest.mark.parametrize("old_ocred", [None, OCRED_OLD])
@pytest.mark.parametrize("when", ["during_context", "during_snapshot_read"])
def test_r3_created_during_first_context_check_stops_export_without_mutations(
    tmp_path, monkeypatch, old_ocred, when,
):
    pdic, ocred, marker = _setup(tmp_path, old_ocred)
    calls = []
    validations = []
    original_read = Path.read_bytes

    def validate():
        validations.append(True)
        if when == "during_context":
            marker.write_bytes(b"R3 unfinished review transaction")

    def read_with_concurrent_r3(path):
        data = original_read(path)
        # The OCRed read following validation is the latest sidecar
        # snapshot before export. Do not depend on a brittle read count:
        # arm the injection after the provenance callback ran.
        if path == ocred and validations and when == "during_snapshot_read":
            marker.write_bytes(b"R3 began during sidecar revalidation")
        return data

    monkeypatch.setattr(Path, "read_bytes", read_with_concurrent_r3)

    with pytest.raises(RuntimeError, match="Unresolved R3 transaction") as caught:
        _publish(pdic, ocred, old_ocred, validate, calls)

    assert "拒绝批量 OCR 发布" in str(caught.value)
    assert calls == []
    assert validations == [True]
    assert original_read(pdic) == PDIC_OLD
    assert (original_read(ocred) if ocred.exists() else None) == old_ocred
    assert marker.exists()
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("old_ocred", [None, OCRED_OLD])
def test_r3_marker_status_unreadable_after_context_is_fail_closed(
    tmp_path, monkeypatch, old_ocred,
):
    pdic, ocred, marker = _setup(tmp_path, old_ocred)
    denied = PermissionError("R3 marker lstat permission denied")
    original_lstat = Path.lstat
    validations = []
    calls = []

    def validate():
        validations.append(True)

    def read_marker_status(path):
        if path == marker and validations:
            raise denied
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", read_marker_status)

    with pytest.raises(PermissionError) as caught:
        _publish(pdic, ocred, old_ocred, validate, calls)

    assert caught.value is denied
    assert calls == []
    assert validations == [True]
    assert pdic.read_bytes() == PDIC_OLD
    assert (ocred.read_bytes() if ocred.exists() else None) == old_ocred
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("old_ocred", [None, OCRED_OLD])
def test_no_marker_retains_context_validation_and_pdic_writer_order(
    tmp_path, old_ocred,
):
    pdic, ocred, marker = _setup(tmp_path, old_ocred)
    calls = []

    def validate():
        calls.append("validate")

    _publish(pdic, ocred, old_ocred, validate, calls)

    assert calls == ["validate", "export", "validate", "pdic", "validate"]
    assert pdic.read_bytes() == PDIC_OLD
    assert ocred.read_bytes() == OCRED_NEW
    assert not marker.exists()
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
