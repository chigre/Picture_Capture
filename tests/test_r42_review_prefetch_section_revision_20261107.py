"""Synthetic R4.2 SECTION revision owner regression for ReviewWindow prefetch.

A cached page has SECTION-sorted Entry rows. A SECTION rewrite, removal or
first appearance must invalidate those cached rows even if the source image,
PDIC, PPP and OCR cache did not change. No real project/scans or OCR used.
"""
from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from types import SimpleNamespace

from PIL import Image
import pytest

from picture_capture.persistence.page_sections import PageSection, write_page_sections
from picture_capture.persistence.project_storage import page_sections_read_path_for_image
from picture_capture.ui import review_page_lifecycle as lifecycle


def _fixture(tmp_path):
    page = tmp_path / "synthetic.png"
    Image.new("RGB", (100, 120), "white").save(page)
    deps = SimpleNamespace(
        ocr_cache_root=lambda root: root / "QT" / "PaddleOCR",
        ppp_read_path_for_image=lambda image: image.with_suffix(".ppp"),
        pdic_path=lambda image: image.with_suffix(".pdic"),
    )
    parent = SimpleNamespace(project=SimpleNamespace(root=tmp_path, images=[page]))
    review = SimpleNamespace(
        parent=parent,
        _prefetch_lock=Lock(),
        _prefetched_pages={},
    )
    review._prefetch_path_signature = lambda path: lifecycle._prefetch_path_signature(
        deps, path
    )
    review._page_prefetch_signature = lambda image: lifecycle._page_prefetch_signature(
        review, deps, image
    )
    review._review_prefetch_key = lambda: ("synthetic-unchanged-settings",)
    return review, deps, page


def _pin_section_mtime(page, seconds):
    sidecar = page_sections_read_path_for_image(page)
    os.utime(sidecar, ns=(seconds * 10**9, seconds * 10**9))


@pytest.mark.parametrize("mutation", ["rewrite", "remove"])
def test_section_change_revises_prefetch_signature_without_pdic_or_image_change(
    tmp_path, mutation,
):
    review, _deps, page = _fixture(tmp_path)
    write_page_sections(page, [PageSection(0, 80)])
    _pin_section_mtime(page, 1_600_000_000)
    before = review._page_prefetch_signature(page)

    if mutation == "rewrite":
        write_page_sections(page, [PageSection(0, 45), PageSection(45, 100)])
        _pin_section_mtime(page, 1_600_000_050)
    else:
        page_sections_read_path_for_image(page).unlink()
    after = review._page_prefetch_signature(page)

    assert before != after, "SECTION revision must invalidate prefetched row order"


def test_new_section_sidecar_invalidates_cached_page_at_consume(tmp_path):
    review, deps, page = _fixture(tmp_path)
    old_signature = review._page_prefetch_signature(page)
    review._prefetched_pages[0] = {
        "project_root": str(tmp_path),
        "signature": old_signature,
        "review_key": review._review_prefetch_key(),
        "sentinel": "stale-entry-order",
    }
    write_page_sections(page, [PageSection(0, 80)])
    assert lifecycle._take_prefetched_page(review, deps, 0) is None


def test_unchanged_section_allows_same_owner_cached_page(tmp_path):
    review, deps, page = _fixture(tmp_path)
    write_page_sections(page, [PageSection(0, 80)])
    signature = review._page_prefetch_signature(page)
    review._prefetched_pages[0] = {
        "project_root": str(tmp_path),
        "signature": signature,
        "review_key": review._review_prefetch_key(),
        "sentinel": "safe-entry-order",
    }
    selected = lifecycle._take_prefetched_page(review, deps, 0)
    assert selected is not None and selected["sentinel"] == "safe-entry-order"
