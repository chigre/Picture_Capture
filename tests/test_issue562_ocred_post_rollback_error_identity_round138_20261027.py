"""Round 138: recovery tooling retains the exact PDIC verification error.

A compensating OCRed replace/delete may already be complete when the second
PDIC ownership check fails. Do not retry either write just to diagnose it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


OLD = b"prior human proofreading"
BATCH = b"published batch OCR"
PDIC = b"unchanged PDIC snapshot"


@pytest.mark.parametrize("previous", [None, OLD])
def test_post_compensation_verifier_error_has_identity_without_repeat_mutation(
    tmp_path, previous,
):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(BATCH)
    denied = PermissionError("PDIC could not be re-read after compensation")
    checks = []

    def verify_pdic():
        checks.append(True)
        if len(checks) == 2:
            assert (ocred.read_bytes() if ocred.exists() else None) == previous
            raise denied

    with pytest.raises(RuntimeError, match="回滚后 PDIC 版本") as caught:
        publication._restore_ocred_if_unchanged(
            ocred, previous, BATCH, verify_before_mutation=verify_pdic,
        )

    assert caught.value.verification_error is denied
    assert caught.value.__cause__ is denied
    assert len(checks) == 2
    assert (ocred.read_bytes() if ocred.exists() else None) == previous
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, OLD])
def test_pdic_save_failure_retains_original_and_post_compensation_error(
    tmp_path, monkeypatch, previous,
):
    ocred = tmp_path / "001.OCRed"
    pdic = tmp_path / "001.PDIC"
    pdic.write_bytes(PDIC)
    if previous is not None:
        ocred.write_bytes(previous)

    actual_read = Path.read_bytes
    saved = []
    denied = PermissionError("PDIC final ownership read denied")
    save_error = OSError("PDIC writer failed")
    read_faults = []

    def guarded_read(path):
        # Avoid a fragile hard-coded PDIC read count. This fault is injected
        # only after the failed writer and a visibly completed OCRed rollback.
        if path == pdic and saved and (
            (actual_read(ocred) if ocred.exists() else None) == previous
        ):
            read_faults.append(True)
            raise denied
        return actual_read(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)

    def export(path, _words):
        path.write_bytes(BATCH)

    def write(*_args):
        saved.append(True)
        raise save_error

    with pytest.raises(RuntimeError, match="PDIC 保存失败，OCRed 回滚也失败") as caught:
        publication.publish_existing_pdic_ocr(
            ocred, pdic, ["word"], [], 100, ("001", "@", "@"),
            export_ocred=export, write_pdic=write,
            expected_pdic_bytes=PDIC,
            expected_ocred_bytes=previous,
            expected_exported_ocred_bytes=BATCH,
        )

    rollback_error = caught.value.rollback_error
    assert caught.value.publication_error is save_error
    assert caught.value.__cause__ is rollback_error
    # The PDIC ownership callback intentionally adds a recovery message
    # around the underlying I/O exception. Preserve both object identities
    # across the final post-compensation wrapper, without flattening causes.
    assert rollback_error.__cause__ is rollback_error.verification_error
    assert rollback_error.verification_error.__cause__ is denied
    assert saved == [True]
    assert read_faults == [True]
    assert actual_read(pdic) == PDIC
    assert (actual_read(ocred) if ocred.exists() else None) == previous
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
