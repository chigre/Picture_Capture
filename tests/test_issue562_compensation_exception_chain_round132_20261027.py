"""Round 132: retain both failure objects when OCRed compensation is uncertain.

The caller must be able to distinguish the original export/SECTION/PDIC
failure from the later rollback or PDIC ownership failure. The rollback
failure is the immediate exception cause, not merely a string in a message.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


OLD_PDIC = b"old manually reviewed PDIC"
NEW_PDIC = b"concurrent PDIC edit"
OLD_OCRED = b"old proofread OCRed"
EXPORTED_OCRED = b"new OCRed from this batch"


@pytest.mark.parametrize("route", ["export", "section", "pdic"])
@pytest.mark.parametrize("operation", ["replace", "unlink"])
@pytest.mark.parametrize("fault", ["changed", "unreadable"])
def test_compensation_failure_keeps_original_and_rollback_exceptions(
    tmp_path, monkeypatch, route, operation, fault,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(OLD_PDIC)
    if operation == "replace":
        ocred.write_bytes(OLD_OCRED)

    original_replace = publication.os.replace
    original_unlink = Path.unlink
    original_read = Path.read_bytes
    operations = []
    deny_read = [False]

    def after_compensation():
        operations.append(operation)
        if fault == "changed":
            pdic.write_bytes(NEW_PDIC)
        else:
            deny_read[0] = True

    def replace(source, destination):
        original_replace(source, destination)
        if Path(destination) == ocred:
            after_compensation()

    def unlink(path, *args, **kwargs):
        result = original_unlink(path, *args, **kwargs)
        if path == ocred:
            after_compensation()
        return result

    def read(path):
        if path == pdic and deny_read[0]:
            raise PermissionError("injected late PDIC read failure")
        return original_read(path)

    monkeypatch.setattr(publication.os, "replace", replace)
    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(Path, "read_bytes", read)

    primary = {
        "export": OSError("original OCRed export error"),
        "section": ValueError("original SECTION validation error"),
        "pdic": OSError("original PDIC save error"),
    }[route]
    calls = []
    validations = []

    def export(path, _texts):
        calls.append("export")
        path.write_bytes(EXPORTED_OCRED)
        if route == "export":
            raise primary

    def validate():
        validations.append("section")
        if route == "section" and len(validations) == 2:
            raise primary

    def write(*_args):
        calls.append("pdic")
        if route == "pdic":
            raise primary
        raise AssertionError("PDIC write must not occur after SECTION/export failure")

    with pytest.raises(RuntimeError, match="回滚") as captured:
        publication.publish_existing_pdic_ocr(
            ocred, pdic, ["word"], [], 100, ("001", "@", "@"),
            export_ocred=export,
            write_pdic=write,
            expected_pdic_bytes=OLD_PDIC,
            expected_ocred_bytes=OLD_OCRED if operation == "replace" else None,
            expected_exported_ocred_bytes=EXPORTED_OCRED,
            validate_page_context=validate if route == "section" else None,
        )

    failure = captured.value
    assert failure.publication_error is primary
    assert isinstance(failure.rollback_error, RuntimeError)
    assert failure.__cause__ is failure.rollback_error
    assert "OCRed 回滚已完成，但回滚后 PDIC 版本" in str(failure.rollback_error)
    assert failure.rollback_error.__cause__ is not None
    assert operations == [operation]  # no repeated destructive compensation
    assert calls == (["export", "pdic"] if route == "pdic" else ["export"])
    assert original_read(pdic) == (NEW_PDIC if fault == "changed" else OLD_PDIC)
    if operation == "replace":
        assert original_read(ocred) == OLD_OCRED
    else:
        assert not ocred.exists()
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
