"""Lined and unlined postproduction exports share refinement illustration whitening.

The mask is temporary, opt-in and never rewrites scan/PPP/PDIC. This tests the
actual image saved, rather than merely checking that a helper was called.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture import layout_illustration_mask, processing_core, unlined_line_export
from picture_capture.models import AppSettings


def _scan(path: Path) -> None:
    image = Image.new("RGB", (40, 36), "white")
    image.paste((0, 0, 0), (10, 10, 16, 16))
    image.save(path)
    image.close()


def _mask_spy(monkeypatch):
    calls = []

    def mask(image, settings, *, profile_page_index, **kwargs):
        calls.append((int(profile_page_index), kwargs))
        result = image.copy()
        result.paste((255, 255, 255), (10, 10, 16, 16))
        return result, object()

    monkeypatch.setattr(layout_illustration_mask, "mask_large_illustrations_for_layout", mask)
    return calls


@pytest.mark.parametrize("reuse", [False, True])
def test_lined_png_uses_refinement_mask_without_editing_source(tmp_path, monkeypatch, reuse):
    page = tmp_path / "page.png"
    _scan(page)
    original = page.read_bytes()
    settings = AppSettings()
    settings.layout_mask_illustrations = True
    settings.layout_mask_illustrations_use_existing = reuse
    calls = _mask_spy(monkeypatch)

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
        lambda entry, geometry, source, effective: (5, 5, 25, 25),
    )

    output = tmp_path / "PSW"
    records = processing_core.split_single_lines(
        page, [SimpleNamespace(word="head")], settings, output,
        profile_page_index=4, page_sections=[], write_manifest=False,
    )

    assert len(records) == 1
    with Image.open(output / "page_SW_000.png") as exported:
        assert exported.getpixel((6, 6)) == (255, 255, 255)
    assert calls == [(4, {"source_image_path": page} if reuse else {})]
    assert page.read_bytes() == original
    assert not list(tmp_path.glob("*.PPP"))
    assert not list(tmp_path.glob("*.PSWords"))


@pytest.mark.parametrize("enabled,merge", [(True, False), (True, True), (False, False)])
def test_unlined_layout_and_png_see_same_temporary_mask(
    tmp_path, monkeypatch, enabled, merge,
):
    page = tmp_path / "page.png"
    _scan(page)
    original = page.read_bytes()
    settings = AppSettings()
    settings.layout_mask_illustrations = enabled
    settings.layout_mask_illustrations_use_existing = False
    calls = _mask_spy(monkeypatch)
    seen = []

    monkeypatch.setattr(unlined_line_export.formats, "read_pdic", lambda path: [])
    monkeypatch.setattr(unlined_line_export, "read_page_sections", lambda path: [])
    def resolve(root, path, image, settings, *, page_index):
        seen.append((page_index, image.getpixel((11, 11))))
        return object(), "fast_projection"
    monkeypatch.setattr(unlined_line_export, "resolve_unlined_physical_rows", resolve)
    monkeypatch.setattr(
        unlined_line_export, "unlined_rows_from_layout",
        lambda layout, entries, sections, *, crop_width_percent: (
            [unlined_line_export.UnlinedRow(0, 0, "body", (5, 5, 25, 25), 0)],
            1, 0,
        ),
    )

    result = unlined_line_export.export_unlined_page_job(
        tmp_path, page, 2, settings, merge, False, False, 50.0,
    )

    assert result.exported_images == 1
    assert seen == [(2, (255, 255, 255) if enabled else (0, 0, 0))]
    assert calls == ([(2, {})] if enabled else [])
    output = tmp_path / "QT" / "PSW_UNLINED"
    target = output / ("page_UL_PAGE.png" if merge else "page_UL_000.png")
    with Image.open(target) as exported:
        if enabled:
            assert exported.getpixel((6, 6)) == (255, 255, 255)
        else:
            assert exported.getpixel((0, 0)) == (0, 0, 0)
    assert page.read_bytes() == original
    assert not list(tmp_path.glob("*.PPP"))
