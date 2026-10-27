"""Round 146: a late R3 journal cannot be mistaken for a clean OCRed/PDIC pair.

The earlier post-writer marker check does not cover the final OCRed read and
optional slow SECTION/source-image validation. The batch worker must refuse
to report success if R3 begins in that window, without rolling back either
already-published file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


OLD_PDIC = b"old-pdic-with-manual-edits"
NEW_PDIC = b"new-pdic-from-batch"
OLD_OCRED = b"old-ocred-proofreading"
NEW_OCRED = b"new-ocred-from-batch"


def _case(tmp_path):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    marker = tmp_path / ".001.PDIC.r3-inflight.json"
    pdic.write_bytes(OLD_PDIC)
    ocred.write_bytes(OLD_OCRED)
    return pdic, ocred, marker


def _run(pdic, ocred, state, *, validator):
    def export(path, _texts):
        state["calls"].append("export")
        path.write_bytes(NEW_OCRED)

    def save(path, _entries, _width, _pages):
        state["calls"].append("pdic")
        path.write_bytes(NEW_PDIC)
        state["saved"] = True

    def validate():
        state["validations"] += 1
        state["calls"].append("validate")
        hook = state.get("validate_hook")
        if hook is not None:
            hook(state["validations"])

    publication.publish_existing_pdic_ocr(
        ocred, pdic, ["new"], [], 100, ("001", "@", "@"),
        export_ocred=export, write_pdic=save,
        expected_pdic_bytes=OLD_PDIC,
        expected_ocred_bytes=OLD_OCRED,
        expected_exported_ocred_bytes=NEW_OCRED,
        validate_page_context=validate if validator else None,
    )


@pytest.mark.parametrize(
    "when,validator",
    [
        ("post_writer_ocred_read", False),
        ("post_writer_ocred_read", True),
        ("third_context", True),
        ("final_ocred_read", True),
        ("final_pdic_read", True),
    ],
)
def test_late_r3_marker_refuses_clean_success_after_commit(
    tmp_path, monkeypatch, when, validator,
):
    pdic, ocred, marker = _case(tmp_path)
    original_read = Path.read_bytes
    state = {"calls": [], "saved": False, "validations": 0, "post_ocred": False}

    def mark_r3():
        marker.write_bytes(b"unresolved R3 proofreading transaction")

    def validation_hook(number):
        if when == "third_context" and number == 3:
            mark_r3()

    state["validate_hook"] = validation_hook

    def read_with_r3(path):
        data = original_read(path)
        if state["saved"]:
            if path == ocred and not state["post_ocred"]:
                state["post_ocred"] = True
                if when == "post_writer_ocred_read":
                    mark_r3()
            elif validator and state["validations"] == 3:
                if when == "final_ocred_read" and path == ocred:
                    mark_r3()
                if when == "final_pdic_read" and path == pdic:
                    mark_r3()
        return data

    monkeypatch.setattr(Path, "read_bytes", read_with_r3)

    with pytest.raises(RuntimeError, match="Unresolved R3 transaction"):
        _run(pdic, ocred, state, validator=validator)

    assert state["saved"]
    assert state["calls"].count("pdic") == 1
    assert state["validations"] == (3 if validator else 0)
    assert original_read(pdic) == NEW_PDIC
    assert original_read(ocred) == NEW_OCRED
    assert original_read(marker) == b"unresolved R3 proofreading transaction"
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("validator", [False, True])
def test_late_marker_stat_permission_failure_is_not_success(
    tmp_path, monkeypatch, validator,
):
    pdic, ocred, marker = _case(tmp_path)
    original_read = Path.read_bytes
    original_lstat = Path.lstat
    denied = PermissionError("R3 marker status unreadable after OCRed commit")
    state = {"calls": [], "saved": False, "validations": 0, "post_ocred": False}

    def observe_post_commit_ocred(path):
        data = original_read(path)
        if state["saved"] and path == ocred:
            state["post_ocred"] = True
        return data

    def marker_lstat(path):
        if path == marker and state["post_ocred"]:
            raise denied
        return original_lstat(path)

    monkeypatch.setattr(Path, "read_bytes", observe_post_commit_ocred)
    monkeypatch.setattr(Path, "lstat", marker_lstat)

    with pytest.raises(PermissionError) as caught:
        _run(pdic, ocred, state, validator=validator)
    assert caught.value is denied
    assert state["saved"]
    assert state["calls"].count("pdic") == 1
    assert original_read(pdic) == NEW_PDIC
    assert original_read(ocred) == NEW_OCRED
    assert not marker.exists()
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("validator", [False, True])
def test_no_r3_marker_preserves_success_and_legacy_call_order(
    tmp_path, validator,
):
    pdic, ocred, marker = _case(tmp_path)
    state = {"calls": [], "saved": False, "validations": 0}
    _run(pdic, ocred, state, validator=validator)
    assert state["calls"] == (
        ["validate", "export", "validate", "pdic", "validate"]
        if validator else ["export", "pdic"]
    )
    assert pdic.read_bytes() == NEW_PDIC
    assert ocred.read_bytes() == NEW_OCRED
    assert not marker.exists()
