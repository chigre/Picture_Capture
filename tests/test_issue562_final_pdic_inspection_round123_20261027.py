"""Round 123: ambiguous final pre-commit PDIC reads must not undo OCRed.

The second page-context validator may be slow. A concurrent proofreader
can replace PDIC while it runs; if the final PDIC read then fails, the
worker cannot establish whether a one-sided OCRed rollback is safe.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.models import Entry
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr


@pytest.mark.parametrize("prior_ocred", [None, b"prior OCRed"], ids=["new", "existing"])
@pytest.mark.parametrize("pdic_changed", [False, True], ids=["unchanged", "edited"])
def test_unreadable_final_pdic_preserves_exported_ocred_and_current_pdic(
    tmp_path, monkeypatch, prior_ocred, pdic_changed,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(b"prior PDIC")
    if prior_ocred is not None:
        ocred.write_bytes(prior_ocred)

    original_read = Path.read_bytes
    pdic_reads = 0
    validations = 0
    writer_calls = []
    published = b"freshly exported OCRed"
    concurrent_pdic = b"manual PDIC replacement"

    def read_with_final_permission_error(self):
        nonlocal pdic_reads
        if self == pdic:
            pdic_reads += 1
            # Initial snapshot, post-first-validation check, post-export
            # inspection, then final check after the second validator.
            if pdic_reads == 4:
                raise PermissionError("PDIC locked during final inspection")
        return original_read(self)

    def validate_context():
        nonlocal validations
        validations += 1
        if validations == 2 and pdic_changed:
            pdic.write_bytes(concurrent_pdic)

    monkeypatch.setattr(Path, "read_bytes", read_with_final_permission_error)

    with pytest.raises(RuntimeError, match="拒绝单侧回滚 OCRed") as caught:
        publish_existing_pdic_ocr(
            ocred, pdic, ["recognized"], [Entry("recognized", 7, 19)],
            80, ("001", "@", "@"),
            export_ocred=lambda path, _texts: path.write_bytes(published),
            write_pdic=lambda *_args: writer_calls.append(True),
            expected_pdic_bytes=b"prior PDIC",
            expected_ocred_bytes=prior_ocred,
            expected_exported_ocred_bytes=published,
            validate_page_context=validate_context,
        )

    assert isinstance(caught.value.__cause__, PermissionError)
    assert pdic_reads == 4
    assert validations == 2
    assert writer_calls == []
    assert original_read(ocred) == published
    assert original_read(pdic) == (
        concurrent_pdic if pdic_changed else b"prior PDIC"
    )
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
