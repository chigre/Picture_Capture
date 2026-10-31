"""Round 135: unreadable OCRed at the last pre-PDIC ownership checkpoint.

The first post-export read may succeed while a later read, after checking
PDIC, fails. The worker must not commit PDIC or compensate an OCRed version
whose ownership can no longer be established.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


@pytest.mark.parametrize("had_ocred", [False, True])
@pytest.mark.parametrize("export_changed_ocred", [False, True])
def test_pre_pdic_unreadable_ocred_preserves_disk_and_verification_error(
    tmp_path, monkeypatch, had_ocred, export_changed_ocred,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    old_pdic = b"manual PDIC"
    old_ocred = b"proofread OCRed"
    exported_ocred = b"batch OCRed"
    pdic.write_bytes(old_pdic)
    if had_ocred:
        ocred.write_bytes(old_ocred)

    original_read = Path.read_bytes
    read_count = [0]
    verification_error = PermissionError("OCRed became unreadable before PDIC write")

    def read_bytes(path):
        if path == ocred:
            read_count[0] += 1
            # 1: pre-export snapshot, 2: post-export snapshot,
            # 3: after PDIC ownership check, immediately before writer.
            if read_count[0] == 3:
                raise verification_error
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    rollback_calls = []
    pdic_writes = []

    def forbidden_rollback(*_args, **_kwargs):
        rollback_calls.append(True)
        raise AssertionError("unverified OCRed must not be rolled back")

    monkeypatch.setattr(publication, "_restore_ocred_if_unchanged", forbidden_rollback)

    def export(path, _texts):
        if export_changed_ocred:
            path.write_bytes(exported_ocred)

    def write(*_args):
        pdic_writes.append(True)
        raise AssertionError("PDIC writer must not run after unreadable OCRed")

    with pytest.raises(
        RuntimeError, match="导出后、PDIC 保存前无法再次读取 OCRed",
    ) as captured:
        publication.publish_existing_pdic_ocr(
            ocred, pdic, ["word"], [], 100, ("001", "@", "@"),
            export_ocred=export,
            write_pdic=write,
            expected_pdic_bytes=old_pdic,
            expected_ocred_bytes=old_ocred if had_ocred else None,
            expected_exported_ocred_bytes=(
                exported_ocred if export_changed_ocred else None
            ),
        )

    failure = captured.value
    assert failure.verification_error is verification_error
    assert failure.__cause__ is verification_error
    assert read_count == [3]
    assert rollback_calls == []
    assert pdic_writes == []
    assert original_read(pdic) == old_pdic
    expected_ocred = (
        exported_ocred if export_changed_ocred
        else old_ocred if had_ocred else None
    )
    if expected_ocred is None:
        assert not ocred.exists()
    else:
        assert original_read(ocred) == expected_ocred
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
