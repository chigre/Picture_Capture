"""Round 122: slow page-context checks must not overwrite newer sidecars.

A source-image hash can take time after the initial OCRed/PDIC snapshots.
Inject manual changes *inside* that validation and verify no exporter or
PDIC writer runs; keep the on-disk manual edit byte-for-byte.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from picture_capture.models import Entry
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import export_ocred, import_ocred
from picture_capture.io.formats import write_pdic


@pytest.mark.parametrize("target_name", ["ocred", "pdic"])
@pytest.mark.parametrize("initially_present", [False, True])
def test_edit_during_page_context_validation_aborts_before_any_export(
    tmp_path, target_name, initially_present,
):
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir()
    pdic = tmp_path / "001.PDIC"
    target = {"ocred": ocred, "pdic": pdic}[target_name]
    if initially_present:
        target.write_bytes(b"old proofread sidecar bytes")
    original_ocred = ocred.read_bytes() if ocred.exists() else None
    original_pdic = pdic.read_bytes() if pdic.exists() else None
    manual_bytes = b"new manual edit during slow source-image hash"
    calls = []

    def validate_page_context():
        calls.append("validate")
        target.write_bytes(manual_bytes)

    with pytest.raises(RuntimeError, match=f"页面来源核验期间 {target_name.upper() if target_name == 'pdic' else 'OCRed'} 已被其他操作修改"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["recognized"], [Entry("recognized", 7, 19)],
            80, ("001", "@", "@"),
            export_ocred=lambda *_: calls.append("export"),
            write_pdic=lambda *_: calls.append("write"),
            expected_ocred_bytes=original_ocred,
            expected_pdic_bytes=original_pdic,
            validate_page_context=validate_page_context,
        )
    assert calls == ["validate"]
    assert target.read_bytes() == manual_bytes
    other = pdic if target == ocred else ocred
    other_original = original_pdic if target == ocred else original_ocred
    assert (other.read_bytes() if other.exists() else None) == other_original


@pytest.mark.parametrize("target_name", ["ocred", "pdic"])
def test_unreadable_sidecar_after_context_check_never_starts_export(
    tmp_path, monkeypatch, target_name,
):
    ocred = tmp_path / "001.OCRed"
    pdic = tmp_path / "001.PDIC"
    ocred.write_bytes(b"old OCRed")
    pdic.write_bytes(b"old PDIC")
    target = {"ocred": ocred, "pdic": pdic}[target_name]
    original_read = Path.read_bytes
    after_validation = [False]
    calls = []

    def read_with_permission_failure(self):
        if after_validation[0] and self == target:
            raise PermissionError("manual editor locked sidecar")
        return original_read(self)

    def validate_page_context():
        calls.append("validate")
        after_validation[0] = True

    monkeypatch.setattr(Path, "read_bytes", read_with_permission_failure)
    with pytest.raises(RuntimeError, match=f"无法再次读取 {target_name.upper() if target_name == 'pdic' else 'OCRed'}") as caught:
        publish_existing_pdic_ocr(
            ocred, pdic, ["recognized"], [Entry("recognized", 7, 19)],
            80, ("001", "@", "@"),
            export_ocred=lambda *_: calls.append("export"),
            write_pdic=lambda *_: calls.append("write"),
            expected_ocred_bytes=b"old OCRed",
            expected_pdic_bytes=b"old PDIC",
            validate_page_context=validate_page_context,
        )
    assert isinstance(caught.value.__cause__, PermissionError)
    assert calls == ["validate"]
    assert original_read(ocred) == b"old OCRed"
    assert original_read(pdic) == b"old PDIC"


def test_unchanged_sidecars_after_context_check_publish_normally(tmp_path):
    ocred = tmp_path / "QT" / "001.OCRed"
    pdic = tmp_path / "001.PDIC"
    export_ocred(ocred, ["old"])
    write_pdic(pdic, [Entry("old", 7, 19)], 80, ("001", "@", "@"))
    old_ocred, old_pdic = ocred.read_bytes(), pdic.read_bytes()
    checks = []

    publish_existing_pdic_ocr(
        ocred, pdic, ["new"], [Entry("new", 7, 19)],
        80, ("001", "@", "@"),
        export_ocred=export_ocred,
        write_pdic=write_pdic,
        expected_ocred_bytes=old_ocred,
        expected_pdic_bytes=old_pdic,
        validate_page_context=lambda: checks.append("validated"),
    )
    assert checks == ["validated", "validated", "validated"]
    assert import_ocred(ocred) == ["new"]
    assert pdic.read_text(encoding="utf-8").startswith("new#7#19#")
