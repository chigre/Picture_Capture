"""Round 94: detect SECTION/source-image conflicts inside successful PDIC saves.

This is post-commit *detection*, not a two-file transaction or filesystem
compare-and-swap. Never roll back already committed PDIC or newer page data.
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
from picture_capture.persistence.page_sections import (
    PageSection, read_page_sections, write_page_sections,
)


def _publisher_fixture(tmp_path):
    pdic = tmp_path / "001.PDIC"
    write_pdic(pdic, [Entry("original", 17, 43)], 100, ("001", "@", "@"))
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True, exist_ok=True)
    ocred.write_bytes(b"\xef\xbb\xbf000|\x60manual-before\r\n")
    return pdic, ocred


def test_postcommit_page_context_failure_preserves_committed_pair(tmp_path):
    pdic, ocred = _publisher_fixture(tmp_path)
    events = []

    def check():
        events.append("check")
        if events.count("check") == 3:
            raise RuntimeError("SECTION changed during PDIC save")

    def export(path, words):
        events.append("export")
        export_ocred(path, words)

    def save(path, entries, width, pages):
        events.append("pdic")
        write_pdic(path, entries, width, pages)

    with pytest.raises(RuntimeError, match="PDIC 已保存，但保存期间页面来源") as exc:
        publish_existing_pdic_ocr(
            ocred, pdic, ["new"], [Entry("new", 17, 43)],
            100, ("001", "@", "@"),
            export_ocred=export, write_pdic=save,
            expected_exported_ocred_bytes=render_ocred_bytes(["new"]),
            validate_page_context=check,
        )
    assert "SECTION changed during PDIC save" in str(exc.value)
    assert events == ["check", "export", "check", "pdic", "check"]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("new", 17, 43)
    ]
    assert ocred.read_bytes() == render_ocred_bytes(["new"])
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


@pytest.mark.parametrize("change", ["section", "image", "image_removed"])
def test_real_worker_detects_source_mutation_during_successful_pdic_save(
    tmp_path, change,
):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (100, 120), "white").save(page)
    write_page_sections(page, [PageSection(0, 75)])
    pdic, ocred = _publisher_fixture(tmp_path)
    events = []

    def save_then_external_edit(path, entries, width, pages):
        events.append("pdic")
        write_pdic(path, entries, width, pages)
        if change == "section":
            write_page_sections(page, [PageSection(0, 45)])
        elif change == "image":
            with Image.open(page) as opened:
                altered = opened.copy()
            altered.putpixel((0, 0), (0, 0, 0))
            altered.save(page)
        else:
            page.unlink()
        events.append("external-edit")

    def ocr(_image, entries, _settings, _rules, **kwargs):
        assert kwargs["page_sections"] == [PageSection(0, 75)]
        assert [(e.x, e.y) for e in entries] == [(17, 43)]
        return ["new-ocr"]

    deps = {
        "pdic_path": lambda p: p.with_suffix(".PDIC"),
        "read_pdic": read_pdic,
        "Image": Image,
        "normalize_page_rgb": lambda opened: opened.copy().convert("RGB"),
        "effective_page_settings": lambda s, _size, _index: s,
        "page_template_analysis_image": lambda image, _s, _i: image,
        "read_page_sections": read_page_sections,
        "sort_entries_reading_order": lambda entries, _geo, _sections: entries,
        "derive_geometry": lambda *_args: object(),
        "ocr_entries": ocr,
        "qt_root": lambda root: root / "QT",
        "export_ocred": export_ocred,
        "write_pdic": save_then_external_edit,
    }
    with pytest.raises(RuntimeError, match="PDIC 已保存，但保存期间页面来源") as exc:
        process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [],
            ("001", "@", "@"), deps=deps,
        )
    assert events == ["pdic", "external-edit"]
    assert "来源=" in str(exc.value)
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("new-ocr", 17, 43)
    ]
    assert ocred.read_bytes() == render_ocred_bytes(["new-ocr"])
    if change == "section":
        assert read_page_sections(page) == [PageSection(0, 45)]
    elif change == "image":
        with Image.open(page) as opened:
            assert opened.getpixel((0, 0)) == (0, 0, 0)
    else:
        assert not page.exists()


def test_uncontended_postcommit_context_check_runs_and_keeps_xy(tmp_path):
    pdic, ocred = _publisher_fixture(tmp_path)
    calls = []

    publish_existing_pdic_ocr(
        ocred, pdic, ["recognized"], [Entry("recognized", 17, 43)],
        100, ("001", "@", "@"),
        export_ocred=export_ocred,
        write_pdic=write_pdic,
        expected_exported_ocred_bytes=render_ocred_bytes(["recognized"]),
        validate_page_context=lambda: calls.append("check"),
    )
    assert calls == ["check", "check", "check"]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("recognized", 17, 43)
    ]
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])


def test_postcommit_page_context_read_failure_is_explicit(tmp_path):
    pdic, ocred = _publisher_fixture(tmp_path)
    calls = []

    def validate():
        calls.append("check")
        if len(calls) == 3:
            raise PermissionError("source scan unreadable")

    with pytest.raises(RuntimeError, match="PDIC 已保存，但保存期间页面来源") as exc:
        publish_existing_pdic_ocr(
            ocred, pdic, ["recognized"], [Entry("recognized", 17, 43)],
            100, ("001", "@", "@"),
            export_ocred=export_ocred,
            write_pdic=write_pdic,
            expected_exported_ocred_bytes=render_ocred_bytes(["recognized"]),
            validate_page_context=validate,
        )
    assert "source scan unreadable" in str(exc.value)
    assert len(calls) == 3
    assert read_pdic(pdic)[0].word == "recognized"
    assert ocred.read_bytes() == render_ocred_bytes(["recognized"])


def test_postcommit_context_check_follows_ocred_check_without_rollback():
    source = (
        Path(__file__).resolve().parents[1]
        / "src/picture_capture/ocr/batch_publication.py"
    ).read_text(encoding="utf-8")
    tail = source.split("if ocred_after_pdic != published_ocred:", 1)[1]
    assert "validate_page_context()" in tail
    assert "_restore_ocred" not in tail
