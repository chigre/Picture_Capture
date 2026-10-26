"""Round 100: SECTION edits during a slow source-image hash must be detected.

The source fingerprint may be expensive for large scans. Checking SECTION
only *before* the hash leaves a stale-reading-order window even when PDIC
and OCRed have not changed. Exercise both publication checkpoints using
the real page worker and real sidecar serializers.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ocr import batch_existing_entries as worker
from picture_capture.ocr.text_io import export_ocred, render_ocred_bytes
from picture_capture.persistence.page_sections import (
    PageSection, read_page_sections, write_page_sections,
)
from picture_capture.persistence.project_storage import (
    page_sections_read_path_for_image,
)


PAGES = ("001", "@", "@")
ORIGINAL_OCRED = b"\xef\xbb\xbf000|`reviewed-before\r\n"


def _run_page(tmp_path, *, write_callback):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (100, 120), "white").save(page)
    write_page_sections(page, [PageSection(0, 75)])
    pdic = page.with_suffix(".PDIC")
    write_pdic(pdic, [Entry("old", 17, 43)], 100, PAGES)
    ocred = tmp_path / "QT" / "001.OCRed"
    ocred.parent.mkdir(parents=True)
    ocred.write_bytes(ORIGINAL_OCRED)

    def ocr(_image, entries, _settings, _rules, **kwargs):
        assert kwargs["page_sections"] == [PageSection(0, 75)]
        assert [(entry.x, entry.y) for entry in entries] == [(17, 43)]
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
        "write_pdic": write_callback,
    }
    return page, pdic, ocred, deps


@pytest.mark.parametrize("phase,hash_call", [
    ("precommit", 4),
    ("postcommit", 5),
])
@pytest.mark.parametrize("mutation", ["rewrite", "remove"])
def test_section_mutated_during_image_hash_is_not_silent(
    tmp_path, monkeypatch, phase, hash_call, mutation,
):
    writes = []

    def save(path, entries, width, pages):
        writes.append(True)
        write_pdic(path, entries, width, pages)

    page, pdic, ocred, deps = _run_page(tmp_path, write_callback=save)
    original_pdic = pdic.read_bytes()
    real_hash = worker._source_image_sha256
    hash_calls = []

    def hash_then_mutate(path: Path):
        result = real_hash(path)
        hash_calls.append(True)
        if len(hash_calls) == hash_call:
            if mutation == "rewrite":
                write_page_sections(page, [PageSection(0, 45)])
            else:
                page_sections_read_path_for_image(page).unlink()
        return result

    monkeypatch.setattr(worker, "_source_image_sha256", hash_then_mutate)
    if phase == "precommit":
        expected_message = "SECTION"
    else:
        expected_message = "PDIC 已保存，但保存期间页面来源"

    with pytest.raises(RuntimeError, match=expected_message):
        worker.process_existing_pdic_page(
            page, 0, tmp_path, SimpleNamespace(), [], PAGES, deps=deps,
        )

    assert len(hash_calls) == hash_call
    assert len(writes) == (0 if phase == "precommit" else 1)
    if phase == "precommit":
        assert pdic.read_bytes() == original_pdic
        assert ocred.read_bytes() == ORIGINAL_OCRED
        assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
            ("old", 17, 43),
        ]
    else:
        assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
            ("new-ocr", 17, 43),
        ]
        assert ocred.read_bytes() == render_ocred_bytes(["new-ocr"])

    if mutation == "rewrite":
        assert read_page_sections(page) == [PageSection(0, 45)]
    else:
        assert not page_sections_read_path_for_image(page).exists()
    assert not list(ocred.parent.glob(".001.OCRed.*.tmp"))


def test_unchanged_section_survives_all_five_image_hashes(tmp_path, monkeypatch):
    writes = []

    def save(path, entries, width, pages):
        writes.append(True)
        write_pdic(path, entries, width, pages)

    page, pdic, ocred, deps = _run_page(tmp_path, write_callback=save)
    real_hash = worker._source_image_sha256
    hash_calls = []

    def count_hash(path):
        hash_calls.append(True)
        return real_hash(path)

    monkeypatch.setattr(worker, "_source_image_sha256", count_hash)
    assert worker.process_existing_pdic_page(
        page, 0, tmp_path, SimpleNamespace(), [], PAGES, deps=deps,
    ) == 1
    assert len(hash_calls) == 5
    assert len(writes) == 1
    assert read_page_sections(page) == [PageSection(0, 75)]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("new-ocr", 17, 43),
    ]
    assert ocred.read_bytes() == render_ocred_bytes(["new-ocr"])
