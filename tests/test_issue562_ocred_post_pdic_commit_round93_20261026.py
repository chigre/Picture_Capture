"""Round 93: detect OCRed manual edits during a successful PDIC save.

The publisher cannot atomically commit two independent files. A conflict
detected after PDIC commit must be reported, never 'fixed' by a one-sided
rollback that could overwrite newer human proofreading.
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


def _fixture(tmp_path):
    pdic = tmp_path / "001.PDIC"
    write_pdic(pdic, [Entry("before", 13, 37)], 100, ("001", "@", "@"))
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"\xef\xbb\xbf000|`proofread-before\r\n")
    return pdic, ocred


def _publish(pdic, ocred, save):
    return publish_existing_pdic_ocr(
        ocred, pdic, ["new-ocr"], [Entry("new-ocr", 13, 37)],
        100, ("001", "@", "@"),
        export_ocred=export_ocred, write_pdic=save,
        expected_exported_ocred_bytes=render_ocred_bytes(["new-ocr"]),
    )


@pytest.mark.parametrize("interference", ["rewrite", "remove"])
def test_successful_pdic_commit_reports_sidecar_edit_without_unsafe_rollback(
    tmp_path, interference,
):
    pdic, ocred = _fixture(tmp_path)
    latest = b"\xef\xbb\xbf000|`human-correction-after-export\r\n"
    events = []

    def save_then_external_edit(path, entries, width, pages):
        events.append("pdic")
        write_pdic(path, entries, width, pages)
        if interference == "rewrite":
            ocred.write_bytes(latest)
        else:
            ocred.unlink()
        events.append("external-ocred-edit")

    with pytest.raises(RuntimeError, match="PDIC 已保存，但 OCRed 在保存期间被其他操作修改"):
        _publish(pdic, ocred, save_then_external_edit)

    assert events == ["pdic", "external-ocred-edit"]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("new-ocr", 13, 37)
    ]
    assert (ocred.read_bytes() if ocred.exists() else None) == (
        latest if interference == "rewrite" else None
    )
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


def test_postcommit_ocred_inspection_error_reports_ambiguous_pair(tmp_path, monkeypatch):
    pdic, ocred = _fixture(tmp_path)
    original_read = Path.read_bytes
    committed = [False]

    def save(path, entries, width, pages):
        write_pdic(path, entries, width, pages)
        committed[0] = True

    def fail_postcommit_ocred_read(path):
        if path == ocred and committed[0]:
            raise PermissionError("simulated read denied after commit")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", fail_postcommit_ocred_read)
    with pytest.raises(RuntimeError, match="PDIC 已保存，但无法核验 OCRed") as error:
        _publish(pdic, ocred, save)
    assert "simulated read denied" in str(error.value)
    assert committed == [True]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("new-ocr", 13, 37)
    ]
    assert original_read(ocred) == render_ocred_bytes(["new-ocr"])


def test_uncontended_commit_preserves_legacy_order_and_original_pixel_xy(tmp_path):
    pdic, ocred = _fixture(tmp_path)
    events = []

    def export(path, words):
        events.append("ocred")
        export_ocred(path, words)

    def save(path, entries, width, pages):
        events.append("pdic")
        write_pdic(path, entries, width, pages)

    publish_existing_pdic_ocr(
        ocred, pdic, ["recognized"], [Entry("recognized", 13, 37)],
        100, ("001", "@", "@"),
        export_ocred=export, write_pdic=save,
        expected_exported_ocred_bytes=render_ocred_bytes(["recognized"]),
    )
    assert events == ["ocred", "pdic"]
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("recognized", 13, 37)
    ]


def test_real_worker_propagates_postcommit_conflict_without_overwriting_manual_edit(
    tmp_path,
):
    page = tmp_path / "001.png"
    Image.new("RGB", (100, 140), "white").save(page)
    pdic, ocred = _fixture(tmp_path)
    latest = b"000|`reviewed-after-pdic-commit\n"

    def save_and_proofread(path, entries, width, pages):
        write_pdic(path, entries, width, pages)
        ocred.write_bytes(latest)

    deps = {
        "pdic_path": lambda path: path.with_suffix(".PDIC"),
        "read_pdic": read_pdic,
        "Image": Image,
        "normalize_page_rgb": lambda opened: opened.copy().convert("RGB"),
        "effective_page_settings": lambda settings, _size, _index: settings,
        "page_template_analysis_image": lambda image, _settings, _index: image,
        "read_page_sections": lambda _page: [],
        "sort_entries_reading_order": lambda entries, _geo, _sections: entries,
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": lambda *_args, **_kwargs: ["new-ocr"],
        "qt_root": lambda root: root / "QT",
        "export_ocred": export_ocred,
        "write_pdic": save_and_proofread,
    }
    with pytest.raises(RuntimeError, match="PDIC 已保存，但 OCRed 在保存期间被其他操作修改"):
        process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], ("001", "@", "@"),
            deps=deps,
        )
    assert ocred.read_bytes() == latest
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("new-ocr", 13, 37)
    ]


def test_postcommit_check_is_after_writer_and_does_not_invoke_rollback():
    source = (
        Path(__file__).resolve().parents[1]
        / "src/picture_capture/ocr/batch_publication.py"
    ).read_text(encoding="utf-8")
    assert source.index("write_pdic(pdic_path, entries, image_width, pages_info)") < (
        source.index("if ocred_after_pdic != published_ocred:")
    )
    tail = source.split("if ocred_after_pdic != published_ocred:", 1)[1]
    assert "_restore_ocred" not in tail
