"""Round 139: retain exact filesystem read errors at pre-PDIC publication gates.

After OCRed export, an unreadable ownership snapshot must not lead to a
PDIC write or a one-sided OCRed rollback. Diagnostics retain the original
exception object without changing the on-disk recovery policy.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.ocr import batch_publication as publication


OLD_OCRED = b"prior human OCRed proofreading"
PUBLISHED_OCRED = b"batch OCRed output"
ORIGINAL_PDIC = b"original marker PDIC"


@pytest.mark.parametrize(
    ("checkpoint", "message"),
    [
        ("post_export_ocred", "OCRed 导出后无法核验其文件版本"),
        ("post_export_pdic", "OCRed 已导出，但无法核验导出后的 PDIC"),
        ("post_context_pdic", "页面来源核验后无法读取 PDIC"),
        ("post_context_ocred", "页面来源核验后无法读取 OCRed"),
    ],
)
def test_unreadable_pre_pdic_snapshot_keeps_exact_error_and_disk_pair(
    tmp_path, monkeypatch, checkpoint, message,
):
    ocred = tmp_path / "001.OCRed"
    pdic = tmp_path / "001.PDIC"
    ocred.write_bytes(OLD_OCRED)
    pdic.write_bytes(ORIGINAL_PDIC)
    actual_read = Path.read_bytes
    denied = PermissionError("injected ownership read failure")
    state = {"exported": False, "validations": 0}
    writes = []
    denied_reads = []

    def guarded_read(path):
        fail = (
            (checkpoint == "post_export_ocred"
             and path == ocred and state["exported"])
            or (checkpoint == "post_export_pdic"
                and path == pdic and state["exported"])
            or (checkpoint == "post_context_pdic"
                and path == pdic and state["validations"] == 2)
            or (checkpoint == "post_context_ocred"
                and path == ocred and state["validations"] == 2)
        )
        if fail:
            denied_reads.append(path)
            raise denied
        return actual_read(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)

    def export(path, _texts):
        path.write_bytes(PUBLISHED_OCRED)
        state["exported"] = True

    def validate():
        state["validations"] += 1

    def write(*_args):
        writes.append(True)

    with pytest.raises(RuntimeError, match=message) as caught:
        publication.publish_existing_pdic_ocr(
            ocred, pdic, ["word"], [], 100, ("001", "@", "@"),
            export_ocred=export, write_pdic=write,
            expected_pdic_bytes=ORIGINAL_PDIC,
            expected_ocred_bytes=OLD_OCRED,
            expected_exported_ocred_bytes=PUBLISHED_OCRED,
            validate_page_context=(
                validate if checkpoint.startswith("post_context") else None
            ),
        )

    assert caught.value.verification_error is denied
    assert caught.value.__cause__ is denied
    assert len(denied_reads) == 1
    assert writes == []
    assert actual_read(pdic) == ORIGINAL_PDIC
    assert actual_read(ocred) == PUBLISHED_OCRED
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
    assert state["validations"] == (
        2 if checkpoint.startswith("post_context") else 0
    )
