"""Regression: postproduction line image exports must not create .PSWords.

Legacy single-line/CLI callers retain the optional manifest by default;
the 后期制作 page worker explicitly opts out of that compatibility artifact.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture import processing_core
from picture_capture.single_line_merge_settings import merge_page_line_images


@pytest.mark.parametrize("has_entry", [True, False])
def test_manifest_free_single_line_page_cleans_old_pswords(tmp_path, monkeypatch, has_entry):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (40, 30), "white").save(image_path)
    output_dir = tmp_path / "QT" / "PSW"
    output_dir.mkdir(parents=True)

    legacy = output_dir / "page.PSWords"
    legacy.write_text("old contents\n", encoding="utf-8")
    stale = output_dir / "page_SW_999.png"
    Image.new("RGB", (1, 1), "black").save(stale)

    monkeypatch.setattr(
        processing_core, "_page_geometry_context",
        lambda image, settings, page_index: (image, settings, None, object()),
    )
    monkeypatch.setattr(
        processing_core, "sort_entries_reading_order",
        lambda entries, geometry, sections: list(entries),
    )
    monkeypatch.setattr(
        processing_core, "line_box",
        lambda entry, geometry, source, effective: (2, 3, 20, 16),
    )
    entries = [SimpleNamespace(word="alpha")] if has_entry else []
    records = processing_core.split_single_lines(
        image_path, entries, object(), output_dir,
        page_sections=[], write_manifest=False,
    )
    assert len(records) == (1 if has_entry else 0)
    assert not legacy.exists()
    assert not stale.exists()
    assert (output_dir / "page_SW_000.png").exists() is has_entry
    assert not list(output_dir.glob("*.PSWords"))


def test_legacy_manifest_default_remains_available(tmp_path, monkeypatch):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (40, 30), "white").save(image_path)
    output_dir = tmp_path / "QT" / "PSW"
    output_dir.mkdir(parents=True)
    monkeypatch.setattr(
        processing_core, "_page_geometry_context",
        lambda image, settings, page_index: (image, settings, None, object()),
    )
    monkeypatch.setattr(
        processing_core, "sort_entries_reading_order",
        lambda entries, geometry, sections: list(entries),
    )
    monkeypatch.setattr(
        processing_core, "line_box",
        lambda entry, geometry, source, effective: (2, 3, 20, 16),
    )
    processing_core.split_single_lines(
        image_path, [SimpleNamespace(word="alpha")], object(), output_dir,
        page_sections=[],
    )
    assert (output_dir / "page.PSWords").read_text(encoding="utf-8") == (
        "page_SW_000.png\n"
    )


@pytest.mark.parametrize("blank", [True, False])
def test_manifest_free_page_merge_never_leaves_pswords(tmp_path, blank):
    output_dir = tmp_path / "QT" / "PSW"
    output_dir.mkdir(parents=True)
    page = tmp_path / "page.jpg"
    first = output_dir / "page_SW_000.png"
    Image.new("RGB", (12, 8), "white" if blank else "black").save(first)
    legacy = output_dir / "page.PSWords"
    legacy.write_text(first.name + "\n", encoding="utf-8")
    result = merge_page_line_images(
        page, [SimpleNamespace(filename=first.name)], output_dir,
        write_manifest=False,
    )
    assert result == (None if blank else output_dir / "page_SW_PAGE.png")
    assert not legacy.exists()
    assert not first.exists()
    assert not list(output_dir.glob("*.PSWords"))
