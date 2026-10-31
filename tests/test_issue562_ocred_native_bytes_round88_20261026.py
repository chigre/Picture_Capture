"""Round 88: real OCRed bytes must match the platform-native text writer.

The canonical legacy writer uses text-mode newline translation on Windows.
A mock exporter that does not write must not bypass the integrity guard.
"""
from __future__ import annotations

import os

import pytest

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import (
    export_ocred, import_ocred, render_ocred_bytes, render_ocred_text,
)


@pytest.mark.parametrize("words", [[], ["alpha"], ["苹果", "second"], ["a\nb"]])
def test_canonical_ocred_bytes_match_real_atomic_writer_on_each_platform(
    tmp_path, words,
):
    path = tmp_path / "QT" / "001.OCRed"
    export_ocred(path, words)
    assert path.read_bytes() == render_ocred_bytes(words)
    assert render_ocred_bytes(words) == render_ocred_text(words).replace(
        "\n", os.linesep,
    ).encode("utf-8")
    if words:
        assert (b"\r\n" in path.read_bytes()) == (os.linesep == "\r\n")


def test_missing_export_is_rejected_without_writing_pdic(tmp_path):
    pdic = tmp_path / "001.PDIC"
    write_pdic(pdic, [Entry("old", 12, 34)], 90, ("001", "@", "@"))
    before = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    calls = []
    with pytest.raises(RuntimeError, match="OCRed 导出后内容与预期不符"):
        publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 12, 34)], 90,
            ("001", "@", "@"),
            export_ocred=lambda *_args: calls.append("export-noop"),
            write_pdic=lambda *_args: calls.append("pdic"),
            expected_pdic_bytes=before,
            expected_exported_ocred_bytes=render_ocred_bytes(["new"]),
        )
    assert calls == ["export-noop"]
    assert pdic.read_bytes() == before
    assert not ocred.exists()


def test_expected_native_bytes_allow_real_publication_with_original_xy(tmp_path):
    pdic = tmp_path / "001.PDIC"
    write_pdic(pdic, [Entry("old", 12, 34)], 90, ("001", "@", "@"))
    before = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    publish_existing_pdic_ocr(
        ocred, pdic, ["苹果"], [Entry("苹果", 12, 34)], 90,
        ("001", "@", "@"),
        export_ocred=export_ocred, write_pdic=write_pdic,
        expected_pdic_bytes=before,
        expected_exported_ocred_bytes=render_ocred_bytes(["苹果"]),
    )
    assert import_ocred(ocred) == ["苹果"]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("苹果", 12, 34)
    ]
