"""Focused batch crop cache cannot reuse pixels or SECTION/PDIC from stale files.

All fixtures use disposable synthetic image/sidecars. No real scanned pages.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.persistence.project_storage import (
    page_sections_read_path_for_image, pdic_path_for_image,
)
from picture_capture.ui import focused_filter_workflow as workflow


@dataclass
class _Settings:
    character_height: int = 18


def _fixture(tmp_path: Path):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (8, 8), "black").save(page)
    pdic = pdic_path_for_image(page)
    pdic.parent.mkdir(parents=True, exist_ok=True)
    pdic.write_bytes(b"old#3#4#1#1#001#@#@\n")
    section = page_sections_read_path_for_image(page)
    section.parent.mkdir(parents=True, exist_ok=True)
    section.write_bytes(b'{"revision":"A"}')

    target = {
        "page_index": 0, "page_name": page.name, "x": 3, "y": 4,
        "original_word": "old", "current_word": "old",
        "column_number": 1, "sequence_number": 1,
    }
    rendered, preloaded = [], []
    parent = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path, images=[page]),
        settings=_Settings(),
        canvas=SimpleNamespace(winfo_width=lambda: 700),
    )
    review = SimpleNamespace(
        parent=parent,
        filtered_targets=[target],
        filtered_batch_index=0,
        _filter_rows_active=True,
        _filter_scan_complete=True,
        _filter_save_running=False,
        _filter_pending_changes={},
        _filter_batch_render_cache={},
        _filter_prefetch_key=None,
        _filter_available_target_count=lambda: 1,
        _focused_batch_size=lambda: 1,
        _review_image_area_width=lambda: 640,
        review_zoom_auto=False,
        review_zoom=1.0,
        _update_filter_batch_indicator=lambda: None,
        _render_filter_batch=lambda targets, crops: rendered.append((targets, crops)),
        _reset_rows_scroll_top=lambda: None,
        _schedule_filter_next_batch_preload=lambda: preloaded.append(True),
    )
    deps = SimpleNamespace(replace=replace, _format_layout_percent=lambda value: str(value))
    review._filter_batch_snapshot = lambda index: workflow._filter_batch_snapshot(
        review, deps, index
    )
    return review, deps, page, pdic, section, rendered, preloaded


def _replace_bytes_preserving_mtime(path: Path, updated: bytes):
    stat = path.stat()
    assert len(updated) == stat.st_size
    path.write_bytes(updated)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert path.stat().st_size == stat.st_size
    assert path.stat().st_mtime_ns == stat.st_mtime_ns


@pytest.mark.parametrize("changed", ["image", "pdic", "section", "section_removed"])
def test_batch_source_signature_changes_even_without_mtime_or_size_change(
    tmp_path, changed,
):
    review, _deps, page, pdic, section, _rendered, _preloaded = _fixture(tmp_path)
    original_key = review._filter_batch_snapshot(0)[0]
    if changed == "image":
        # 24-bit BMP: equally sized, valid alternate source pixels.
        before = page.read_bytes()
        Image.new("RGB", (8, 8), "red").save(page)
        after = page.read_bytes()
        assert len(after) == len(before)
        _replace_bytes_preserving_mtime(page, before)
        _replace_bytes_preserving_mtime(page, after)
    elif changed == "pdic":
        _replace_bytes_preserving_mtime(pdic, b"new#3#4#1#1#001#@#@\n")
    elif changed == "section":
        _replace_bytes_preserving_mtime(section, b'{"revision":"B"}')
    else:
        section.unlink()
    new_key = review._filter_batch_snapshot(0)[0]
    assert new_key != original_key, (
        "crop cache reused a source from a different image/PDIC/SECTION"
    )


@pytest.mark.parametrize("changed", ["image", "pdic", "section"])
def test_stale_prefetched_payload_is_never_applied_after_file_replacement(tmp_path, changed):
    review, deps, page, pdic, section, rendered, preloaded = _fixture(tmp_path)
    cache_key = review._filter_batch_snapshot(0)[0]
    if changed == "image":
        before = page.stat()
        Image.new("RGB", (8, 8), "red").save(page)
        os.utime(page, ns=(before.st_atime_ns, before.st_mtime_ns))
    elif changed == "pdic":
        _replace_bytes_preserving_mtime(pdic, b"new#3#4#1#1#001#@#@\n")
    else:
        _replace_bytes_preserving_mtime(section, b'{"revision":"B"}')

    accepted = workflow._apply_filter_batch_payload(
        review, deps, 0, cache_key, ([object()], 1.0, [(7, 8)])
    )
    assert accepted is False
    assert rendered == [] and preloaded == []
    assert review.filtered_targets[0]["column_number"] == 1
    assert review.filtered_targets[0]["sequence_number"] == 1


def test_unchanged_batch_source_accepts_valid_payload(tmp_path):
    review, deps, _page, _pdic, _section, rendered, preloaded = _fixture(tmp_path)
    cache_key = review._filter_batch_snapshot(0)[0]
    assert workflow._apply_filter_batch_payload(
        review, deps, 0, cache_key, ([object()], 1.0, [(7, 8)])
    )
    assert len(rendered) == 1
    assert preloaded == [True]
    assert review.filtered_targets[0]["column_number"] == 7
    assert review.filtered_targets[0]["sequence_number"] == 8
