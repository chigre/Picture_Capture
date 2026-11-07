"""Unreadable PDIC after OCRed export must preserve ambiguous disk state.

Round 118 extends the ambiguous-commit policy to the prewrite read: a
failed PDIC inspection cannot prove that PDIC was not externally replaced.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.models import Entry
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import export_ocred, import_ocred
import picture_capture.ocr.batch_publication as publication


@pytest.mark.parametrize("had_sidecar", [False, True])
@pytest.mark.parametrize("had_pdic", [False, True])
def test_prewrite_pdic_read_error_preserves_exported_sidecar_and_skips_writer(
    tmp_path, monkeypatch, had_sidecar, had_pdic,
):
    pdic = tmp_path / "001.PDIC"
    if had_pdic:
        pdic.write_bytes(b"unchanged PDIC bytes")
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir()
    old_ocred = None
    if had_sidecar:
        old_ocred = b"\xef\xbb\xbf000|`manually-corrected\r\n"
        ocred.write_bytes(old_ocred)

    read_original = Path.read_bytes
    pdic_reads = []
    writes = []

    def unreadable_after_export(self):
        if self == pdic:
            pdic_reads.append(len(pdic_reads) + 1)
            if len(pdic_reads) == 2:
                raise PermissionError("verification read denied")
        return read_original(self)

    monkeypatch.setattr(Path, "read_bytes", unreadable_after_export)
    with pytest.raises(RuntimeError, match="拒绝单侧回滚，未启动 PDIC 保存") as caught:
        publish_existing_pdic_ocr(
            ocred, pdic, ["new OCR"], [Entry("new OCR", 7, 31)],
            100, ("001", "@", "@"),
            export_ocred=export_ocred,
            write_pdic=lambda *_args: writes.append("pdic writer invoked"),
        )
    assert isinstance(caught.value.__cause__, PermissionError)
    assert pdic_reads == [1, 2]
    assert writes == []
    assert import_ocred(ocred) == ["new OCR"]
    if had_sidecar:
        assert read_original(ocred) != old_ocred
    else:
        assert ocred.exists()
    if had_pdic:
        assert read_original(pdic) == b"unchanged PDIC bytes"
    else:
        assert not pdic.exists()
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


def test_prewrite_verification_failure_never_attempts_rollback(
    tmp_path, monkeypatch,
):
    pdic = tmp_path / "001.PDIC"
    pdic.write_bytes(b"old")
    ocred = tmp_path / "001.OCRed"
    export_ocred(ocred, ["old"])
    old_bytes = ocred.read_bytes()
    original_read = Path.read_bytes
    count = {"pdic": 0}
    writes = []

    def fail_second_pdic_read(self):
        if self == pdic:
            count["pdic"] += 1
            if count["pdic"] == 2:
                raise PermissionError("verification denied")
        return original_read(self)

    monkeypatch.setattr(Path, "read_bytes", fail_second_pdic_read)
    rollback_calls = []

    def forbid_rollback(*_args, **_kwargs):
        rollback_calls.append(True)
        raise AssertionError("unsafe rollback attempted")

    monkeypatch.setattr(publication, "_restore_ocred_if_unchanged", forbid_rollback)
    with pytest.raises(RuntimeError, match="拒绝单侧回滚，未启动 PDIC 保存") as caught:
        publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 7, 31)],
            100, ("001", "@", "@"),
            export_ocred=export_ocred,
            write_pdic=lambda *_args: writes.append("pdic writer invoked"),
        )
    assert isinstance(caught.value.__cause__, PermissionError)
    assert "verification denied" in str(caught.value)
    assert rollback_calls == []
    assert count["pdic"] == 2
    assert writes == []
    assert import_ocred(ocred) == ["new"]
    assert original_read(ocred) != old_bytes
    assert original_read(pdic) == b"old"


def test_prewrite_and_postwrite_verification_errors_have_distinct_recovery_rules():
    source = (
        Path(__file__).resolve().parents[1]
        / "src/picture_capture/ocr/batch_publication.py"
    ).read_text(encoding="utf-8")
    # Anchor on the PDIC verification phase, not the number of earlier
    # OSError handlers (which grows as sidecar integrity checks evolve).
    prewrite = source.split("pdic_after_export = pdic_path.read_bytes()", 1)[1]
    prewrite = prewrite.split("if pdic_after_export != previous_pdic:", 1)[0]
    postwrite = source.split("except Exception as pdic_error:", 1)[1]
    assert "拒绝单侧回滚，未启动 PDIC 保存" in prewrite
    assert "_restore_ocred_if_unchanged(ocred_path, previous, published_ocred)" not in prewrite
    assert "不执行仅 OCRed 回滚" in postwrite
    assert "current_pdic != previous_pdic" in postwrite
