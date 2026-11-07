"""Failed exporter must not roll back OCRed if it also changed PDIC."""
from __future__ import annotations

import pytest

from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr


@pytest.mark.parametrize("fault", ["pdic_replaced", "pdic_removed", "pdic_unchanged"])
def test_exporter_error_pdic_mutation_blocks_one_sided_compensation(tmp_path, fault):
    pdic = tmp_path / "001.PDIC"
    ocred = tmp_path / "001.OCRed"
    pdic.write_bytes(b"original PDIC")
    ocred.write_bytes(b"original OCRed")
    writer_calls = []

    def broken_export(path, texts):
        path.write_bytes(b"new OCRed")
        if fault == "pdic_replaced":
            pdic.write_bytes(b"external PDIC")
        elif fault == "pdic_removed":
            pdic.unlink()
        raise OSError("export callback failed")

    def write_never(*args):
        writer_calls.append(True)

    def run():
        publish_existing_pdic_ocr(
            ocred, pdic, ["recognized"], [], 100, ("001", "@", "@"),
            export_ocred=broken_export, write_pdic=write_never,
            expected_pdic_bytes=b"original PDIC",
            expected_ocred_bytes=b"original OCRed",
            expected_exported_ocred_bytes=b"new OCRed",
        )

    if fault == "pdic_unchanged":
        with pytest.raises(OSError, match="export callback failed"):
            run()
        assert ocred.read_bytes() == b"original OCRed"
        assert pdic.read_bytes() == b"original PDIC"
    else:
        with pytest.raises(RuntimeError, match="导出期间 PDIC 已被修改"):
            run()
        assert ocred.read_bytes() == b"new OCRed"
        if fault == "pdic_replaced":
            assert pdic.read_bytes() == b"external PDIC"
        else:
            assert not pdic.exists()
    assert writer_calls == []
    assert not list(tmp_path.glob(".001.OCRed.*.tmp"))
