"""Round 131: OCRed compensation does not prove the PDIC pair is still owned.

A filesystem callback can complete OCRed replacement/deletion and then
change PDIC (or make it unreadable) before returning. Exercise all three
publication failure paths with real sidecar files and injected late faults.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


OLD_PDIC = b"original manually proofread PDIC"
FOREIGN_PDIC = b"newer PDIC from another process"
OLD_OCRED = b"previously proofread OCRed"
EXPORTED = b"freshly exported OCRed"


@pytest.mark.parametrize("route", ["pdic_failure", "export_failure", "context_failure"])
@pytest.mark.parametrize("operation", ["replace", "unlink"])
@pytest.mark.parametrize("fault", ["pdic_changed", "pdic_unreadable"])
def test_post_compensation_pdic_conflict_is_reported_without_second_mutation(
    tmp_path, monkeypatch, route, operation, fault,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(OLD_PDIC)
    if operation == "replace":
        ocred.write_bytes(OLD_OCRED)

    original_read = Path.read_bytes
    original_replace = publication.os.replace
    original_unlink = Path.unlink
    mutated = []
    unreadable = [False]

    def after_ocred_compensation():
        mutated.append(operation)
        if fault == "pdic_changed":
            pdic.write_bytes(FOREIGN_PDIC)
        else:
            unreadable[0] = True

    def replacement(source, destination):
        original_replace(source, destination)
        if Path(destination) == ocred:
            after_ocred_compensation()

    def deletion(path, *args, **kwargs):
        result = original_unlink(path, *args, **kwargs)
        if path == ocred:
            after_ocred_compensation()
        return result

    def guarded_read(path):
        if path == pdic and unreadable[0]:
            raise PermissionError("injected PDIC post-rollback read denial")
        return original_read(path)

    monkeypatch.setattr(publication.os, "replace", replacement)
    monkeypatch.setattr(Path, "unlink", deletion)
    monkeypatch.setattr(Path, "read_bytes", guarded_read)

    calls = []
    context_calls = []

    def export(path, _texts):
        calls.append("export")
        path.write_bytes(EXPORTED)
        if route == "export_failure":
            raise OSError("injected export failure")

    def write(*_args):
        calls.append("pdic")
        raise OSError("injected PDIC save failure")

    def context():
        context_calls.append("validate")
        if route == "context_failure" and len(context_calls) == 2:
            raise RuntimeError("injected SECTION source conflict")

    expected_message = {
        "pdic_failure": "PDIC 保存失败，OCRed 回滚也失败",
        "export_failure": "OCRed 导出失败，且原文件回滚也失败",
        "context_failure": "SECTION 发布前核验失败，且 OCRed 回滚失败",
    }[route]
    with pytest.raises(RuntimeError, match=expected_message) as error:
        publication.publish_existing_pdic_ocr(
            ocred, pdic, ["recognized"], [], 100, ("001", "@", "@"),
            export_ocred=export,
            write_pdic=write,
            expected_pdic_bytes=OLD_PDIC,
            expected_ocred_bytes=OLD_OCRED if operation == "replace" else None,
            expected_exported_ocred_bytes=EXPORTED,
            validate_page_context=context if route == "context_failure" else None,
        )

    assert "OCRed 回滚已完成，但回滚后 PDIC 版本" in str(error.value)
    assert mutated == [operation]  # never retry a destructive rollback
    assert calls == (["export", "pdic"] if route == "pdic_failure" else ["export"])
    assert original_read(pdic) == (
        FOREIGN_PDIC if fault == "pdic_changed" else OLD_PDIC
    )
    if operation == "replace":
        assert original_read(ocred) == OLD_OCRED
    else:
        assert not ocred.exists()
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("operation", ["replace", "unlink"])
def test_successful_compensation_checks_pdic_before_and_after(tmp_path, operation):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(EXPORTED)
    observations = []

    def verify():
        observations.append("PDIC unchanged")

    publication._restore_ocred_if_unchanged(
        ocred,
        OLD_OCRED if operation == "replace" else None,
        EXPORTED,
        verify_before_mutation=verify,
    )
    assert observations == ["PDIC unchanged", "PDIC unchanged"]
    if operation == "replace":
        assert ocred.read_bytes() == OLD_OCRED
    else:
        assert not ocred.exists()


def test_noop_compensation_does_not_touch_or_recheck_other_side(tmp_path):
    ocred = tmp_path / "001.OCRed"
    ocred.write_bytes(OLD_OCRED)

    def unexpected_verify():
        raise AssertionError("No mutation means no compensation ownership check")

    publication._restore_ocred_if_unchanged(
        ocred, OLD_OCRED, OLD_OCRED,
        verify_before_mutation=unexpected_verify,
    )
    assert ocred.read_bytes() == OLD_OCRED
