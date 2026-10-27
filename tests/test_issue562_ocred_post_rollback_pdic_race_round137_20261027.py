"""Round 137: post-rollback PDIC verification must not hide a later OCRed edit.

The final PDIC read is a callback that may be slow or invoke external hooks.
OCRed restoration/deletion may be complete before a proofreader publishes
new bytes during that read. Report the observed inconsistent pair without
overwriting the proofreader's version or attempting a second compensation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


ORIGINAL = b"human OCRed before batch"
PUBLISHED = b"batch OCRed"
FOREIGN = b"proofreader edit after rollback"
PDIC = b"original PDIC"


@pytest.mark.parametrize("previous", [None, ORIGINAL])
def test_post_rollback_pdic_callback_edits_ocred_and_preserves_edit(tmp_path, previous):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(PUBLISHED)
    calls = []

    def verify_pdic():
        calls.append(True)
        if len(calls) == 2:
            # The first callback precedes the destructive rollback;
            # the second runs after rollback has completed on disk.
            assert (ocred.read_bytes() if ocred.exists() else None) == previous
            ocred.write_bytes(FOREIGN)

    with pytest.raises(RuntimeError, match="回滚后 PDIC 核验期间 OCRed 再次被修改"):
        publication._restore_ocred_if_unchanged(
            ocred, previous, PUBLISHED, verify_before_mutation=verify_pdic,
        )

    assert len(calls) == 2
    assert ocred.read_bytes() == FOREIGN
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, ORIGINAL])
def test_post_rollback_ocred_read_denied_preserves_completed_compensation(
    tmp_path, monkeypatch, previous,
):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(PUBLISHED)
    actual_read = publication._read_optional_ocred_bytes
    calls = []
    reads = []
    denied = PermissionError("final OCRed read denied")

    def read_with_denial(path):
        reads.append(True)
        # Initial rollback ownership, after PDIC callback, after unlink/
        # replace, and finally after the post-rollback PDIC callback.
        if len(reads) == 4:
            raise denied
        return actual_read(path)

    monkeypatch.setattr(publication, "_read_optional_ocred_bytes", read_with_denial)

    with pytest.raises(RuntimeError, match="回滚后无法再次读取 OCRed") as error:
        publication._restore_ocred_if_unchanged(
            ocred, previous, PUBLISHED,
            verify_before_mutation=lambda: calls.append(True),
        )

    assert error.value.verification_error is denied
    assert error.value.__cause__ is denied
    assert len(calls) == 2
    assert len(reads) == 4
    assert (ocred.read_bytes() if ocred.exists() else None) == previous
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, ORIGINAL])
def test_failed_pdic_save_post_rollback_read_edits_ocred_without_second_rollback(
    tmp_path, monkeypatch, previous,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(PDIC)
    if previous is not None:
        ocred.write_bytes(previous)

    actual_read = Path.read_bytes
    pdic_reads = []
    injected = []
    writes = []
    pdic_error = OSError("PDIC save failed")

    def read_with_late_proofreading(path):
        if path == pdic:
            pdic_reads.append(True)
            # 1 initial; 2 after export; 3 after PDIC save failure;
            # 4 before compensation; 5 pre-mutation; 6 post-rollback.
            if len(pdic_reads) == 6:
                assert (actual_read(ocred) if ocred.exists() else None) == previous
                ocred.write_bytes(FOREIGN)
                injected.append(True)
        return actual_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_with_late_proofreading)

    def export(path, _texts):
        path.write_bytes(PUBLISHED)

    def write(*_args):
        writes.append(True)
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
    assert "回滚后 PDIC 核验期间 OCRed 再次被修改" in str(error.value.rollback_error)
    assert len(pdic_reads) == 6
    assert injected == [True]
    assert writes == [True]
    assert actual_read(pdic) == PDIC
    assert actual_read(ocred) == FOREIGN
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, ORIGINAL])
def test_post_rollback_pdic_callback_without_edit_preserves_normal_error(
    tmp_path, previous,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(PDIC)
    if previous is not None:
        ocred.write_bytes(previous)
    pdic_error = OSError("PDIC save failed")

    def export(path, _texts):
        path.write_bytes(PUBLISHED)

    def write(*_args):
        raise pdic_error

    with pytest.raises(OSError) as error:
        publication.publish_existing_pdic_ocr(
            ocred, pdic, ["word"], [], 100, ("001", "@", "@"),
            export_ocred=export,
            write_pdic=write,
            expected_pdic_bytes=PDIC,
            expected_ocred_bytes=previous,
            expected_exported_ocred_bytes=PUBLISHED,
        )

    assert error.value is pdic_error
    assert pdic.read_bytes() == PDIC
    assert (ocred.read_bytes() if ocred.exists() else None) == previous
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
