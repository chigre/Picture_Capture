"""Failed OCRed export must not compensate after PDIC changes during staging.

Faults are injected *after* the pre-compensation PDIC read, at the last
OCRed rollback stage, rather than during the exporter itself.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr


ORIGINAL_PDIC = b"PDIC before export"
MANUAL_PDIC = b"PDIC edited while compensating"
ORIGINAL_OCRED = b"proofread OCRed before export"
EXPORTED_OCRED = b"partially committed OCRed"


def _run_failed_export(pdic, ocred, previous, writer_calls):
    def export_then_fail(path, _texts):
        path.write_bytes(EXPORTED_OCRED)
        raise OSError("injected exporter failure")

    return publish_existing_pdic_ocr(
        ocred, pdic, ["recognized"], [], 100, ("001", "@", "@"),
        export_ocred=export_then_fail,
        write_pdic=lambda *_args: writer_calls.append(True),
        expected_pdic_bytes=ORIGINAL_PDIC,
        expected_ocred_bytes=previous,
        expected_exported_ocred_bytes=EXPORTED_OCRED,
    )


@pytest.mark.parametrize("previous", [None, ORIGINAL_OCRED], ids=["new-ocred", "old-ocred"])
def test_pdic_edit_during_failed_export_rollback_stage_preserves_both(
    tmp_path, monkeypatch, previous,
):
    pdic, ocred = tmp_path / "001.PDIC", tmp_path / "001.OCRed"
    pdic.write_bytes(ORIGINAL_PDIC)
    if previous is not None:
        ocred.write_bytes(previous)
    writer_calls = []
    original_read = Path.read_bytes

    if previous is None:
        # The delete compensation has no temp/fsync stage. Inject after
        # the third PDIC inspection, during the final OCRed ownership read
        # immediately before unlink would otherwise remove the new file.
        ocred_reads = 0

        def edit_during_last_ocred_read(path):
            nonlocal ocred_reads
            if path == ocred:
                ocred_reads += 1
                if ocred_reads == 4:
                    pdic.write_bytes(MANUAL_PDIC)
            return original_read(path)

        monkeypatch.setattr(Path, "read_bytes", edit_during_last_ocred_read)
    else:
        # Staging a byte-exact old OCRed uses fsync. A manual PDIC edit
        # during that fsync must prevent the subsequent os.replace.
        real_fsync = batch_publication.os.fsync

        def edit_during_fsync(fd):
            real_fsync(fd)
            pdic.write_bytes(MANUAL_PDIC)

        monkeypatch.setattr(batch_publication.os, "fsync", edit_during_fsync)

    with pytest.raises(RuntimeError, match="回滚暂存期间 PDIC 已被其他操作修改"):
        _run_failed_export(pdic, ocred, previous, writer_calls)

    assert original_read(pdic) == MANUAL_PDIC
    assert original_read(ocred) == EXPORTED_OCRED
    assert writer_calls == []
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, ORIGINAL_OCRED], ids=["new-ocred", "old-ocred"])
def test_pdic_unreadable_at_failed_export_rollback_mutation_preserves_ocred(
    tmp_path, monkeypatch, previous,
):
    pdic, ocred = tmp_path / "001.PDIC", tmp_path / "001.OCRed"
    pdic.write_bytes(ORIGINAL_PDIC)
    if previous is not None:
        ocred.write_bytes(previous)
    original_read = Path.read_bytes
    pdic_reads = 0
    writer_calls = []

    def fail_fourth_pdic_read(path):
        nonlocal pdic_reads
        if path == pdic:
            pdic_reads += 1
            if pdic_reads == 4:
                raise PermissionError("injected late PDIC read error")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", fail_fourth_pdic_read)
    with pytest.raises(RuntimeError, match="回滚写入前无法再次核验 PDIC"):
        _run_failed_export(pdic, ocred, previous, writer_calls)

    assert pdic_reads == 4
    assert original_read(pdic) == ORIGINAL_PDIC
    assert original_read(ocred) == EXPORTED_OCRED
    assert writer_calls == []
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, ORIGINAL_OCRED], ids=["new-ocred", "old-ocred"])
def test_failed_export_uncontended_compensation_still_restores_exact_bytes(
    tmp_path, previous,
):
    pdic, ocred = tmp_path / "001.PDIC", tmp_path / "001.OCRed"
    pdic.write_bytes(ORIGINAL_PDIC)
    if previous is not None:
        ocred.write_bytes(previous)
    writer_calls = []

    with pytest.raises(OSError, match="injected exporter failure"):
        _run_failed_export(pdic, ocred, previous, writer_calls)

    assert pdic.read_bytes() == ORIGINAL_PDIC
    assert (ocred.read_bytes() if ocred.exists() else None) == previous
    assert writer_calls == []
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
