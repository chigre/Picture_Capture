"""Round 89: an exporter exception must not erase later OCRed proofreading.

The worker passes canonical OCRed bytes so a failed exporter cannot claim
ownership of arbitrary on-disk content. Checks remain optimistic, not locks.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr.batch_existing_entries import process_existing_pdic_page
from picture_capture.ocr.batch_publication import publish_existing_pdic_ocr
from picture_capture.ocr.text_io import export_ocred, render_ocred_bytes


OLD_BYTES = b"\xef\xbb\xbf000|`reviewed-old\r\n"
MANUAL_BYTES = b"000|`proofread-after-export\r\n"


def _publish(tmp_path, export, *, old, expected=True, pdic_write=None):
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    if old is not None:
        ocred.write_bytes(old)
    pdic = tmp_path / "001.PDIC"
    write_pdic(pdic, [Entry("old", 11, 33)], 90, ("001", "@", "@"))
    pdic_before = pdic.read_bytes()
    calls = []

    def save(*args):
        calls.append("pdic")
        if pdic_write is not None:
            pdic_write(*args)

    def run():
        kwargs = {"expected_exported_ocred_bytes": render_ocred_bytes(["new"])} if expected else {}
        return publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 11, 33)],
            90, ("001", "@", "@"),
            export_ocred=export, write_pdic=save, **kwargs,
        )

    return ocred, pdic, pdic_before, calls, run


@pytest.mark.parametrize("old", [None, OLD_BYTES])
def test_exporter_raises_after_external_ocred_edit_never_rolls_it_back(tmp_path, old):
    def export_then_manual_edit(path, texts):
        export_ocred(path, texts)
        path.write_bytes(MANUAL_BYTES)
        raise OSError("export hook failed")

    ocred, pdic, pdic_before, calls, run = _publish(
        tmp_path, export_then_manual_edit, old=old,
    )
    with pytest.raises(RuntimeError, match="拒绝回滚不明来源的 OCRed") as exc:
        run()
    assert isinstance(exc.value.__cause__, OSError)
    assert "export hook failed" in str(exc.value)
    assert ocred.read_bytes() == MANUAL_BYTES
    assert pdic.read_bytes() == pdic_before
    assert calls == []
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("old", [None, OLD_BYTES])
def test_exporter_raises_after_its_own_atomic_write_restores_exact_old_bytes(
    tmp_path, old,
):
    def export_then_fail(path, texts):
        export_ocred(path, texts)
        raise OSError("post-export callback failed")

    ocred, pdic, pdic_before, calls, run = _publish(
        tmp_path, export_then_fail, old=old,
    )
    with pytest.raises(OSError, match="post-export callback failed"):
        run()
    assert (ocred.read_bytes() if ocred.exists() else None) == old
    assert pdic.read_bytes() == pdic_before
    assert calls == []
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


def test_exporter_raises_after_noncanonical_write_keeps_unknown_bytes(tmp_path):
    unexpected = b"partial-or-unowned-sidecar"
    def broken_export(path, _texts):
        path.write_bytes(unexpected)
        raise OSError("export aborted")

    ocred, pdic, pdic_before, calls, run = _publish(
        tmp_path, broken_export, old=OLD_BYTES,
    )
    with pytest.raises(RuntimeError, match="磁盘内容与本次导出预期不符"):
        run()
    assert ocred.read_bytes() == unexpected
    assert pdic.read_bytes() == pdic_before
    assert calls == []


def test_manual_edit_between_export_error_inspection_and_rollback_survives(
    tmp_path, monkeypatch,
):
    exporter_finished = []
    def export_then_fail(path, texts):
        export_ocred(path, texts)
        # Atomic publication may read its destination for verification.
        # Arm the injected proofreader edit only AFTER the exporter returns,
        # so its own sidecar checks cannot consume the fault prematurely.
        exporter_finished.append(True)
        raise OSError("post-export failure")

    ocred, pdic, pdic_before, calls, run = _publish(
        tmp_path, export_then_fail, old=OLD_BYTES,
    )
    original_read = Path.read_bytes
    post_export_reads = [0]

    def read_with_interleaved_proofreading(path):
        if path == ocred and exporter_finished:
            post_export_reads[0] += 1
            # 1: failed-export content inspection; 2: optimistic ownership
            # comparison before compensation. Edit just before the second.
            if post_export_reads[0] == 2:
                path.write_bytes(MANUAL_BYTES)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_with_interleaved_proofreading)
    with pytest.raises(RuntimeError, match="原文件回滚也失败") as exc:
        run()
    assert "拒绝回滚覆盖人工校对内容" in str(exc.value)
    assert post_export_reads[0] >= 2
    assert original_read(ocred) == MANUAL_BYTES
    assert original_read(pdic) == pdic_before
    assert calls == []


def test_direct_legacy_exporter_still_compensates_without_expected_bytes(tmp_path):
    def export_then_fail(path, texts):
        export_ocred(path, texts)
        raise OSError("legacy post-export error")

    ocred, pdic, pdic_before, calls, run = _publish(
        tmp_path, export_then_fail, old=OLD_BYTES, expected=False,
    )
    with pytest.raises(OSError, match="legacy post-export error"):
        run()
    assert ocred.read_bytes() == OLD_BYTES
    assert pdic.read_bytes() == pdic_before
    assert calls == []


def test_worker_preserves_manual_sidecar_and_original_marker_xy(tmp_path):
    page = tmp_path / "001.png"
    Image.new("RGB", (90, 120), "white").save(page)
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("old", 14, 45)], 90, ("001", "@", "@"))
    old_pdic = pdic.read_bytes()
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(OLD_BYTES)
    pdic_writes = []

    def exporter(path, texts):
        export_ocred(path, texts)
        path.write_bytes(MANUAL_BYTES)
        raise OSError("exporter post-hook")

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
        "ocr_entries": lambda *_args, **_kwargs: ["new"],
        "qt_root": lambda root: root / "QT",
        "export_ocred": exporter,
        "write_pdic": lambda *_args: pdic_writes.append("pdic"),
    }
    with pytest.raises(RuntimeError, match="拒绝回滚不明来源的 OCRed"):
        process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"),
            deps=deps,
        )
    assert ocred.read_bytes() == MANUAL_BYTES
    assert pdic.read_bytes() == old_pdic
    assert [(entry.word, entry.x, entry.y) for entry in read_pdic(pdic)] == [
        ("old", 14, 45)
    ]
    assert pdic_writes == []


def test_round89_export_exception_uses_guarded_rollback():
    source = (
        Path(__file__).resolve().parents[1]
        / "src/picture_capture/ocr/batch_publication.py"
    ).read_text(encoding="utf-8")
    export_error_block = source.split("except Exception as export_error:", 1)[1].split(
        "# Capture the sidecar produced", 1
    )[0]
    assert "current_ocred != expected_exported_ocred_bytes" in export_error_block
    assert "_restore_ocred_if_unchanged(" in export_error_block
    assert "_restore_ocred_bytes(ocred_path, previous)" not in export_error_block
