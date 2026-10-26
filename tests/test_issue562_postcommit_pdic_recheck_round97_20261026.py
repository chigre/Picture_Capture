"""Round 97: post-commit PDIC conflict detection during slow source hashing."""
from pathlib import Path

import pytest

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import export_ocred, render_ocred_bytes


def _setup(tmp_path):
    pdic = tmp_path / "001.PDIC"
    write_pdic(pdic, [Entry("old", 17, 43)], 100, ("001", "@", "@"))
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"\\xef\\xbb\\xbf000|\\x60manual-before\\r\\n")
    return pdic, ocred


def _publish(pdic, ocred, check, writer=write_pdic):
    publish_existing_pdic_ocr(
        ocred, pdic, ["recognized"], [Entry("recognized", 17, 43)],
        100, ("001", "@", "@"),
        export_ocred=export_ocred, write_pdic=writer,
        expected_exported_ocred_bytes=render_ocred_bytes(["recognized"]),
        validate_page_context=check,
    )


@pytest.mark.parametrize("change", ["replace", "delete"])
def test_late_pdic_edit_is_preserved_and_reported(tmp_path, change):
    pdic, ocred = _setup(tmp_path)
    calls = []
    def check():
        calls.append("check")
        if len(calls) == 3:
            if change == "replace":
                write_pdic(pdic, [Entry("manual", 91, 92)], 100, ("001", "@", "@"))
            else:
                pdic.unlink()

    with pytest.raises(RuntimeError, match="页面来源核验期间 PDIC"):
        _publish(pdic, ocred, check)
    assert len(calls) == 3
    if change == "replace":
        assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
            ("manual", 91, 92)
        ]
    else:
        assert not pdic.exists()
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


def test_late_pdic_read_error_is_explicit_without_rollback(tmp_path, monkeypatch):
    pdic, ocred = _setup(tmp_path)
    calls = []
    original = Path.read_bytes
    def check():
        calls.append("check")
    def fault(path):
        if path == pdic and len(calls) == 3:
            raise PermissionError("late PDIC read denied")
        return original(path)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", fault)
        with pytest.raises(RuntimeError, match="无法再次读取 PDIC") as exc:
            _publish(pdic, ocred, check)
    assert "late PDIC read denied" in str(exc.value)
    assert read_pdic(pdic)[0].word == "recognized"
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])


def test_missing_committed_pdic_does_not_rollback_ocred(tmp_path):
    pdic, ocred = _setup(tmp_path)
    calls = []
    def writer(path, entries, width, pages):
        write_pdic(path, entries, width, pages)
        path.unlink()
    with pytest.raises(RuntimeError, match="提交后的 PDIC 文件不存在"):
        _publish(pdic, ocred, lambda: calls.append("check"), writer)
    assert len(calls) == 2
    assert not pdic.exists()
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])


def test_committed_pdic_snapshot_read_error_is_explicit(tmp_path, monkeypatch):
    pdic, ocred = _setup(tmp_path)
    calls, committed = [], []
    original = Path.read_bytes
    def writer(path, entries, width, pages):
        write_pdic(path, entries, width, pages)
        committed.append(True)
    def fault(path):
        if path == pdic and committed and len(calls) == 2:
            raise PermissionError("snapshot PDIC read denied")
        return original(path)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", fault)
        with pytest.raises(RuntimeError, match="无法核验提交后的 PDIC 版本"):
            _publish(pdic, ocred, lambda: calls.append("check"), writer)
    assert len(calls) == 2
    assert read_pdic(pdic)[0].word == "recognized"
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])


def test_normal_commit_preserves_source_pixel_coordinates(tmp_path):
    pdic, ocred = _setup(tmp_path)
    calls = []
    _publish(pdic, ocred, lambda: calls.append("check"))
    assert calls == ["check"] * 3
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("recognized", 17, 43)
    ]
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
