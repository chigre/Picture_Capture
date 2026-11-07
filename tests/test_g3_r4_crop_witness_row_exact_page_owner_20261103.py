"""R3/R4.2: a crop witness row must have an exact integer page owner.

Disposable 8x8 BMP and PDIC bytes only; no user data or live OCR.
The displayed crop's page row is part of the save-source authority: Python
bool/float equality must not transfer it to another page identity.
"""
from __future__ import annotations

import pytest
from PIL import Image

from picture_capture.persistence.project_storage import pdic_path_for_image
from picture_capture.proofreading.focused_crop_source_fingerprint import (
    focused_crop_source_witness,
    focused_save_source_from_crop_witness,
    focused_save_source_witness,
    verify_focused_save_source,
)


def _pages(tmp_path):
    pages = [tmp_path / "001.bmp", tmp_path / "002.bmp"]
    for page in pages:
        Image.new("RGB", (8, 8), "black").save(page)
        pdic_path_for_image(page).write_text(
            "synthetic#3#4#37.5#50#001#@#@\n", encoding="utf-8"
        )
    return pages


@pytest.mark.parametrize(
    ("owner_page", "malformed_row_page"),
    [(0, False), (1, True), (0, 0.0), (1, 1.0)],
)
def test_malformed_crop_row_cannot_authorize_save_page(
    tmp_path, owner_page, malformed_row_page,
):
    pages = _pages(tmp_path)
    authentic = focused_crop_source_witness(
        pages, [{"page_index": owner_page}]
    )
    assert len(authentic[1]) == 1
    row = authentic[1][0]
    # Change only the row's *type*, not its page's image or SECTION bytes.
    malformed = (authentic[0], ((malformed_row_page, *row[1:]),))
    assert focused_save_source_from_crop_witness(
        malformed, owner_page
    ) is None, "boolean/floating crop row must not confer exact page ownership"


@pytest.mark.parametrize("owner_page", [0, 1])
def test_true_integer_crop_row_preserves_valid_save_source(tmp_path, owner_page):
    pages = _pages(tmp_path)
    authentic = focused_crop_source_witness(
        pages, [{"page_index": owner_page}]
    )
    accepted = focused_save_source_from_crop_witness(authentic, owner_page)
    assert accepted == focused_save_source_witness(pages[owner_page])
    verify_focused_save_source(pages[owner_page], accepted)


def test_other_integer_page_row_is_not_accepted(tmp_path):
    pages = _pages(tmp_path)
    first_page = focused_crop_source_witness(
        pages, [{"page_index": 0}]
    )
    assert focused_save_source_from_crop_witness(first_page, 1) is None
