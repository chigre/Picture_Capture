"""Fail-first: filtered PDIC readback must verify all eight sidecar fields.

Word/X/Y/order integrity is necessary but not enough: a damaged percent
coordinate or navigation link can corrupt dictionaries while the edited
word itself still looks correct in the GUI. Use the real PDIC serializer
and mutate only post-publication metadata, with no rollback expected.
"""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.proofreading.focused_pdic_updates import (
    FocusedPdicDeps, apply_focused_review_page_updates,
)


class _Image:
    width = 200
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


def _case(tmp_path, mutator=None):
    pages = [tmp_path / name for name in ("001.png", "002.png", "003.png")]
    pages[1].write_bytes(b"source-image-stub")
    pdic = tmp_path / "002.pdic"
    pdic.write_text(
        "甲#10#20#5#10#002#001#003\n"
        "丙#30#40#15#20#002#001#003\n", encoding="utf-8",
    )
    calls = []
    def writer(path, rows, width, links):
        calls.append(1)
        result = write_pdic(path, rows, width, links)
        if mutator:
            current = path.read_text(encoding="utf-8")
            path.write_text(mutator(current), encoding="utf-8")
        return result
    deps = FocusedPdicDeps(
        pdic_path=lambda _page: pdic,
        read_pdic=read_pdic,
        replace=replace,
        Image=SimpleNamespace(open=lambda _path: _Image()),
        _write_pdic_atomic=writer,
    )
    def run():
        return apply_focused_review_page_updates(
            pages[1], pages, 1,
            [{"page_index": 1, "x": 10, "y": 20,
              "original_word": "甲", "new_word": "乙"}],
            deps=deps,
        )
    return SimpleNamespace(run=run, pdic=pdic, calls=calls)


def _mutate_field(text, row, field, new):
    lines = text.splitlines()
    cells = lines[row].split("#")
    cells[field] = new
    lines[row] = "#".join(cells)
    return "\n".join(lines) + "\n"


def test_unchanged_eight_field_pdic_write_still_succeeds(tmp_path):
    x = _case(tmp_path)
    assert x.run() == ([(1, 10, 20, "乙")], [])
    assert x.calls == [1]
    assert x.pdic.read_text(encoding="utf-8").splitlines() == [
        "乙#10#20#5#10#002#001#003",
        "丙#30#40#15#20#002#001#003",
    ]


@pytest.mark.parametrize("row,field,new", [
    (1, 3, "99"),         # unedited row's original-image x percent
    (0, 4, "83.5"),       # edited row's original-image y percent
    (1, 5, "wrongpage"),  # unedited row current-page link
    (0, 6, "wrongprev"),  # edited row previous-page link
    (1, 7, "wrongnext"),  # unedited row next-page link
])
def test_metadata_corrupted_after_write_is_reported_as_failure(tmp_path, row, field, new):
    x = _case(
        tmp_path,
        lambda text: _mutate_field(text, row, field, new),
    )
    with pytest.raises(RuntimeError, match="(保存后|校验|变化|不一致)"):
        x.run()
    assert x.calls == [1]  # never roll back onto another writer's bytes
    fields = x.pdic.read_text(encoding="utf-8").splitlines()[row].split("#")
    assert fields[field] == new


def test_actual_pdic_record_remains_eight_fields(tmp_path):
    x = _case(tmp_path)
    x.run()
    assert all(len(line.split("#")) == 8
               for line in x.pdic.read_text(encoding="utf-8").splitlines())
