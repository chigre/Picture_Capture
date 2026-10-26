"""PDIC edit during failed-export inspection must prevent OCRed-only rollback."""
from __future__ import annotations

import pytest

from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr


@pytest.mark.parametrize("fault", ["replace", "remove", "none"])
def test_pdic_edit_during_failed_export_inspection_blocks_rollback(tmp_path, monkeypatch, fault):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(b"original PDIC")
    ocred.write_bytes(b"original OCRed")
    pdic_reads = {"count": 0}
    original_read = type(pdic).read_bytes
    writer_calls = []

    def read_with_late_edit(path):
        if path == pdic:
            pdic_reads["count"] += 1
        if path == ocred and pdic_reads["count"] == 2:
            # The first PDIC read is the baseline, the second is the
            # failed-export check. Modify PDIC during subsequent OCRed
            # inspection, after the earlier PDIC check has succeeded.
            if fault == "replace":
                pdic.write_bytes(b"manual PDIC edit")
            elif fault == "remove":
                pdic.unlink()
        return original_read(path)

    monkeypatch.setattr(type(pdic), "read_bytes", read_with_late_edit)

    def failing_export(path, texts):
        path.write_bytes(b"new OCRed")
        raise OSError("export failed")

    def write_never(*args):
        writer_calls.append(True)

    def run():
        publish_existing_pdic_ocr(
            ocred, pdic, ["recognized"], [], 100, ("001", "@", "@"),
            export_ocred=failing_export, write_pdic=write_never,
            expected_pdic_bytes=b"original PDIC",
            expected_ocred_bytes=b"original OCRed",
            expected_exported_ocred_bytes=b"new OCRed",
        )

    if fault == "none":
        with pytest.raises(OSError, match="export failed"):
            run()
        assert ocred.read_bytes() == b"original OCRed"
        assert pdic.read_bytes() == b"original PDIC"
    else:
        with pytest.raises(RuntimeError, match="回滚前 PDIC 已被其他操作修改"):
            run()
        assert ocred.read_bytes() == b"new OCRed"
        if fault == "replace":
            assert pdic.read_bytes() == b"manual PDIC edit"
        else:
            assert not pdic.exists()
    assert writer_calls == []
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
