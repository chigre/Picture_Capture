"""PDIC ownership loss before commit must never trigger OCRed-only rollback.

The earlier optimistic rollback could replace a proofreader's matching OCRed
sidecar after a separate PDIC edit. These tests force both conflict windows,
including the case where OCRed was independently corrected in the same window.
"""
from __future__ import annotations

import pytest

from picture_capture.ocr import batch_publication

OLD_PDIC = b"original PDIC bytes"
MANUAL_PDIC = b"concurrent proofreader PDIC"
OLD_OCRED = b"proofread OCRed before batch"
EXPORTED_OCRED = b"new OCRed from batch"
MANUAL_OCRED = b"concurrent proofreader OCRed"


def _publish(pdic, ocred, previous, race, calls, *, edit_ocred=False):
    validations = []

    def validate():
        validations.append(True)
        if race == "validator" and len(validations) == 2:
            pdic.write_bytes(MANUAL_PDIC)
            if edit_ocred:
                ocred.write_bytes(MANUAL_OCRED)

    def exporter(path, _texts):
        calls.append("export")
        path.write_bytes(EXPORTED_OCRED)
        if race == "export":
            pdic.write_bytes(MANUAL_PDIC)

    def writer(*_args):
        calls.append("write")
        pdic.write_bytes(b"saved PDIC")

    batch_publication.publish_existing_pdic_ocr(
        ocred, pdic, ["new"], [], 100, ("001", "@", "@"),
        export_ocred=exporter,
        write_pdic=writer,
        expected_pdic_bytes=OLD_PDIC,
        expected_ocred_bytes=previous,
        expected_exported_ocred_bytes=EXPORTED_OCRED,
        validate_page_context=validate,
    )
    return validations


@pytest.mark.parametrize("previous", [None, OLD_OCRED], ids=["new", "existing"])
@pytest.mark.parametrize("race", ["export", "validator"])
def test_pdic_conflict_does_not_attempt_any_ocred_compensation(
    tmp_path, monkeypatch, previous, race,
):
    pdic, ocred = tmp_path / "001.PDIC", tmp_path / "001.OCRed"
    pdic.write_bytes(OLD_PDIC)
    if previous is not None:
        ocred.write_bytes(previous)
    calls = []

    def forbidden_rollback(*_args, **_kwargs):
        raise AssertionError("PDIC conflict must not start OCRed rollback")

    monkeypatch.setattr(
        batch_publication, "_restore_ocred_if_unchanged", forbidden_rollback,
    )
    expected = (
        "PDIC 在 OCRed 导出期间被其他操作修改"
        if race == "export"
        else "页面来源核验期间 PDIC 已被其他操作修改"
    )
    with pytest.raises(RuntimeError, match=expected) as error:
        _publish(pdic, ocred, previous, race, calls)
    assert "拒绝单侧回滚" in str(error.value)
    assert calls == ["export"]
    assert pdic.read_bytes() == MANUAL_PDIC
    assert ocred.read_bytes() == EXPORTED_OCRED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("previous", [None, OLD_OCRED], ids=["new", "existing"])
def test_pdic_and_ocred_both_proofread_during_validator_are_preserved(
    tmp_path, monkeypatch, previous,
):
    pdic, ocred = tmp_path / "001.PDIC", tmp_path / "001.OCRed"
    pdic.write_bytes(OLD_PDIC)
    if previous is not None:
        ocred.write_bytes(previous)
    calls = []

    def forbidden_rollback(*_args, **_kwargs):
        raise AssertionError("manual sidecars must not be rolled back")

    monkeypatch.setattr(
        batch_publication, "_restore_ocred_if_unchanged", forbidden_rollback,
    )
    with pytest.raises(RuntimeError, match="页面来源核验期间 PDIC 已被其他操作修改"):
        _publish(pdic, ocred, previous, "validator", calls, edit_ocred=True)
    assert calls == ["export"]
    assert pdic.read_bytes() == MANUAL_PDIC
    assert ocred.read_bytes() == MANUAL_OCRED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


def test_uncontended_validator_still_publishes_both_files(tmp_path):
    pdic, ocred = tmp_path / "001.PDIC", tmp_path / "001.OCRed"
    pdic.write_bytes(OLD_PDIC)
    ocred.write_bytes(OLD_OCRED)
    calls = []
    validations = _publish(pdic, ocred, OLD_OCRED, "none", calls)
    assert calls == ["export", "write"]
    assert len(validations) == 3
    assert pdic.read_bytes() == b"saved PDIC"
    assert ocred.read_bytes() == EXPORTED_OCRED
