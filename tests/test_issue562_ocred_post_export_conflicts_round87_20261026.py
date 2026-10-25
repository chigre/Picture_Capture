"""Round 87: do not compensate over OCRed edits arriving after export.

The publisher remains optimistic: the final read and filesystem replace are
not an atomic cross-process compare-and-swap.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.models import Entry
from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import export_ocred, render_ocred_text


def _save_pdic(path: Path, word: str = "original") -> None:
    write_pdic(path, [Entry(word, 13, 37)], 100, ("001", "@", "@"))


def _publish(ocred, pdic, export, save, *, expected_pdic_bytes):
    return publish_existing_pdic_ocr(
        ocred, pdic, ["new-ocr"], [Entry("new-ocr", 13, 37)],
        100, ("001", "@", "@"),
        export_ocred=export, write_pdic=save,
        expected_pdic_bytes=expected_pdic_bytes,
        expected_exported_ocred_bytes=render_ocred_text(["new-ocr"]).encode("utf-8"),
    )


@pytest.mark.parametrize("original_ocred", [None, b"\xef\xbb\xbf000|`old\r\n"])
def test_manual_sidecar_edit_during_failed_pdic_save_survives_rollback(
    tmp_path, original_ocred,
):
    pdic = tmp_path / "001.PDIC"
    _save_pdic(pdic)
    original_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    if original_ocred is not None:
        ocred.write_bytes(original_ocred)
    latest = b"000|`proofread-after-export\r\n"
    calls = []

    def save_then_fail(*_args):
        calls.append("pdic")
        ocred.write_bytes(latest)
        raise OSError("pdic denied")

    with pytest.raises(RuntimeError, match="PDIC 保存失败，OCRed 回滚也失败") as exc:
        _publish(ocred, pdic, export_ocred, save_then_fail,
                 expected_pdic_bytes=original_pdic)
    assert "OCRed 在批量 OCR 发布后被其他操作修改" in str(exc.value)
    assert calls == ["pdic"]
    assert ocred.read_bytes() == latest
    assert pdic.read_bytes() == original_pdic
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


def test_sidecar_changed_during_post_export_pdic_check_blocks_pdic_writer(
    tmp_path, monkeypatch,
):
    pdic = tmp_path / "001.PDIC"
    _save_pdic(pdic)
    original_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"old")
    manual = b"000|`corrected-by-editor\n"
    original_read = Path.read_bytes
    pdic_reads = [0]
    calls = []

    def interleaved_read(path):
        if path == pdic:
            pdic_reads[0] += 1
            # 1: original PDIC; 2: post-export PDIC verification.
            if pdic_reads[0] == 2:
                ocred.write_bytes(manual)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", interleaved_read)
    with pytest.raises(RuntimeError, match="OCRed 在导出后、PDIC 保存前被其他操作修改"):
        _publish(ocred, pdic, export_ocred,
                 lambda *_args: calls.append("pdic"),
                 expected_pdic_bytes=original_pdic)
    assert pdic_reads[0] == 2
    assert calls == []
    assert ocred.read_bytes() == manual
    assert pdic.read_bytes() == original_pdic


def test_both_files_edited_during_export_are_not_rolled_back(tmp_path):
    pdic = tmp_path / "001.PDIC"
    _save_pdic(pdic)
    original_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"old")
    manual = b"000|`latest-proofread\n"

    def export_and_manual_edit(path, texts):
        export_ocred(path, texts)
        _save_pdic(pdic, "new-manual-pdic")
        # Interleave an independent OCRed editor after our export.
        path.write_bytes(manual)

    # The worker-supplied canonical byte expectation rejects an unrelated
    # OCRed edit even when it happened inside the export callback itself.
    with pytest.raises(RuntimeError, match="OCRed 导出后内容与预期不符"):
        _publish(ocred, pdic, export_and_manual_edit,
                 lambda *_args: pytest.fail("stale PDIC must not save"),
                 expected_pdic_bytes=original_pdic)
    assert read_pdic(pdic)[0].word == "new-manual-pdic"
    assert ocred.read_bytes() == manual


@pytest.mark.parametrize("old", [None, b"\xef\xbb\xbf000|`old\r\n"])
def test_ordinary_pdic_failure_still_restores_exact_ocred_bytes(tmp_path, old):
    pdic = tmp_path / "001.PDIC"
    _save_pdic(pdic)
    original_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    if old is not None:
        ocred.write_bytes(old)

    with pytest.raises(OSError, match="pdic failed"):
        _publish(ocred, pdic, export_ocred,
                 lambda *_args: (_ for _ in ()).throw(OSError("pdic failed")),
                 expected_pdic_bytes=original_pdic)
    assert pdic.read_bytes() == original_pdic
    assert (ocred.read_bytes() if ocred.exists() else None) == old
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


def test_successful_commit_keeps_original_pixel_coordinates(tmp_path):
    pdic = tmp_path / "001.PDIC"
    _save_pdic(pdic)
    original_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    calls = []

    def export(path, texts):
        calls.append("ocred")
        export_ocred(path, texts)

    def save(path, entries, width, pages):
        calls.append("pdic")
        write_pdic(path, entries, width, pages)

    _publish(ocred, pdic, export, save, expected_pdic_bytes=original_pdic)
    assert calls == ["ocred", "pdic"]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("new-ocr", 13, 37)
    ]


def test_post_export_guard_precedes_pdic_write_and_rollback():
    source = (
        Path(__file__).resolve().parents[1]
        / "src/picture_capture/ocr/batch_publication.py"
    ).read_text(encoding="utf-8")
    assert "_restore_ocred_if_unchanged" in source
    assert "if current_ocred != published_ocred:" in source
    assert source.index("if current_ocred != published_ocred:") < source.index(
        "write_pdic(pdic_path, entries, image_width, pages_info)"
    )


def test_worker_rejects_manual_edit_inside_export_callback(tmp_path):
    from picture_capture.ocr.batch_existing_entries import process_existing_pdic_page

    page = tmp_path / "001.png"
    Image.new("RGB", (100, 140), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    _save_pdic(pdic)
    original_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"original-ocred")
    manual = b"000|`human-edit-during-export\\n"
    writes = []

    def export_then_manual_edit(path, texts):
        export_ocred(path, texts)
        path.write_bytes(manual)

    deps = {
        "pdic_path": lambda path: path.with_suffix(".PDIC"),
        "read_pdic": read_pdic,
        "Image": Image,
        "normalize_page_rgb": lambda opened: opened.copy().convert("RGB"),
        "effective_page_settings": lambda settings, _size, _index: settings,
        "page_template_analysis_image": lambda image, _settings, _index: image,
        "read_page_sections": lambda _page: [],
        "sort_entries_reading_order": lambda entries, _geometry, _sections: entries,
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": lambda *_args, **_kwargs: ["new-ocr"],
        "qt_root": lambda root: root / "QT",
        "export_ocred": export_then_manual_edit,
        "write_pdic": lambda *_args: writes.append("pdic"),
    }
    with pytest.raises(RuntimeError, match="OCRed 导出后内容与预期不符"):
        process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"),
            deps=deps,
        )
    assert writes == []
    assert ocred.read_bytes() == manual
    assert pdic.read_bytes() == original_pdic
