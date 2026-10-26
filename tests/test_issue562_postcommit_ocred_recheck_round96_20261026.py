"""Round 96: detect OCRed edits made during the final source-image check.

PDIC is already committed when the third page-context verification runs.
Conflicts are reported without reverting PDIC or clobbering manual OCRed edits.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import export_ocred, render_ocred_bytes


def _files(tmp_path):
    pdic = tmp_path / "001.PDIC"
    write_pdic(pdic, [Entry("before", 17, 43)], 100, ("001", "@", "@"))
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"\xef\xbb\xbf000|`proofread-before\r\n")
    return pdic, ocred


def _publish(pdic, ocred, verify):
    publish_existing_pdic_ocr(
        ocred, pdic, ["recognized"], [Entry("recognized", 17, 43)],
        100, ("001", "@", "@"),
        export_ocred=export_ocred, write_pdic=write_pdic,
        expected_exported_ocred_bytes=render_ocred_bytes(["recognized"]),
        validate_page_context=verify,
    )


@pytest.mark.parametrize("change", ["replace", "delete"])
def test_postcommit_context_check_detects_late_manual_ocred_change(
    tmp_path, change,
):
    pdic, ocred = _files(tmp_path)
    calls = []
    manual_bytes = b"\xef\xbb\xbf000|`late-manual\r\n"

    def verify():
        calls.append("source-check")
        if len(calls) == 3:
            if change == "replace":
                ocred.write_bytes(manual_bytes)
            else:
                ocred.unlink()

    with pytest.raises(RuntimeError, match="页面来源核验期间 OCRed"):
        _publish(pdic, ocred, verify)
    assert len(calls) == 3
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("recognized", 17, 43)
    ]
    if change == "replace":
        assert ocred.read_bytes() == manual_bytes
    else:
        assert not ocred.exists()
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


def test_postcommit_ocred_recheck_read_failure_does_not_rollback(
    tmp_path, monkeypatch,
):
    pdic, ocred = _files(tmp_path)
    calls = []
    original_read = Path.read_bytes

    def verify():
        calls.append("source-check")

    def read_with_fault(path):
        if path == ocred and len(calls) == 3:
            raise PermissionError("late OCRed read denied")
        return original_read(path)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", read_with_fault)
        with pytest.raises(RuntimeError, match="无法再次读取 OCRed") as exc:
            _publish(pdic, ocred, verify)
    assert "late OCRed read denied" in str(exc.value)
    assert len(calls) == 3
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("recognized", 17, 43)
    ]
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])


def test_uncontended_postcommit_ocred_recheck_preserves_xy_and_text(tmp_path):
    pdic, ocred = _files(tmp_path)
    calls = []
    _publish(pdic, ocred, lambda: calls.append("source-check"))
    assert calls == ["source-check"] * 3
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("recognized", 17, 43)
    ]
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
