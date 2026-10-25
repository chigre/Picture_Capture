"""Round 79: preserve PDIC/OCRed cardinality and atomic sidecar publication."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.models import Entry
from picture_capture.ocr.batch_existing_entries import process_existing_pdic_page
from picture_capture.ocr.text_io import export_ocred, import_ocred
from picture_capture.io import formats


@pytest.mark.parametrize("texts", [["only-one"], ["one", "two", "extra"]])
def test_mismatched_ocr_count_rejects_both_outputs_and_preserves_markers(tmp_path, texts):
    page = tmp_path / "001.png"
    Image.new("RGB", (80, 100), "white").save(page)
    entries = [Entry("original-one", 7, 19), Entry("original-two", 32, 71)]
    events = []
    deps = {
        "read_pdic": lambda _path: entries,
        "pdic_path": lambda page: page.with_suffix(".PDIC"),
        "Image": Image,
        "normalize_page_rgb": lambda image: image.copy().convert("RGB"),
        "effective_page_settings": lambda settings, _size, _index: settings,
        "page_template_analysis_image": lambda image, _settings, _index: image,
        "read_page_sections": lambda _page: [],
        "sort_entries_reading_order": lambda entries, _geometry, _sections: entries,
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": lambda *_args, **_kwargs: list(texts),
        "qt_root": lambda root: root / "QT",
        "export_ocred": lambda *_args: events.append("export"),
        "write_pdic": lambda *_args: events.append("write"),
    }
    with pytest.raises(ValueError, match="PDIC 2 条，OCR"):
        process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"),
            deps=deps,
        )
    assert events == []
    assert [(e.word, e.x, e.y) for e in entries] == [
        ("original-one", 7, 19), ("original-two", 32, 71),
    ]


def test_ocred_export_creates_directory_and_preserves_legacy_format(tmp_path):
    path = tmp_path / "nested" / "OCR" / "001.OCRed"
    export_ocred(path, ["alpha", "中文"])
    assert path.read_text(encoding="utf-8") == "000|`alpha\n001|`中文\n"
    assert import_ocred(path) == ["alpha", "中文"]
    assert list(path.parent.glob(".001.OCRed.*.tmp")) == []


def test_ocred_failed_atomic_swap_preserves_previous_bytes_and_cleans_temp(
    tmp_path, monkeypatch,
):
    path = tmp_path / "001.OCRed"
    old = b"000|`proofread-old\n"
    path.write_bytes(old)

    def fail_replace(_source, _target):
        raise OSError("simulated swap failure")

    monkeypatch.setattr(formats.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated swap failure"):
        export_ocred(path, ["new-text"])

    assert path.read_bytes() == old
    assert list(tmp_path.glob(".001.OCRed.*.tmp")) == []


def test_ocred_failed_atomic_swap_for_new_file_leaves_no_partial_output(
    tmp_path, monkeypatch,
):
    path = tmp_path / "nested" / "001.OCRed"
    def fail_replace(_source, _target):
        raise OSError("simulated swap failure")

    monkeypatch.setattr(formats.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated swap failure"):
        export_ocred(path, ["new-text"])

    assert not path.exists()
    assert list(path.parent.glob(".001.OCRed.*.tmp")) == []


def test_atomic_sidecar_contract_is_physical_and_pdic_writer_remains_canonical():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture"
    leaf = (root / "ocr/batch_existing_entries.py").read_text(encoding="utf-8")
    writer = (root / "ocr/text_io.py").read_text(encoding="utf-8")
    assert "if len(texts) != len(entries):" in leaf
    assert 'deps["export_ocred"](' in leaf
    assert 'deps["write_pdic"](' in leaf
    assert "write_text_atomic(" in writer
    assert "path.write_text(" not in writer
