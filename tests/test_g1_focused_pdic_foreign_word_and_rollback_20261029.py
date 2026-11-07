"""G1 fail-first: filtered PDIC writer protects original words and foreign bytes.

A unique original-image X/Y coordinate does not prove the dictionary word
still belongs to this UI edit. Exercise actual PDIC read/serialize and use
bounded writer stubs only to interleave a second disk writer deterministically.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.proofreading.focused_pdic_updates import (
    FocusedPdicDeps, apply_focused_review_page_updates,
)


class ImageOpened:
    width = 100

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _setup(tmp_path, *, before="甲", on_image_open=None, writer=None):
    page = tmp_path / "001.png"
    page.write_bytes(b"source-image-stub")
    path = tmp_path / "001.pdic"
    path.write_text(f"{before}#10#20#10#20#001#@#@\n", encoding="utf-8")
    calls = []
    def write(target, entries, width, pages):
        calls.append([entry.word for entry in entries])
        if writer:
            return writer(target, entries, width, pages)
        return write_pdic(target, entries, width, pages)
    def image_open(page_path):
        if on_image_open:
            on_image_open(path)
        return ImageOpened()
    deps = FocusedPdicDeps(
        pdic_path=lambda _: path,
        read_pdic=read_pdic,
        replace=replace,
        Image=SimpleNamespace(open=image_open),
        _write_pdic_atomic=write,
    )
    def run(*changes):
        return apply_focused_review_page_updates(
            page, [page], 0, list(changes), deps=deps,
        )
    def change(original="甲", new="乙", x=10, y=20):
        return {
            "page_index": 0, "x": x, "y": y,
            "original_word": original, "new_word": new,
        }
    return SimpleNamespace(path=path, run=run, change=change, calls=calls)


def test_unique_xy_with_foreign_word_is_conflict_not_overwrite(tmp_path):
    f = _setup(tmp_path, before="外部更新")
    baseline = f.path.read_bytes()
    saved, conflicts = f.run(f.change(original="甲", new="乙"))
    assert saved == []
    assert len(conflicts) == 1
    assert f.path.read_bytes() == baseline
    assert f.calls == []


def test_one_stale_edit_blocks_all_other_edits_on_same_page(tmp_path):
    f = _setup(tmp_path, before="外部更新")
    # A valid edit to a second original-image coordinate must not be
    # partially published if one edit on the same page is stale.
    f.path.write_text(
        "外部更新#10#20#10#20#001#@#@\n"
        "丙#30#40#30#40#001#@#@\n", encoding="utf-8",
    )
    baseline = f.path.read_bytes()
    saved, conflicts = f.run(
        f.change(original="甲", new="乙"),
        f.change(original="丙", new="丁", x=30, y=40),
    )
    assert saved == [] and conflicts
    assert f.calls == []
    assert f.path.read_bytes() == baseline


def test_matching_original_word_still_saves_exact_coordinate(tmp_path):
    f = _setup(tmp_path)
    saved, conflicts = f.run(f.change())
    assert saved == [(0, 10, 20, "乙")]
    assert conflicts == []
    assert f.calls == [["乙"]]
    assert [(e.x, e.y, e.word) for e in read_pdic(f.path)] == [(10, 20, "乙")]


def test_external_disk_change_during_image_open_is_not_overwritten(tmp_path):
    def concurrent_update(path):
        path.write_text("外部更新#10#20#10#20#001#@#@\n", encoding="utf-8")
    f = _setup(tmp_path, on_image_open=concurrent_update)
    with pytest.raises(RuntimeError, match="(changed|变化|修改|conflict|冲突)"):
        f.run(f.change())
    assert f.calls == []
    assert [entry.word for entry in read_pdic(f.path)] == ["外部更新"]


def test_writer_exception_does_not_rollback_over_foreign_commit(tmp_path):
    call_count = []
    def concurrent_writer(path, entries, width, pages):
        call_count.append(1)
        if len(call_count) == 1:
            path.write_text("第三方#10#20#10#20#001#@#@\n", encoding="utf-8")
            raise OSError("simulated write ambiguity")
        # A blind rollback is an unauthorized foreign-file overwrite.
        return write_pdic(path, entries, width, pages)
    f = _setup(tmp_path, writer=concurrent_writer)
    with pytest.raises(OSError, match="ambiguity"):
        f.run(f.change())
    assert len(call_count) == 1
    assert [entry.word for entry in read_pdic(f.path)] == ["第三方"]


def test_postwrite_verification_failure_never_blindly_restores_old_file(tmp_path):
    calls = []
    def concurrent_writer(path, entries, width, pages):
        calls.append(1)
        if len(calls) == 1:
            path.write_text("另一位校对者#10#20#10#20#001#@#@\n", encoding="utf-8")
            return True
        return write_pdic(path, entries, width, pages)
    f = _setup(tmp_path, writer=concurrent_writer)
    with pytest.raises(RuntimeError, match="校验失败"):
        f.run(f.change())
    assert len(calls) == 1
    assert [entry.word for entry in read_pdic(f.path)] == ["另一位校对者"]
