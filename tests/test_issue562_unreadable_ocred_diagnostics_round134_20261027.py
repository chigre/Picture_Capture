"""Round 134: unreadable OCRed after exporter failure retains both errors.

The exporter may have committed OCRed before throwing. If the subsequent
OCRed ownership read fails, do not roll back an unverified sidecar or write
PDIC; preserve the exporter and verification exceptions for recovery.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


@pytest.mark.parametrize("had_ocred", [False, True])
@pytest.mark.parametrize("export_changed_ocred", [False, True])
def test_export_failure_unreadable_ocred_keeps_both_errors_and_disk_bytes(
    tmp_path, monkeypatch, had_ocred, export_changed_ocred,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    old_pdic = b"human PDIC"
    old_ocred = b"human OCRed"
    new_ocred = b"newly exported OCRed"
    pdic.write_bytes(old_pdic)
    if had_ocred:
        ocred.write_bytes(old_ocred)

    export_error = OSError("exporter raised after optional write")
    read_error = PermissionError("OCRed ownership read denied")
    original_read = Path.read_bytes
    ocred_reads = [0]

    def read_bytes(path):
        if path == ocred:
            ocred_reads[0] += 1
            if ocred_reads[0] == 2:
                raise read_error
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    rollback_calls = []
    pdic_writes = []

    def forbidden_rollback(*args, **kwargs):
        rollback_calls.append(True)
        raise AssertionError("unreadable OCRed must not be rolled back")

    monkeypatch.setattr(publication, "_restore_ocred_if_unchanged", forbidden_rollback)

    def export(path, _texts):
        if export_changed_ocred:
            path.write_bytes(new_ocred)
        raise export_error

    def write(*args):
        pdic_writes.append(True)
        raise AssertionError("PDIC writer must not run after failed export")

    with pytest.raises(RuntimeError, match="OCRed 导出报错，且无法核验 OCRed") as captured:
        publication.publish_existing_pdic_ocr(
            ocred, pdic, ["word"], [], 100, ("001", "@", "@"),
            export_ocred=export,
            write_pdic=write,
            expected_pdic_bytes=old_pdic,
            expected_ocred_bytes=old_ocred if had_ocred else None,
            expected_exported_ocred_bytes=new_ocred,
        )

    failure = captured.value
    assert failure.publication_error is export_error
    assert failure.verification_error is read_error
    assert failure.__cause__ is read_error
    assert ocred_reads == [2]
    assert rollback_calls == []
    assert pdic_writes == []
    assert original_read(pdic) == old_pdic
    expected_ocred = new_ocred if export_changed_ocred else (
        old_ocred if had_ocred else None
    )
    if expected_ocred is None:
        assert not ocred.exists()
    else:
        assert original_read(ocred) == expected_ocred
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
