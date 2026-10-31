"""Round 136: a PDIC ownership callback must not invalidate OCRed rollback ownership.

The last PDIC check is an injected callable and may itself be slow or run
filesystem hooks. If OCRed changes inside that callback, compensation must
not overwrite or unlink the newly proofread sidecar.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


ORIGINAL = b"human OCRed before batch"
PUBLISHED = b"batch OCRed"
FOREIGN = b"new proofreader edit"
PDIC = b"original PDIC"


@pytest.mark.parametrize("previous", [None, ORIGINAL])
def test_pdic_callback_edits_ocred_before_rollback_mutation(tmp_path, previous):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(PUBLISHED)
    callbacks = []

    def verify_pdic():
        callbacks.append(True)
        ocred.write_bytes(FOREIGN)

    with pytest.raises(RuntimeError, match="PDIC 核验期间被其他操作修改"):
        publication._restore_ocred_bytes(
            ocred, previous, expected_current=PUBLISHED,
            verify_before_mutation=verify_pdic,
        )

    assert callbacks == [True]
    assert ocred.read_bytes() == FOREIGN
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, ORIGINAL])
def test_ocred_read_denied_after_pdic_callback_never_mutates(tmp_path, monkeypatch, previous):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(PUBLISHED)
    real_read = publication._read_optional_ocred_bytes
    reads = []
    denied = PermissionError("second OCRed ownership read denied")

    def read_with_denial(path):
        reads.append(True)
        if len(reads) == 2:
            raise denied
        return real_read(path)

    monkeypatch.setattr(publication, "_read_optional_ocred_bytes", read_with_denial)
    callbacks = []
    with pytest.raises(PermissionError) as error:
        publication._restore_ocred_bytes(
            ocred, previous, expected_current=PUBLISHED,
            verify_before_mutation=lambda: callbacks.append(True),
        )

    assert error.value is denied
    assert callbacks == [True]
    assert len(reads) == 2
    assert ocred.read_bytes() == PUBLISHED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, ORIGINAL])
def test_failed_pdic_save_callback_edits_ocred_no_unilateral_rollback(
    tmp_path, monkeypatch, previous,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(PDIC)
    if previous is not None:
        ocred.write_bytes(previous)

    original_read = Path.read_bytes
    pdic_reads = []
    injected = []

    def read_with_late_proofreading(path):
        if path == pdic:
            pdic_reads.append(True)
            # 1: initial PDIC snapshot, 2: after export,
            # 3: after failed PDIC save, 4: immediately before rollback.
            if len(pdic_reads) == 4:
                injected.append(True)
                ocred.write_bytes(FOREIGN)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_with_late_proofreading)
    pdic_error = OSError("PDIC writer rejected save")

    def export(path, _texts):
        path.write_bytes(PUBLISHED)

    def write(*_args):
        raise pdic_error

    with pytest.raises(RuntimeError, match="PDIC 保存失败，OCRed 回滚也失败") as error:
        publication.publish_existing_pdic_ocr(
            ocred, pdic, ["word"], [], 100, ("001", "@", "@"),
            export_ocred=export,
            write_pdic=write,
            expected_pdic_bytes=PDIC,
            expected_ocred_bytes=previous,
            expected_exported_ocred_bytes=PUBLISHED,
        )

    assert error.value.publication_error is pdic_error
    assert error.value.__cause__ is error.value.rollback_error
    assert "PDIC 核验期间被其他操作修改" in str(error.value.rollback_error)
    assert len(pdic_reads) == 4
    assert injected == [True]
    assert original_read(pdic) == PDIC
    assert original_read(ocred) == FOREIGN
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
