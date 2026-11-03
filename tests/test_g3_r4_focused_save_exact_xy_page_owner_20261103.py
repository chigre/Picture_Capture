"""R4.2 focused PDIC writer: exact integer XY, page owner, and no-op batches.

Disposable tiny images and PDIC only; no project dictionary or OCR data.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.persistence.project_storage import pdic_path_for_image
from picture_capture.proofreading import focused_pdic_updates as owner


def _case(tmp_path):
    page = tmp_path / "001.bmp"
    sibling = tmp_path / "002.bmp"
    for path in (page, sibling):
        Image.new("RGB", (8, 8), "black").save(path)
    pdic = pdic_path_for_image(page)
    pdic.write_text("old#3#4#37.5#50#001#@#@\n", encoding="utf-8")
    untouched = pdic.read_bytes()
    writes = []

    def publish(path, rows, image_width, links):
        writes.append(1)
        write_pdic(path, rows, image_width, links)

    deps = owner.FocusedPdicDeps(
        pdic_path=pdic_path_for_image, read_pdic=read_pdic,
        replace=replace, Image=Image, _write_pdic_atomic=publish,
    )
    change = {
        "page_index": 0, "x": 3, "y": 4,
        "original_word": "old", "new_word": "edit",
    }

    def run(changes=None, *, page_arg=None, index=0):
        return owner.apply_focused_review_page_updates(
            page if page_arg is None else page_arg,
            [page, sibling], index,
            [change] if changes is None else changes, deps=deps,
        )

    return page, sibling, pdic, untouched, writes, change, run


@pytest.mark.parametrize(("field", "invalid"), [
    ("x", 3.9), ("y", 4.9),
    ("x", True), ("y", False),
    ("x", "3"), ("y", "4"),
])
def test_nonintegral_or_noninteger_xy_never_aliases_existing_marker(
    tmp_path, field, invalid,
):
    _page, _sibling, pdic, original, writes, change, run = _case(tmp_path)
    bad = dict(change, **{field: invalid})
    with pytest.raises(RuntimeError, match="(整数|坐标|XY|非法)"):
        run([bad])
    assert pdic.read_bytes() == original
    assert writes == []


@pytest.mark.parametrize("mode", ["wrong_page", "wrong_change_page", "out_of_range"])
def test_page_owner_conflict_refuses_before_publication(tmp_path, mode):
    page, _sibling, pdic, original, writes, change, run = _case(tmp_path)
    if mode == "wrong_page":
        invoke = lambda: run(page_arg=page, index=1)
    elif mode == "wrong_change_page":
        invoke = lambda: run([dict(change, page_index=1)])
    else:
        invoke = lambda: run(index=2)
    with pytest.raises(RuntimeError, match="(页面|页码|来源|归属)"):
        invoke()
    assert pdic.read_bytes() == original
    assert writes == []


def test_empty_batch_does_not_republish_pdic(tmp_path):
    _page, _sibling, pdic, original, writes, _change, run = _case(tmp_path)
    assert run([]) == ([], [])
    assert pdic.read_bytes() == original
    assert writes == []


def test_exact_integer_xy_and_correct_page_still_save(tmp_path):
    _page, _sibling, pdic, _original, writes, _change, run = _case(tmp_path)
    assert run() == ([(0, 3, 4, "edit")], [])
    assert writes == [1]
    assert [row.word for row in read_pdic(pdic)] == ["edit"]
