"""Round 130: a successful filesystem return is not proof of OCRed rollback.

A no-op adapter or a competing writer can leave the destination unchanged
(or changed again) even when replace/unlink does not raise. These tests use
real sidecar files and check that compensation never silently reports success.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


OLD = b"human proofread OCRed before batch"
EXPORTED = b"batch OCRed output"
FOREIGN = b"new concurrent human edit"
PDIC = b"unchanged original PDIC"


def _patch_mutation(monkeypatch, ocred: Path, operation: str, *, foreign: bool):
    if operation == "replace":
        original = publication.os.replace

        def replacement(source, destination):
            if foreign:
                original(source, destination)
                Path(destination).write_bytes(FOREIGN)
            # Otherwise simulate a no-op filesystem wrapper that returns
            # normally without moving the staging file.

        monkeypatch.setattr(publication.os, "replace", replacement)
    else:
        original = Path.unlink

        def deletion(path, *args, **kwargs):
            if path == ocred:
                if foreign:
                    original(path, *args, **kwargs)
                    path.write_bytes(FOREIGN)
                # Otherwise return without deleting the target.
                return None
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", deletion)


@pytest.mark.parametrize("operation", ["replace", "unlink"])
def test_normal_return_without_mutation_is_not_reported_as_rollback(
    tmp_path, monkeypatch, operation,
):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(EXPORTED)
    _patch_mutation(monkeypatch, ocred, operation, foreign=False)

    with pytest.raises(RuntimeError, match="函数已返回.*") as error:
        publication._restore_ocred_bytes(
            ocred, OLD if operation == "replace" else None,
            expected_current=EXPORTED,
        )
    assert "未确认回滚完成" in str(error.value)
    assert ocred.read_bytes() == EXPORTED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("operation", ["replace", "unlink"])
def test_foreign_edit_after_successful_mutation_is_not_hidden(
    tmp_path, monkeypatch, operation,
):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(EXPORTED)
    _patch_mutation(monkeypatch, ocred, operation, foreign=True)

    with pytest.raises(RuntimeError, match="函数已返回"):
        publication._restore_ocred_bytes(
            ocred, OLD if operation == "replace" else None,
            expected_current=EXPORTED,
        )
    assert ocred.read_bytes() == FOREIGN
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("operation", ["replace", "unlink"])
def test_pdic_save_error_does_not_mask_noop_rollback(
    tmp_path, monkeypatch, operation,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(PDIC)
    if operation == "replace":
        ocred.write_bytes(OLD)
    _patch_mutation(monkeypatch, ocred, operation, foreign=False)
    calls = []

    def export(path, _texts):
        calls.append("export")
        path.write_bytes(EXPORTED)

    def write(*_args):
        calls.append("pdic")
        raise OSError("PDIC save failure")

    with pytest.raises(RuntimeError, match="PDIC 保存失败，OCRed 回滚也失败") as error:
        publication.publish_existing_pdic_ocr(
            ocred, pdic, ["recognized"], [], 100, ("001", "@", "@"),
            export_ocred=export,
            write_pdic=write,
            expected_pdic_bytes=PDIC,
            expected_ocred_bytes=OLD if operation == "replace" else None,
            expected_exported_ocred_bytes=EXPORTED,
        )
    assert "PDIC save failure" in str(error.value)
    assert "未确认回滚完成" in str(error.value)
    assert calls == ["export", "pdic"]
    assert pdic.read_bytes() == PDIC
    assert ocred.read_bytes() == EXPORTED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
