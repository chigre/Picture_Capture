"""Unverifiable PDIC after successful OCRed export must not trigger a one-sided rollback."""
from __future__ import annotations

import pytest

from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr


@pytest.mark.parametrize("pdic_changed", [False, True], ids=["unchanged", "replaced"])
def test_pdic_read_failure_after_ocred_export_preserves_both_disk_versions(
    tmp_path, monkeypatch, pdic_changed,
):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(b"prior PDIC")
    ocred.write_bytes(b"prior OCRed")
    original_read_bytes = type(pdic).read_bytes
    pdic_read_count = 0
    writer_calls = []

    def fail_second_pdic_read(path):
        nonlocal pdic_read_count
        if path == pdic:
            pdic_read_count += 1
            if pdic_read_count == 2:
                raise PermissionError("PDIC temporarily unreadable")
        return original_read_bytes(path)

    monkeypatch.setattr(type(pdic), "read_bytes", fail_second_pdic_read)

    def successful_export(path, _texts):
        path.write_bytes(b"exported OCRed")
        if pdic_changed:
            pdic.write_bytes(b"externally replaced PDIC")

    with pytest.raises(RuntimeError, match="拒绝单侧回滚，未启动 PDIC 保存"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["recognized"], [], 100, ("001", "@", "@"),
            export_ocred=successful_export,
            write_pdic=lambda *_args: writer_calls.append(True),
            expected_pdic_bytes=b"prior PDIC",
            expected_ocred_bytes=b"prior OCRed",
            expected_exported_ocred_bytes=b"exported OCRed",
        )

    assert pdic_read_count == 2
    assert original_read_bytes(ocred) == b"exported OCRed"
    assert original_read_bytes(pdic) == (
        b"externally replaced PDIC" if pdic_changed else b"prior PDIC"
    )
    assert writer_calls == []
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
