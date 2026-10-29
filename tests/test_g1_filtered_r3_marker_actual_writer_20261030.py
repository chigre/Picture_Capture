"""G1 fail-first: actual PDIC restore writer may bypass a target R3 journal.

The serializer is called for a *temporary* PDIC filename. It checks the
temporary file's R3 marker, whereas the unresolved transaction belongs
to the real target. Both existing markers and ones appearing during
staging must preserve the target's byte-for-byte contents.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.io.formats import read_pdic
from picture_capture.models import Entry
from picture_capture.proofreading import pdic_restore
from picture_capture.proofreading.focused_pdic_updates import (
    FocusedPdicDeps,
    apply_focused_review_page_updates,
)


class _Opened:
    width = 100
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


def _case(tmp_path):
    page = tmp_path / "001.png"
    page.write_bytes(b"source-image-stub")
    target = tmp_path / "001.pdic"
    original = b"\xe7\x94\xb2#10#20#10#20#001#@#@\n"
    target.write_bytes(original)
    marker = target.with_name(f".{target.name}.r3-inflight.json")
    deps = FocusedPdicDeps(
        pdic_path=lambda _: target,
        read_pdic=read_pdic,
        replace=replace,
        Image=SimpleNamespace(open=lambda _: _Opened()),
        _write_pdic_atomic=pdic_restore.write_pdic_atomic,
    )
    def filtered_save():
        return apply_focused_review_page_updates(
            page, [page], 0,
            [{"page_index": 0, "x": 10, "y": 20,
              "original_word": "甲", "new_word": "乙"}],
            deps=deps,
        )
    return target, marker, original, filtered_save


def test_live_filtered_writer_refuses_existing_target_r3_marker(tmp_path):
    target, marker, original, save = _case(tmp_path)
    marker.write_bytes(b'{"unresolved":"leave intact"}')
    with pytest.raises(RuntimeError, match="(R3|marker|恢复|事务)"):
        save()
    assert target.read_bytes() == original
    assert marker.read_bytes() == b'{"unresolved":"leave intact"}'
    assert not target.with_name(f".{target.name}.restore.tmp").exists()


def test_writer_refuses_marker_created_during_temp_staging(tmp_path, monkeypatch):
    target, marker, original, _ = _case(tmp_path)
    real_write = pdic_restore.write_pdic
    stages = []
    def stage_then_announce_recovery(path, entries, width, links):
        stages.append(path)
        result = real_write(path, entries, width, links)
        marker.write_bytes(b"recovery still in progress")
        return result
    monkeypatch.setattr(pdic_restore, "write_pdic", stage_then_announce_recovery)
    with pytest.raises(RuntimeError, match="(R3|marker|恢复|事务)"):
        pdic_restore.write_pdic_atomic(
            target, [Entry(word="乙", x=10, y=20)], 100, ("001", "@", "@"),
        )
    assert len(stages) == 1
    assert target.read_bytes() == original
    assert marker.read_bytes() == b"recovery still in progress"
    assert not target.with_name(f".{target.name}.restore.tmp").exists()


def test_dangling_symlink_r3_marker_is_not_treated_as_absent(tmp_path):
    target, marker, original, save = _case(tmp_path)
    try:
        marker.symlink_to("missing-recovery-journal.json")
    except (OSError, NotImplementedError):
        pytest.skip("OS does not permit symlink construction")
    with pytest.raises(RuntimeError, match="(R3|marker|恢复|事务)"):
        save()
    assert marker.is_symlink()
    assert target.read_bytes() == original


def test_unmarked_actual_writer_still_saves_clean_pdic(tmp_path):
    target, marker, _, save = _case(tmp_path)
    assert save() == ([(0, 10, 20, "乙")], [])
    assert [(entry.word, entry.x, entry.y) for entry in read_pdic(target)] == [
        ("乙", 10, 20),
    ]
    assert not marker.exists()
