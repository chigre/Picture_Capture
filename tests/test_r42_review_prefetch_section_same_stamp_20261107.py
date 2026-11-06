"""Synthetic R4.2 SECTION same-size/same-mtime replacement witness.

SECTION is read into a sorted row-order snapshot. Independent managed-project
copy/sync tools can preserve a sidecar's size and mtime across different bytes.
Only synthetic PIL page and synthetic SECTION v2 sidecar under pytest tmp_path.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from threading import Lock

from PIL import Image

from picture_capture.persistence.page_sections import PageSection, write_page_sections
from picture_capture.persistence.project_storage import page_sections_read_path_for_image
from picture_capture.ui import review_page_lifecycle as lifecycle


def _fixture(tmp_path):
    page = tmp_path / "section_stamp.png"
    Image.new("RGB", (80, 100), "white").save(page)
    deps = SimpleNamespace(
        json=SimpleNamespace(),
        ocr_cache_root=lambda root: root / "QT" / "PaddleOCR",
        ppp_read_path_for_image=lambda path: path.with_suffix(".ppp"),
        pdic_path=lambda path: path.with_suffix(".pdic"),
    )
    review = SimpleNamespace(
        parent=SimpleNamespace(project=SimpleNamespace(root=tmp_path, images=[page])),
        _prefetch_lock=Lock(), _prefetched_pages={},
        _review_prefetch_key=lambda: ("same review settings",),
    )
    review._prefetch_path_signature = lambda path: lifecycle._prefetch_path_signature(
        deps, path
    )
    review._page_prefetch_signature_for = lambda root, path: lifecycle._page_prefetch_signature_for(
        review, deps, root, path
    )
    review._page_prefetch_signature = lambda path: lifecycle._page_prefetch_signature(
        review, deps, path
    )
    return page, review, deps


def _rewrite_preserving_stamp(page, *, top):
    sidecar = page_sections_read_path_for_image(page)
    old_bytes = sidecar.read_bytes()
    stat = sidecar.stat()
    write_page_sections(page, [PageSection(0, top)])
    new_bytes = sidecar.read_bytes()
    assert old_bytes != new_bytes
    assert len(new_bytes) == len(old_bytes), "test must not depend on file-size metadata"
    os.utime(sidecar, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    after = sidecar.stat()
    assert after.st_size == stat.st_size
    assert after.st_mtime_ns == stat.st_mtime_ns


def test_same_stamp_changed_section_bytes_must_invalidate_worker_signature(tmp_path):
    page, review, _deps = _fixture(tmp_path)
    write_page_sections(page, [PageSection(0, 80)])
    original = review._page_prefetch_signature(page)
    _rewrite_preserving_stamp(page, top=60)
    updated = review._page_prefetch_signature(page)
    assert updated != original, "SECTION exact-byte change was concealed by stable size/mtime"


def test_same_stamp_changed_section_bytes_must_reject_cached_page_on_take(tmp_path):
    page, review, deps = _fixture(tmp_path)
    write_page_sections(page, [PageSection(0, 80)])
    old_key = review._page_prefetch_signature(page)
    review._prefetched_pages[0] = dict(
        project_root=str(tmp_path), signature=old_key,
        review_key=review._review_prefetch_key(), sentinel="stale reading order",
    )
    _rewrite_preserving_stamp(page, top=60)
    assert lifecycle._take_prefetched_page(review, deps, 0) is None


def test_identical_section_bytes_remain_acceptable_cache_hit(tmp_path):
    page, review, deps = _fixture(tmp_path)
    write_page_sections(page, [PageSection(0, 80)])
    old = review._page_prefetch_signature(page)
    review._prefetched_pages[0] = dict(
        project_root=str(tmp_path), signature=old,
        review_key=review._review_prefetch_key(), sentinel="unchanged",
    )
    found = lifecycle._take_prefetched_page(review, deps, 0)
    assert found is not None and found["sentinel"] == "unchanged"
