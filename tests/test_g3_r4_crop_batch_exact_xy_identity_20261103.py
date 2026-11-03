"""R4.2: a crop cache or off-Tk worker cannot alias malformed source XY.

All files are synthetic 8x8 BMP/PDIC; no real operator/source data.
This is a RED-first test-only artifact, not passing gate evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.persistence.project_storage import pdic_path_for_image
from picture_capture.ui import focused_filter_workflow as workflow


@dataclass
class _Settings:
    character_height: int = 18


def _case(tmp_path: Path):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (8, 8), "black").save(page)
    pdic = pdic_path_for_image(page)
    pdic.parent.mkdir(parents=True, exist_ok=True)
    pdic.write_bytes(b"old#3#4#37.5#50#001#@#@\n")
    target = {
        "page_index": 0, "x": 3, "y": 4, "original_word": "old",
        "current_word": "old",
    }
    review = SimpleNamespace(
        parent=SimpleNamespace(
            project=SimpleNamespace(root=tmp_path, images=[page]),
            settings=_Settings(),
            canvas=SimpleNamespace(winfo_width=lambda: 700),
        ),
        filtered_targets=[target],
        _filter_scan_complete=True,
        _filter_available_target_count=lambda: 1,
        _focused_batch_size=lambda: 1,
        _review_image_area_width=lambda: 600,
        review_zoom_auto=False,
        review_zoom=1.0,
    )
    snap_deps = SimpleNamespace(replace=replace)
    crop_deps = SimpleNamespace(
        read_pdic=lambda path: [SimpleNamespace(x=3, y=4, word="old")],
        pdic_path=pdic_path_for_image,
        normalize_page_rgb=lambda opened: opened.convert("RGB"),
        _review_crop_context=lambda *args: (object(), object()),
        sort_entries_reading_order=lambda entries, *_: entries,
        read_page_sections=lambda page: [],
        column_index=lambda *args: 0,
        _review_line_box=lambda *args: (0, 0, 5, 5),
        review_auto_fit_zoom=lambda *args: 1.0,
        Image=Image,
    )
    return page, pdic, target, review, snap_deps, crop_deps


@pytest.mark.parametrize(("field", "invalid"), [
    ("x", 3.9), ("x", "3"), ("x", True),
    ("y", 4.9), ("y", "4"), ("y", False),
])
def test_crop_snapshot_rejects_noninteger_xy_before_cache_key(tmp_path, field, invalid):
    page, pdic, target, review, deps, _crop_deps = _case(tmp_path)
    original_image, original_pdic = page.read_bytes(), pdic.read_bytes()
    target[field] = invalid

    # A cache key that silently maps 3.9 to 3 can own the wrong thumbnail.
    assert workflow._filter_batch_snapshot(review, deps, 0) is None
    assert page.read_bytes() == original_image
    assert pdic.read_bytes() == original_pdic
    assert target[field] == invalid


@pytest.mark.parametrize(("field", "invalid"), [
    ("page_index", 0.9), ("page_index", "0"), ("page_index", False),
    ("page_index", -1),
    ("x", 3.9), ("x", "3"), ("x", True),
    ("y", 4.9), ("y", "4"), ("y", False),
])
def test_offthread_crop_worker_rejects_untrusted_page_or_xy(tmp_path, field, invalid):
    page, pdic, target, _review, _deps, crop_deps = _case(tmp_path)
    before = (page.read_bytes(), pdic.read_bytes())
    target[field] = invalid

    with pytest.raises((ValueError, RuntimeError)):
        workflow._prepare_filter_batch_payload(
            crop_deps, [target], [page], _Settings(), 700, 600, 1.0, False,
        )
    assert (page.read_bytes(), pdic.read_bytes()) == before


def test_valid_integer_snapshot_and_crop_worker_keep_original_geometry(tmp_path):
    page, pdic, target, review, snap_deps, crop_deps = _case(tmp_path)
    original_image, original_pdic = page.read_bytes(), pdic.read_bytes()

    snapshot = workflow._filter_batch_snapshot(review, snap_deps, 0)
    assert snapshot is not None
    cache_key, selected, *_rest = snapshot
    assert cache_key[1][0] == ((0, 3, 4, "old"),)
    assert selected[0]["x"] == 3 and selected[0]["y"] == 4

    crops, zoom, display_meta = workflow._prepare_filter_batch_payload(
        crop_deps, [target], [page], _Settings(), 700, 600, 1.0, False,
    )
    assert len(crops) == 1 and crops[0].size == (5, 5)
    assert zoom == 1.0 and display_meta == [(1, 1)]
    assert (page.read_bytes(), pdic.read_bytes()) == (original_image, original_pdic)
