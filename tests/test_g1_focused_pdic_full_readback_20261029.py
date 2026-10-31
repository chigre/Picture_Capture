"""G1 fail-first: verify the whole PDIC image after a focused page write.

The writer previously verified count and *planned* coordinates only. A
foreign process can change another row or reorder rows yet the filtered
UI reports success, even though the published page is not our snapshot.
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


def _writer_case(tmp_path, publish):
    page = tmp_path / "001.png"
    page.write_bytes(b"source-image-stub")
    pdic = tmp_path / "001.pdic"
    pdic.write_text(
        "甲#10#20#5#10#001#@#@\n"
        "丙#30#40#15#20#001#@#@\n",
        encoding="utf-8",
    )
    counts = []
    def write(path, entries, width, links):
        counts.append(1)
        return publish(path, entries, width, links)
    deps = FocusedPdicDeps(
        pdic_path=lambda _: pdic,
        read_pdic=read_pdic,
        replace=replace,
        Image=SimpleNamespace(open=lambda _: _Image()),
        _write_pdic_atomic=write,
    )
    def run():
        return apply_focused_review_page_updates(
            page, [page], 0,
            [{"page_index": 0, "x": 10, "y": 20,
              "original_word": "甲", "new_word": "乙"}],
            deps=deps,
        )
    return pdic, run, counts


def _normal(path, entries, width, links):
    return write_pdic(path, entries, width, links)


def test_clean_readback_verifies_full_page_and_reports_saved(tmp_path):
    pdic, run, calls = _writer_case(tmp_path, _normal)
    saved, conflicts = run()
    assert saved == [(0, 10, 20, "乙")]
    assert conflicts == []
    assert calls == [1]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("乙", 10, 20), ("丙", 30, 40),
    ]


def test_unrelated_row_text_changed_after_publication_is_detected(tmp_path):
    def foreign(path, entries, width, links):
        changed = [replace(e) for e in entries]
        changed[1].word = "外部修改"
        return write_pdic(path, changed, width, links)
    pdic, run, calls = _writer_case(tmp_path, foreign)
    with pytest.raises(RuntimeError, match="(保存后|校验|一致|变化)"):
        run()
    assert calls == [1]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("乙", 10, 20), ("外部修改", 30, 40),
    ]


def test_unrelated_row_coordinate_drift_after_publication_is_detected(tmp_path):
    def foreign(path, entries, width, links):
        changed = [replace(e) for e in entries]
        changed[1].x = 31
        return write_pdic(path, changed, width, links)
    pdic, run, calls = _writer_case(tmp_path, foreign)
    with pytest.raises(RuntimeError, match="(保存后|校验|一致|变化)"):
        run()
    assert calls == [1]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("乙", 10, 20), ("丙", 31, 40),
    ]


def test_row_reorder_after_publication_is_not_mistaken_for_our_write(tmp_path):
    def foreign(path, entries, width, links):
        return write_pdic(path, list(reversed(entries)), width, links)
    pdic, run, calls = _writer_case(tmp_path, foreign)
    with pytest.raises(RuntimeError, match="(保存后|校验|一致|变化)"):
        run()
    assert calls == [1]
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic)] == [
        ("丙", 30, 40), ("乙", 10, 20),
    ]
