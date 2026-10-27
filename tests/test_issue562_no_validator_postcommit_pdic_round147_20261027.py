"""Round 147: even legacy no-validator callers must verify committed PDIC.

The OCRed/PDIC batch publisher already verifies the saved PDIC when a
SECTION/source-image validator is provided. Without that optional callback,
a writer which silently removes PDIC, or a later concurrent PDIC edit, used
to be reported as a clean OCRed+PDIC publication.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr


OLD_PDIC = b"original-pdic-manual-markers"
NEW_PDIC = b"batch-pdic-markers"
OLD_OCRED = b"original-ocred-proofread"
NEW_OCRED = b"batch-ocred"


def _case(tmp_path):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(OLD_PDIC)
    ocred.write_bytes(OLD_OCRED)
    return pdic, ocred


def _publish(pdic, ocred, state, *, save_action=None):
    def export(path, _texts):
        state["calls"].append("export")
        path.write_bytes(NEW_OCRED)

    def save(path, _entries, _width, _pages):
        state["calls"].append("pdic")
        if save_action is None:
            path.write_bytes(NEW_PDIC)
        else:
            save_action(path)
        state["saved"] = True

    publish_existing_pdic_ocr(
        ocred, pdic, ["word"], [], 800, ("001", "@", "@"),
        export_ocred=export, write_pdic=save,
        expected_pdic_bytes=OLD_PDIC,
        expected_ocred_bytes=OLD_OCRED,
        expected_exported_ocred_bytes=NEW_OCRED,
        validate_page_context=None,
    )


def test_no_validator_refuses_silent_pdic_removal(tmp_path):
    pdic, ocred = _case(tmp_path)
    state = {"calls": [], "saved": False}
    with pytest.raises(RuntimeError, match="PDIC 文件不存在"):
        _publish(pdic, ocred, state, save_action=lambda path: path.unlink())
    assert state == {"calls": ["export", "pdic"], "saved": True}
    assert not pdic.exists()
    assert ocred.read_bytes() == NEW_OCRED
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("read_number", [1, 2])
def test_no_validator_refuses_unreadable_committed_pdic(
    tmp_path, monkeypatch, read_number,
):
    pdic, ocred = _case(tmp_path)
    state = {"calls": [], "saved": False, "post_save_reads": 0}
    original_read = Path.read_bytes
    denied = PermissionError("injected PDIC post-commit read denial")

    def read_with_failure(path):
        if path == pdic and state["saved"]:
            state["post_save_reads"] += 1
            if state["post_save_reads"] == read_number:
                raise denied
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_with_failure)
    with pytest.raises(RuntimeError, match="无法再次读取 PDIC|无法核验提交后的 PDIC") as caught:
        _publish(pdic, ocred, state)
    assert caught.value.__cause__ is denied
    assert getattr(caught.value, "verification_error", None) is denied
    assert state["post_save_reads"] == read_number
    assert state["calls"] == ["export", "pdic"]
    assert original_read(pdic) == NEW_PDIC
    assert original_read(ocred) == NEW_OCRED


@pytest.mark.parametrize("mutation", ["replace", "delete"])
def test_no_validator_detects_pdic_change_during_postcommit_ocred_read(
    tmp_path, monkeypatch, mutation,
):
    pdic, ocred = _case(tmp_path)
    state = {"calls": [], "saved": False, "mutated": False}
    original_read = Path.read_bytes

    def read_with_concurrent_pdic_change(path):
        data = original_read(path)
        if path == ocred and state["saved"] and not state["mutated"]:
            state["mutated"] = True
            if mutation == "replace":
                pdic.write_bytes(b"other-window-manual-pdic")
            else:
                pdic.unlink()
        return data

    monkeypatch.setattr(Path, "read_bytes", read_with_concurrent_pdic_change)
    with pytest.raises(RuntimeError, match="PDIC 被其他操作修改") as caught:
        _publish(pdic, ocred, state)
    assert "未执行单侧回滚" in str(caught.value)
    assert state["mutated"]
    assert state["calls"] == ["export", "pdic"]
    assert original_read(ocred) == NEW_OCRED
    if mutation == "replace":
        assert original_read(pdic) == b"other-window-manual-pdic"
    else:
        assert not pdic.exists()


def test_no_validator_clean_publication_retains_legacy_callback_order(tmp_path):
    pdic, ocred = _case(tmp_path)
    state = {"calls": [], "saved": False}
    _publish(pdic, ocred, state)
    assert state == {"calls": ["export", "pdic"], "saved": True}
    assert pdic.read_bytes() == NEW_PDIC
    assert ocred.read_bytes() == NEW_OCRED
    assert not list(tmp_path.glob(".*.tmp"))
