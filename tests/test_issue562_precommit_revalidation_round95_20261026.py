"""Round 95: guard PDIC/OCRed edits during the last slow source-image hash.

The page-context callback may stream a large image. Recheck both published
sidecars after it returns and before invoking the PDIC writer. These tests
inject concurrent edits at that exact boundary, not after PDIC commit.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import export_ocred, render_ocred_bytes


PAGES = ("001", "@", "@")
OLD_OCRED = b"\\xef\\xbb\\xbf000|`reviewed-before\\r\\n"
HUMAN_OCRED = b"\\xef\\xbb\\xbf000|`reviewed-during-hash\\r\\n"


def _files(tmp_path, old_ocred):
    pdic = tmp_path / "001.PDIC"
    write_pdic(pdic, [Entry("old", 19, 57)], 120, PAGES)
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir()
    if old_ocred is not None:
        ocred.write_bytes(old_ocred)
    return pdic, ocred


def _publish(pdic, ocred, check, writer=write_pdic, *, old_ocred=None):
    return publish_existing_pdic_ocr(
        ocred, pdic, ["new"], [Entry("new", 19, 57)], 120, PAGES,
        export_ocred=export_ocred,
        write_pdic=writer,
        expected_pdic_bytes=pdic.read_bytes(),
        expected_ocred_bytes=old_ocred,
        expected_exported_ocred_bytes=render_ocred_bytes(["new"]),
        validate_page_context=check,
    )


@pytest.mark.parametrize("old_ocred", [None, OLD_OCRED])
def test_pdic_edit_during_final_source_check_restores_only_owned_ocred(
    tmp_path, old_ocred,
):
    pdic, ocred = _files(tmp_path, old_ocred)
    human_pdic = b"external-pdic-change-during-image-hash"
    checks, saves = [], []

    def check():
        checks.append("check")
        if len(checks) == 2:
            pdic.write_bytes(human_pdic)

    def save(*_args):
        saves.append("pdic")

    with pytest.raises(RuntimeError, match="页面来源核验期间 PDIC 已被其他操作修改"):
        _publish(pdic, ocred, check, save, old_ocred=old_ocred)

    assert checks == ["check", "check"]
    assert saves == []
    assert pdic.read_bytes() == human_pdic
    assert (ocred.read_bytes() if ocred.exists() else None) == old_ocred
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


def test_ocred_manual_edit_during_final_source_check_survives(tmp_path):
    pdic, ocred = _files(tmp_path, OLD_OCRED)
    original_pdic = pdic.read_bytes()
    checks, saves = [], []

    def check():
        checks.append("check")
        if len(checks) == 2:
            ocred.write_bytes(HUMAN_OCRED)

    def save(*_args):
        saves.append("pdic")

    with pytest.raises(RuntimeError, match="页面来源核验期间 OCRed 已被其他操作修改"):
        _publish(pdic, ocred, check, save, old_ocred=OLD_OCRED)

    assert checks == ["check", "check"]
    assert saves == []
    assert pdic.read_bytes() == original_pdic
    assert ocred.read_bytes() == HUMAN_OCRED


def test_unreadable_final_pdic_is_explicit_and_compensates(tmp_path, monkeypatch):
    pdic, ocred = _files(tmp_path, OLD_OCRED)
    original_pdic = pdic.read_bytes()
    original_read = Path.read_bytes
    after_validator = [False]
    saves = []

    def check():
        if not after_validator[0]:
            after_validator[0] = True
        else:
            after_validator[0] = "finished"

    def read_with_fault(path):
        if path == pdic and after_validator[0] == "finished":
            raise PermissionError("injected final PDIC read failure")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_with_fault)
    with pytest.raises(RuntimeError, match="页面来源核验后无法读取 PDIC") as exc:
        _publish(
            pdic, ocred, check, lambda *_args: saves.append("pdic"),
            old_ocred=OLD_OCRED,
        )
    assert "injected final PDIC read failure" in str(exc.value)
    assert saves == []
    assert original_read(pdic) == original_pdic
    assert original_read(ocred) == OLD_OCRED


def test_pdic_and_ocred_both_changed_refuses_unsafe_compensation(tmp_path):
    pdic, ocred = _files(tmp_path, OLD_OCRED)
    human_pdic = b"human-pdic-after-export"
    saves = []
    checks = []

    def check():
        checks.append("check")
        if len(checks) == 2:
            pdic.write_bytes(human_pdic)
            ocred.write_bytes(HUMAN_OCRED)

    with pytest.raises(RuntimeError, match="PDIC 被修改，且 OCRed 回滚失败"):
        _publish(
            pdic, ocred, check, lambda *_args: saves.append("pdic"),
            old_ocred=OLD_OCRED,
        )
    assert saves == []
    assert pdic.read_bytes() == human_pdic
    assert ocred.read_bytes() == HUMAN_OCRED


def test_uncontended_three_source_checks_preserve_original_xy(tmp_path):
    pdic, ocred = _files(tmp_path, OLD_OCRED)
    checks = []

    _publish(
        pdic, ocred, lambda: checks.append("check"),
        old_ocred=OLD_OCRED,
    )
    assert checks == ["check", "check", "check"]
    assert [(entry.word, entry.x, entry.y) for entry in read_pdic(pdic)] == [
        ("new", 19, 57),
    ]
    assert ocred.read_bytes() == render_ocred_bytes(["new"])


def test_legacy_direct_call_without_validator_remains_supported(tmp_path):
    pdic, ocred = _files(tmp_path, OLD_OCRED)
    publish_existing_pdic_ocr(
        ocred, pdic, ["legacy"], [Entry("legacy", 19, 57)],
        120, PAGES, export_ocred=export_ocred, write_pdic=write_pdic,
    )
    assert read_pdic(pdic)[0].word == "legacy"
    assert ocred.read_bytes() == render_ocred_bytes(["legacy"])
