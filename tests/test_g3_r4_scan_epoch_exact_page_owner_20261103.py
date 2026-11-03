"""G3 R4.2 scan-source ownership must reject coerced page ids.

Disposable image/PDIC/OCR fixtures only. No actual dictionary pages, OCR, or writes
inside source-validation routines; preserve valid integer and no-witness ABI.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.persistence.project_storage import pdic_path_for_image
from picture_capture.proofreading.focused_crop_source_fingerprint import (
    focused_scan_source_witness,
)
from picture_capture.ui import focused_filter_workflow as workflow


def _sources(tmp_path):
    pages = [tmp_path / "001.bmp", tmp_path / "002.bmp"]
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    for page in pages:
        Image.new("RGB", (8, 8), "black").save(page)
        pdic_path_for_image(page).write_bytes(b"synthetic-only\n")
        (cache_root / f"{page.stem}.json").write_bytes(b"{}\n")
    deps = SimpleNamespace(
        pdic_path=pdic_path_for_image,
        ocr_cache_root=lambda _root: cache_root,
    )
    witnesses = {
        index: focused_scan_source_witness(
            page, pdic_path_for_image(page),
            cache_root / f"{page.stem}.json",
        )
        for index, page in enumerate(pages)
    }
    original_bytes = [
        (page.read_bytes(), pdic_path_for_image(page).read_bytes())
        for page in pages
    ]
    return pages, deps, witnesses, original_bytes


@pytest.mark.parametrize("invalid", [0.9, 1.9, True, False, "0", "1"])
@pytest.mark.parametrize("attested", [True, False])
def test_target_scan_source_cannot_alias_invalid_page_key(
    tmp_path, invalid, attested,
):
    pages, deps, witnesses, before = _sources(tmp_path)
    change = {"page_index": invalid}
    if attested:
        change["_focused_scan_source_witness"] = witnesses[int(invalid)]
    with pytest.raises(ValueError, match="page index"):
        workflow._focused_scan_target_source_signature(
            [change], pages, tmp_path, deps,
        )
    assert [
        (page.read_bytes(), pdic_path_for_image(page).read_bytes())
        for page in pages
    ] == before


@pytest.mark.parametrize("invalid", [0.9, 1.9, True, False, "0", "1"])
@pytest.mark.parametrize("complete", [False, True])
def test_active_scan_epoch_rejects_invalid_witness_key_at_any_phase(
    tmp_path, invalid, complete,
):
    pages, deps, witnesses, before = _sources(tmp_path)
    project = SimpleNamespace(root=tmp_path, images=pages)
    review = SimpleNamespace(
        parent=SimpleNamespace(project=project),
        _filter_scan_epoch_source_witnesses={invalid: witnesses[int(invalid)]},
        _filter_scan_epoch_invalidated=False,
        _filter_scan_epoch_source_serial=7,
        _filter_scan_serial=7,
        _filter_scan_epoch_project=project,
        _filter_scan_epoch_pages=tuple(pages),
        _filter_scan_epoch_project_root=tmp_path,
        _filter_scan_complete=complete,
    )
    assert workflow._verify_active_filter_scan_epoch_sources(review, deps) is False
    assert [
        (page.read_bytes(), pdic_path_for_image(page).read_bytes())
        for page in pages
    ] == before


@pytest.mark.parametrize("complete", [False, True])
def test_valid_integer_scan_epoch_source_keys_remain_accepted(tmp_path, complete):
    pages, deps, witnesses, _before = _sources(tmp_path)
    project = SimpleNamespace(root=tmp_path, images=pages)
    review = SimpleNamespace(
        parent=SimpleNamespace(project=project),
        _filter_scan_epoch_source_witnesses=dict(witnesses),
        _filter_scan_epoch_invalidated=False,
        _filter_scan_epoch_source_serial=7,
        _filter_scan_serial=7,
        _filter_scan_epoch_project=project,
        _filter_scan_epoch_pages=tuple(pages),
        _filter_scan_epoch_project_root=tmp_path,
        _filter_scan_complete=complete,
    )
    assert workflow._verify_active_filter_scan_epoch_sources(review, deps) is True


def test_valid_scan_target_witness_and_legacy_no_witness_still_work(tmp_path):
    pages, deps, witnesses, _before = _sources(tmp_path)
    assert workflow._focused_scan_target_source_signature(
        [{"page_index": 0, "_focused_scan_source_witness": witnesses[0]}],
        pages, tmp_path, deps,
    ) == ((0, witnesses[0]),)
    assert workflow._focused_scan_target_source_signature(
        [{"page_index": 1}], pages, tmp_path, deps,
    ) == ()
