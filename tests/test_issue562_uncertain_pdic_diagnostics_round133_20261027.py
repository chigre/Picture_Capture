"""Round 133: preserve both failures when PDIC ownership cannot be read.

A failed OCRed export or PDIC writer may already have changed a sidecar.
An unreadable PDIC is not proof that a one-sided rollback is safe. The
raised exception must retain both error identities and avoid compensation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


@pytest.mark.parametrize("route", ["export", "pdic"])
@pytest.mark.parametrize("had_ocred", [False, True])
def test_unreadable_pdic_preserves_primary_and_verification_errors_without_rollback(
    tmp_path, monkeypatch, route, had_ocred,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    old_pdic = b"previous human-edited PDIC"
    old_ocred = b"previous proofread OCRed"
    exported_ocred = b"new OCRed"
    pdic.write_bytes(old_pdic)
    if had_ocred:
        ocred.write_bytes(old_ocred)

    primary = OSError(f"injected {route} publication failure")
    verification = PermissionError("injected PDIC ownership read denial")
    original_read = Path.read_bytes
    pdic_reads = [0]
    # Export failure: initial snapshot then failed-export ownership read.
    # PDIC save failure: initial snapshot, post-export read, then failed-save
    # ownership read. Earlier reads must remain real to reach each branch.
    fail_at = 2 if route == "export" else 3

    def read(path):
        if path == pdic:
            pdic_reads[0] += 1
            if pdic_reads[0] == fail_at:
                raise verification
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read)

    rollback_calls = []

    def forbidden_rollback(*_args, **_kwargs):
        rollback_calls.append("rollback")
        raise AssertionError("unreadable PDIC must not trigger OCRed-only rollback")

    monkeypatch.setattr(publication, "_restore_ocred_if_unchanged", forbidden_rollback)

    writes = []

    def export(path, _texts):
        path.write_bytes(exported_ocred)
        if route == "export":
            raise primary

    def write(*_args):
        writes.append("pdic")
        if route == "pdic":
            raise primary
        raise AssertionError("PDIC writer must not run after failed export")

    with pytest.raises(RuntimeError, match="拒绝单侧回滚|不执行仅 OCRed 回滚") as captured:
        publication.publish_existing_pdic_ocr(
            ocred, pdic, ["word"], [], 100, ("001", "@", "@"),
            export_ocred=export,
            write_pdic=write,
            expected_pdic_bytes=old_pdic,
            expected_ocred_bytes=old_ocred if had_ocred else None,
            expected_exported_ocred_bytes=exported_ocred,
        )

    failure = captured.value
    assert failure.publication_error is primary
    assert failure.verification_error is verification
    assert failure.__cause__ is verification
    assert pdic_reads == [fail_at]
    assert writes == (["pdic"] if route == "pdic" else [])
    assert rollback_calls == []
    assert original_read(pdic) == old_pdic
    assert original_read(ocred) == exported_ocred
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
