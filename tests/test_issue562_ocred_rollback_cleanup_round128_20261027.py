"""Round 128: rollback cleanup failures must not hide the original failure.

An OCRed rollback may fail while staging, checking ownership or replacing
the published sidecar. If removing the staged .tmp also fails, both errors
must be visible and the existing OCRed/PDIC files must be left untouched.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication

OLD_OCRED = b"human-proofread OCRed"
NEW_OCRED = b"newly exported OCRed"
OLD_PDIC = b"human-proofread PDIC"


def _fail_rollback_temp_cleanup(monkeypatch):
    original_unlink = Path.unlink
    attempts = []

    def unlink(path, *args, **kwargs):
        if path.name.startswith(".001.OCRed.") and path.suffix == ".tmp":
            attempts.append(path)
            raise PermissionError("injected temp cleanup denied")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    return attempts


@pytest.mark.parametrize("fault", ["replace", "fsync", "ownership"])
def test_rollback_and_cleanup_failures_preserve_both_errors_and_sidecar(
    tmp_path, monkeypatch, fault,
):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(NEW_OCRED)
    cleanup_attempts = _fail_rollback_temp_cleanup(monkeypatch)

    if fault == "replace":
        def fail_replace(*_args):
            raise OSError("injected rollback replace failure")

        monkeypatch.setattr(publication.os, "replace", fail_replace)
        verify = None
    elif fault == "fsync":
        def fail_fsync(_fd):
            raise OSError("injected rollback fsync failure")

        monkeypatch.setattr(publication.os, "fsync", fail_fsync)
        verify = None
    else:
        def verify():
            raise RuntimeError("injected PDIC ownership conflict")

    with pytest.raises(RuntimeError, match="临时文件清理失败") as error:
        publication._restore_ocred_bytes(
            ocred, OLD_OCRED, expected_current=NEW_OCRED,
            verify_before_mutation=verify,
        )
    assert "injected temp cleanup denied" in str(error.value)
    assert isinstance(error.value.__cause__, (OSError, RuntimeError))
    expected_original = {
        "replace": "injected rollback replace failure",
        "fsync": "injected rollback fsync failure",
        "ownership": "injected PDIC ownership conflict",
    }[fault]
    assert expected_original in str(error.value.__cause__)
    assert ocred.read_bytes() == NEW_OCRED
    assert len(cleanup_attempts) == 1
    assert cleanup_attempts[0].exists()
    assert len(list(tmp_path.glob(".001.OCRed.*.tmp"))) == 1


def test_successful_rollback_never_cleans_up_moved_temp(tmp_path, monkeypatch):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(NEW_OCRED)
    cleanup_attempts = _fail_rollback_temp_cleanup(monkeypatch)

    publication._restore_ocred_bytes(
        ocred, OLD_OCRED, expected_current=NEW_OCRED,
    )
    assert ocred.read_bytes() == OLD_OCRED
    assert cleanup_attempts == []
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


def test_pdic_save_failure_reports_both_rollback_and_cleanup_failures(
    tmp_path, monkeypatch,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(OLD_PDIC)
    ocred.write_bytes(OLD_OCRED)
    cleanup_attempts = _fail_rollback_temp_cleanup(monkeypatch)
    calls = []

    def export(path, _texts):
        calls.append("export")
        path.write_bytes(NEW_OCRED)

    def fail_pdic(*_args):
        calls.append("pdic")
        raise OSError("injected PDIC save failure")

    def fail_replace(*_args):
        raise OSError("injected OCRed rollback replace failure")

    monkeypatch.setattr(publication.os, "replace", fail_replace)
    with pytest.raises(RuntimeError, match="PDIC 保存失败，OCRed 回滚也失败") as error:
        publication.publish_existing_pdic_ocr(
            ocred, pdic, ["recognized"], [], 100, ("001", "@", "@"),
            export_ocred=export,
            write_pdic=fail_pdic,
            expected_pdic_bytes=OLD_PDIC,
            expected_ocred_bytes=OLD_OCRED,
            expected_exported_ocred_bytes=NEW_OCRED,
        )

    assert calls == ["export", "pdic"]
    assert "injected PDIC save failure" in str(error.value)
    assert "injected OCRed rollback replace failure" in str(error.value)
    assert "injected temp cleanup denied" in str(error.value)
    assert isinstance(error.value.__cause__, RuntimeError)
    assert isinstance(error.value.__cause__.__cause__, OSError)
    assert pdic.read_bytes() == OLD_PDIC
    assert ocred.read_bytes() == NEW_OCRED
    assert len(cleanup_attempts) == 1
    assert cleanup_attempts[0].exists()
