"""R3/R4.2: PDIC must not drift while the final image/SECTION witness runs.

Only disposable 8x8 BMP, synthetic PDIC, and a deterministic interleaving;
post-publication failure must never roll back or overwrite foreign bytes.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.persistence.project_storage import pdic_path_for_image
from picture_capture.proofreading import focused_pdic_updates as owner
from picture_capture.proofreading.focused_crop_source_fingerprint import (
    focused_save_source_witness,
)


def _case(tmp_path):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (8, 8), "black").save(page)
    pdic = pdic_path_for_image(page)
    pdic.write_text("old#3#4#37.5#50#001#@#@\n", encoding="utf-8")
    change = {
        "page_index": 0, "x": 3, "y": 4,
        "original_word": "old", "new_word": "edit",
        "_focused_save_source_witness": focused_save_source_witness(page),
    }
    writes = []

    def publish(path, rows, image_width, links):
        writes.append(1)
        write_pdic(path, rows, image_width, links)

    deps = owner.FocusedPdicDeps(
        pdic_path=pdic_path_for_image, read_pdic=read_pdic,
        replace=replace, Image=Image, _write_pdic_atomic=publish,
    )
    def run():
        return owner.apply_focused_review_page_updates(
            page, [page], 0, [change], deps=deps,
        )
    return page, pdic, writes, run


@pytest.mark.parametrize("foreign_bytes", [
    b"foreign#3#4#37.5#50#001#@#@\n",
    b"edit#3#4#37.5#50#001#@#@\nother#2#2#25#25#001#@#@\n",
])
def test_last_source_witness_cannot_mask_foreign_pdic_publication(
    tmp_path, monkeypatch, foreign_bytes,
):
    page, pdic, writes, run = _case(tmp_path)
    original_verify = owner.verify_focused_save_source
    checks = []

    def verify_with_interleaving(source_page, witness):
        checks.append(1)
        # The fourth verification follows the complete PDIC readback,
        # sidecar-field comparison, and coordinate validation.
        if len(checks) == 4:
            pdic.write_bytes(foreign_bytes)
        return original_verify(source_page, witness)

    monkeypatch.setattr(owner, "verify_focused_save_source", verify_with_interleaving)
    with pytest.raises(RuntimeError, match="(PDIC|保存后|变化|校验|拒绝)"):
        run()
    assert writes == [1] and len(checks) == 4
    assert pdic.read_bytes() == foreign_bytes  # No rollback of foreign bytes.
    assert focused_save_source_witness(page) is not None


def test_stable_final_witness_still_reports_success(tmp_path, monkeypatch):
    _page, pdic, writes, run = _case(tmp_path)
    original_verify = owner.verify_focused_save_source
    checks = []

    def unchanged(source_page, witness):
        checks.append(1)
        return original_verify(source_page, witness)

    monkeypatch.setattr(owner, "verify_focused_save_source", unchanged)
    assert run() == ([(0, 3, 4, "edit")], [])
    assert writes == [1] and len(checks) == 4
    assert [row.word for row in read_pdic(pdic)] == ["edit"]
