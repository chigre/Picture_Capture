"""G3 R4.2 crop/source provenance must not truncate untrusted page indexes.

All source files are disposable; no real OCR, dictionary or sidecar payload.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from picture_capture.persistence.project_storage import pdic_path_for_image
from picture_capture.proofreading.focused_crop_source_fingerprint import (
    focused_crop_source_witness,
    focused_save_source_from_crop_witness,
    focused_save_source_witness,
)


def _pages(tmp_path):
    pages = [tmp_path / "001.bmp", tmp_path / "002.bmp"]
    for page in pages:
        Image.new("RGB", (8, 8), "black").save(page)
        pdic_path_for_image(page).write_bytes(b"synthetic-source\n")
    return pages


@pytest.mark.parametrize("invalid", [0.9, 1.9, True, False, "0", "1"])
def test_crop_attestation_rejects_noninteger_page_identity(tmp_path, invalid):
    pages = _pages(tmp_path)
    before = [(page.read_bytes(), pdic_path_for_image(page).read_bytes()) for page in pages]
    with pytest.raises(ValueError, match="page index"):
        focused_crop_source_witness(pages, [{"page_index": invalid}])
    assert [(page.read_bytes(), pdic_path_for_image(page).read_bytes()) for page in pages] == before


@pytest.mark.parametrize("invalid", [0.9, 1.9, True, False, "0", "1"])
def test_save_witness_cannot_inherit_truncated_crop_page(tmp_path, invalid):
    pages = _pages(tmp_path)
    crop = focused_crop_source_witness(
        pages, [{"page_index": 0}, {"page_index": 1}],
    )
    assert focused_save_source_from_crop_witness(crop, invalid) is None
    assert focused_save_source_from_crop_witness(crop, 0) == focused_save_source_witness(pages[0])
    assert focused_save_source_from_crop_witness(crop, 1) == focused_save_source_witness(pages[1])


def test_provenance_consumer_passes_raw_page_identity_without_coercion():
    ui = (
        Path(__file__).resolve().parents[1]
        / "src/picture_capture/ui/focused_filter_workflow.py"
    ).read_text(encoding="utf-8")
    assert 'source_witness, target["page_index"]' in ui
    assert 'source_witness, int(target["page_index"])' not in ui


def test_integral_crop_page_targets_remain_attestable(tmp_path):
    pages = _pages(tmp_path)
    witness = focused_crop_source_witness(
        pages, [{"page_index": 1}, {"page_index": 0}, {"page_index": 1}],
    )
    assert witness[0] == "focused-crop-source-v1"
    assert tuple(row[0] for row in witness[1]) == (0, 1)
    assert focused_save_source_from_crop_witness(witness, 0) is not None
    assert focused_save_source_from_crop_witness(witness, 1) is not None
