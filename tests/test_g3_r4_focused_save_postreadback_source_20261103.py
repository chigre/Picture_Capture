"""R3/R4.2: fail first if image/SECTION changes during PDIC readback.

Only disposable 8x8 BMP, synthetic eight-field PDIC and SECTION bytes.
Post-publication refusal must not be mistaken for a rollback/transaction.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.persistence.project_storage import (
    page_sections_read_path_for_image, pdic_path_for_image,
)
from picture_capture.proofreading.focused_crop_source_fingerprint import (
    focused_save_source_witness,
)
from picture_capture.proofreading.focused_pdic_updates import (
    FocusedPdicDeps, apply_focused_review_page_updates,
)


def _case(tmp_path, *, drift=None, attested=True):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (8, 8), "black").save(page)
    pdic = pdic_path_for_image(page)
    pdic.write_text("old#3#4#37.5#50#001#@#@\n", encoding="utf-8")
    section = page_sections_read_path_for_image(page)
    if drift != "section_created":
        section.parent.mkdir(parents=True, exist_ok=True)
        section.write_bytes(b'{"revision":"A"}')
    source = focused_save_source_witness(page)
    reads, writes = [], []

    def read_with_interleaving(path):
        rows = read_pdic(path)
        reads.append(1)
        # The first read builds the working copy; the second is the
        # post-publication readback, after the existing source check.
        if len(reads) == 2:
            if drift == "section_replaced":
                section.write_bytes(b'{"revision":"B"}')
            elif drift == "section_removed":
                section.unlink()
            elif drift == "section_created":
                section.parent.mkdir(parents=True, exist_ok=True)
                section.write_bytes(b'{"revision":"B"}')
            elif drift == "image_replaced":
                Image.new("RGB", (8, 8), "red").save(page)
        return rows

    def publish(path, rows, image_width, links):
        writes.append(1)
        write_pdic(path, rows, image_width, links)

    deps = FocusedPdicDeps(
        pdic_path=pdic_path_for_image,
        read_pdic=read_with_interleaving,
        replace=replace,
        Image=Image,
        _write_pdic_atomic=publish,
    )
    change = {
        "page_index": 0, "x": 3, "y": 4,
        "original_word": "old", "new_word": "edit",
    }
    if attested:
        change["_focused_save_source_witness"] = source

    def run():
        return apply_focused_review_page_updates(
            page, [page], 0, [change], deps=deps,
        )
    return run, page, pdic, source, reads, writes


@pytest.mark.parametrize(
    "drift",
    ["section_replaced", "section_removed", "section_created", "image_replaced"],
)
def test_postwrite_readback_source_drift_refuses_success_without_rollback(
    tmp_path, drift,
):
    run, page, pdic, source, reads, writes = _case(tmp_path, drift=drift)
    with pytest.raises(RuntimeError, match="(来源|SECTION|变化|拒绝)"):
        run()

    assert reads == [1, 1] and writes == [1]
    assert focused_save_source_witness(page) != source
    # Publication already happened. A fail-closed result must never
    # blindly overwrite that file while pretending to roll back.
    assert [row.word for row in read_pdic(pdic)] == ["edit"]


@pytest.mark.parametrize("attested", [True, False])
def test_unchanged_readback_source_preserves_valid_and_legacy_saves(
    tmp_path, attested,
):
    run, page, pdic, source, reads, writes = _case(
        tmp_path, attested=attested,
    )
    planned, conflicts = run()

    assert planned == [(0, 3, 4, "edit")] and conflicts == []
    assert reads == [1, 1] and writes == [1]
    assert [row.word for row in read_pdic(pdic)] == ["edit"]
    assert focused_save_source_witness(page) == source
