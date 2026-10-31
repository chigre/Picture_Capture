"""Round 140: preserve the original failure identity on ownership conflicts.

Conflicts are not permissions to reverse a newer PDIC or proofread OCRed.
Tests check exact original exceptions and unchanged foreign bytes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr


PDIC_OLD = b"marker snapshot"
PDIC_FOREIGN = b"manual PDIC edit"
OCRED_OLD = b"prior proofreading"
OCRED_PUBLISHED = b"batch recognized text"
OCRED_FOREIGN = b"human OCRed correction"


def _page(tmp_path):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(PDIC_OLD)
    ocred.write_bytes(OCRED_OLD)
    return pdic, ocred


def _publish(pdic, ocred, export, write):
    return publish_existing_pdic_ocr(
        ocred, pdic, ["recognized"], [], 100, ("001", "@", "@"),
        export_ocred=export,
        write_pdic=write,
        expected_pdic_bytes=PDIC_OLD,
        expected_ocred_bytes=OCRED_OLD,
        expected_exported_ocred_bytes=OCRED_PUBLISHED,
    )


@pytest.mark.parametrize("conflict", ["pdic_during_export", "foreign_ocred"])
def test_export_failure_conflict_preserves_original_error_and_manual_edits(
    tmp_path, conflict,
):
    pdic, ocred = _page(tmp_path)
    export_error = OSError("export failed after mutation")
    writes = []

    def export(path, _words):
        if conflict == "pdic_during_export":
            path.write_bytes(OCRED_PUBLISHED)
            pdic.write_bytes(PDIC_FOREIGN)
        else:
            path.write_bytes(OCRED_FOREIGN)
        raise export_error

    def save(*_args):
        writes.append(True)

    with pytest.raises(RuntimeError, match="OCRed 导出失败") as caught:
        _publish(pdic, ocred, export, save)

    assert caught.value.publication_error is export_error
    assert caught.value.__cause__ is export_error
    assert writes == []
    assert pdic.read_bytes() == (
        PDIC_FOREIGN if conflict == "pdic_during_export" else PDIC_OLD
    )
    assert ocred.read_bytes() == (
        OCRED_PUBLISHED if conflict == "pdic_during_export" else OCRED_FOREIGN
    )
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("conflict", ["read_denied", "pdic_edit"])
def test_export_failure_precompensation_pdic_conflict_preserves_diagnostics(
    tmp_path, monkeypatch, conflict,
):
    pdic, ocred = _page(tmp_path)
    original_read = Path.read_bytes
    pdic_read_count = []
    exported = []
    writes = []
    denied = PermissionError("PDIC verification denied")
    export_error = OSError("export callback failed")

    def inspect(path):
        if path == pdic:
            pdic_read_count.append(True)
            # One initial read, one immediately after the failed exporter,
            # and one just before the would-be OCRed compensation.
            if len(pdic_read_count) == 3:
                if conflict == "read_denied":
                    raise denied
                pdic.write_bytes(PDIC_FOREIGN)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", inspect)

    def export(path, _words):
        exported.append(True)
        path.write_bytes(OCRED_PUBLISHED)
        raise export_error

    def save(*_args):
        writes.append(True)

    with pytest.raises(RuntimeError, match="回滚前") as caught:
        _publish(pdic, ocred, export, save)

    assert caught.value.publication_error is export_error
    assert caught.value.__cause__ is (
        denied if conflict == "read_denied" else export_error
    )
    if conflict == "read_denied":
        assert caught.value.verification_error is denied
    assert len(pdic_read_count) == 3
    assert exported == [True] and writes == []
    assert original_read(pdic) == (
        PDIC_OLD if conflict == "read_denied" else PDIC_FOREIGN
    )
    assert original_read(ocred) == OCRED_PUBLISHED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


def test_pdic_writer_committed_then_raised_retains_writer_exception(tmp_path):
    pdic, ocred = _page(tmp_path)
    writer_error = OSError("PDIC writer raised after replacement")
    calls = []

    def export(path, _words):
        path.write_bytes(OCRED_PUBLISHED)

    def save(path, *_args):
        calls.append(True)
        path.write_bytes(PDIC_FOREIGN)
        raise writer_error

    with pytest.raises(RuntimeError, match="PDIC 保存报错，但磁盘 PDIC 已发生变化") as caught:
        _publish(pdic, ocred, export, save)

    assert caught.value.publication_error is writer_error
    assert caught.value.__cause__ is writer_error
    assert calls == [True]
    assert pdic.read_bytes() == PDIC_FOREIGN
    assert ocred.read_bytes() == OCRED_PUBLISHED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
