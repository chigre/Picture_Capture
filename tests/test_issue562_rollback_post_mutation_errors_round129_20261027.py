"""Round 129: a filesystem hook may mutate OCRed and then raise.

A post-mutation exception is not proof that replace/unlink failed. Verify the
visible state without repeating a destructive operation or losing the
original PDIC/export failure. All tests use actual temporary sidecar files.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


OLD = b"previously proofread OCRed"
EXPORTED = b"newly recognized OCRed"
PDIC = b"original PDIC"


def _inject_mutation_error(monkeypatch, operation, *, after, extra_edit=None):
    if operation == "replace":
        original = publication.os.replace

        def replacement(source, destination):
            if after:
                original(source, destination)
                if extra_edit is not None:
                    Path(destination).write_bytes(extra_edit)
            raise OSError("injected replace callback error")

        monkeypatch.setattr(publication.os, "replace", replacement)
    else:
        original = Path.unlink

        def deletion(path, *args, **kwargs):
            if path.name == "001.OCRed":
                if after:
                    original(path, *args, **kwargs)
                    if extra_edit is not None:
                        path.write_bytes(extra_edit)
                raise OSError("injected unlink callback error")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", deletion)


@pytest.mark.parametrize("operation", ["replace", "unlink"])
def test_completed_mutation_followed_by_exception_is_recognized(
    tmp_path, monkeypatch, operation,
):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(EXPORTED)
    _inject_mutation_error(monkeypatch, operation, after=True)
    publication._restore_ocred_bytes(
        ocred, OLD if operation == "replace" else None,
        expected_current=EXPORTED,
    )
    if operation == "replace":
        assert ocred.read_bytes() == OLD
    else:
        assert not ocred.exists()
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("operation", ["replace", "unlink"])
def test_exception_before_mutation_is_not_mistaken_for_success(
    tmp_path, monkeypatch, operation,
):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(EXPORTED)
    _inject_mutation_error(monkeypatch, operation, after=False)
    with pytest.raises(OSError, match=f"injected {operation} callback error"):
        publication._restore_ocred_bytes(
            ocred, OLD if operation == "replace" else None,
            expected_current=EXPORTED,
        )
    assert ocred.read_bytes() == EXPORTED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("operation", ["replace", "unlink"])
def test_concurrent_edit_after_mutation_error_is_not_overwritten(
    tmp_path, monkeypatch, operation,
):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(EXPORTED)
    human_edit = b"new human correction"
    _inject_mutation_error(
        monkeypatch, operation, after=True, extra_edit=human_edit,
    )
    with pytest.raises(OSError, match=f"injected {operation} callback error"):
        publication._restore_ocred_bytes(
            ocred, OLD if operation == "replace" else None,
            expected_current=EXPORTED,
        )
    assert ocred.read_bytes() == human_edit
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("operation", ["replace", "unlink"])
def test_post_mutation_inspection_error_reports_uncertain_state(
    tmp_path, monkeypatch, operation,
):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(EXPORTED)
    original_read = Path.read_bytes
    mutated = [False]

    if operation == "replace":
        original_replace = publication.os.replace

        def replace_then_raise(source, destination):
            original_replace(source, destination)
            mutated[0] = True
            raise OSError("replace after commit")

        monkeypatch.setattr(publication.os, "replace", replace_then_raise)
    else:
        original_unlink = Path.unlink

        def unlink_then_raise(path, *args, **kwargs):
            if path == ocred:
                original_unlink(path, *args, **kwargs)
                mutated[0] = True
                raise OSError("unlink after commit")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", unlink_then_raise)

    def unreadable_after_mutation(path):
        if path == ocred and mutated[0]:
            raise PermissionError("injected inspection denied")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", unreadable_after_mutation)
    with pytest.raises(RuntimeError, match="无法确认.*是否完成") as error:
        publication._restore_ocred_bytes(
            ocred, OLD if operation == "replace" else None,
            expected_current=EXPORTED,
        )
    assert isinstance(error.value.__cause__, OSError)
    assert mutated[0]
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
    if operation == "replace":
        assert original_read(ocred) == OLD
    else:
        assert not ocred.exists()


@pytest.mark.parametrize("operation", ["replace", "unlink"])
def test_pdic_save_error_remains_primary_when_ocred_rollback_committed(
    tmp_path, monkeypatch, operation,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(PDIC)
    if operation == "replace":
        ocred.write_bytes(OLD)
    _inject_mutation_error(monkeypatch, operation, after=True)
    calls = []

    def export(path, _texts):
        calls.append("export")
        path.write_bytes(EXPORTED)

    def write(*_args):
        calls.append("pdic")
        raise OSError("injected PDIC save failure")

    with pytest.raises(OSError, match="injected PDIC save failure"):
        publication.publish_existing_pdic_ocr(
            ocred, pdic, ["recognized"], [], 100, ("001", "@", "@"),
            export_ocred=export,
            write_pdic=write,
            expected_pdic_bytes=PDIC,
            expected_ocred_bytes=OLD if operation == "replace" else None,
            expected_exported_ocred_bytes=EXPORTED,
        )
    assert calls == ["export", "pdic"]
    assert pdic.read_bytes() == PDIC
    if operation == "replace":
        assert ocred.read_bytes() == OLD
    else:
        assert not ocred.exists()
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
