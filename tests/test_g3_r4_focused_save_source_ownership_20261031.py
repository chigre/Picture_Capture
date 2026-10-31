"""G3 R4.2: a human correction owns its displayed image and SECTION source.

Deterministic synthetic 8x8 BMP and PDIC; no real scans or operator E3.
"""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.persistence.project_storage import (
    page_sections_read_path_for_image, pdic_path_for_image,
)
from picture_capture.proofreading.focused_crop_source_fingerprint import (
    focused_crop_source_witness,
)
from picture_capture.proofreading.focused_pdic_updates import (
    FocusedPdicDeps, apply_focused_review_page_updates,
)
from picture_capture.ui import focused_filter_workflow as flow


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _files(tmp_path: Path):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (8, 8), "black").save(page)
    pdic = pdic_path_for_image(page)
    pdic.write_bytes(b"old#3#4#37.5#50#001#@#@\n")
    section = page_sections_read_path_for_image(page)
    section.parent.mkdir(parents=True, exist_ok=True)
    section.write_bytes(b'{"revision":"A"}')
    target = {
        "page_index": 0, "page_name": page.name, "x": 3, "y": 4,
        "original_word": "old", "current_word": "old",
        "column_number": 1, "sequence_number": 1,
    }
    crop_witness = focused_crop_source_witness([page], [target])
    return page, pdic, section, target, crop_witness


def _replace_without_metadata_change(path: Path, new_content: bytes):
    old_stat = path.stat()
    assert len(new_content) == old_stat.st_size
    path.write_bytes(new_content)
    os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    assert path.stat().st_size == old_stat.st_size
    assert path.stat().st_mtime_ns == old_stat.st_mtime_ns


def _alter(tmp_path: Path, changed: str, page: Path, section: Path):
    if changed == "image":
        replacement = tmp_path / "replacement.bmp"
        Image.new("RGB", (8, 8), "red").save(replacement)
        _replace_without_metadata_change(page, replacement.read_bytes())
    elif changed == "section":
        _replace_without_metadata_change(section, b'{"revision":"B"}')
    elif changed == "section_removed":
        section.unlink()
    else:
        raise AssertionError(changed)


def _save_deps(page: Path, save_count: list):
    pdic_deps = FocusedPdicDeps(
        pdic_path=pdic_path_for_image,
        read_pdic=read_pdic,
        replace=replace,
        Image=Image,
        _write_pdic_atomic=lambda *args: (
            save_count.append(1), write_pdic(*args)
        )[-1],
    )
    def commit(the_page, pages, index, changes):
        return apply_focused_review_page_updates(
            the_page, pages, index, changes, deps=pdic_deps
        )
    alerts = []
    return SimpleNamespace(
        _apply_focused_review_page_updates=commit,
        messagebox=SimpleNamespace(
            showerror=lambda title, message, **kw: alerts.append((title, message)),
        ),
    ), alerts


def _review(page: Path, target: dict):
    calls = []
    parent = SimpleNamespace(
        project=SimpleNamespace(images=[page]),
        current_index=0,
        entries=[SimpleNamespace(
            word="old", x=3, y=4, confidence=0.5,
            ocr_source="ocr", final_engine="ocr", manually_selected=False,
        )],
        status_var=_Var(),
        _start_ui_worker=lambda *args, **kw: calls.append((args, kw)),
    )
    review = SimpleNamespace(
        parent=parent,
        _filter_rows_active=True,
        filtered_targets=[target],
        _filter_pending_changes={},
        _filter_save_job=None,
        _filter_save_running=False,
        _filter_close_after_save=True,
        _focused_timing_session=None,
    )
    return review, calls


def _edited_change(witness, *, word="edit-1"):
    return {
        "page_index": 0, "x": 3, "y": 4,
        "original_word": "old", "new_word": word,
        "_focused_save_source_witness": witness,
    }


def _save_witness(crop_witness):
    # Image and SECTION, excluding PDIC, which our own valid edit changes.
    row = crop_witness[1][0]
    return ("focused-save-source-v1", row[1], row[3])


def test_rendered_batch_binds_actual_source_to_human_change(tmp_path):
    page, _pdic, _section, target, crop_witness = _files(tmp_path)
    key = (0, (("source",), crop_witness))
    rendered = []
    review, _calls = _review(page, target)
    review.filtered_batch_index = 0
    review.review_zoom_auto = False
    review._focused_batch_size = lambda: 1
    review._filter_available_target_count = lambda: 1
    review._filter_batch_snapshot = lambda _: (
        key, [dict(target)], [page], None, 700, 640, 1.0, False
    )
    review._update_filter_batch_indicator = lambda: None
    review._render_filter_batch = lambda targets, crops: rendered.append(targets)
    review._reset_rows_scroll_top = lambda: None
    review._schedule_filter_next_batch_preload = lambda: None
    assert flow._apply_filter_batch_payload(
        review, SimpleNamespace(_format_layout_percent=str),
        0, key, ([object()], 1.0, [(1, 1)])
    )
    assert rendered and target["_focused_save_source_witness"] == _save_witness(
        crop_witness
    )
    timers = []
    review.after = lambda ms, fn: timers.append(ms) or "save"
    review._flush_focused_changes = lambda: None
    flow._queue_focused_change(
        review, SimpleNamespace(tk=SimpleNamespace(TclError=Exception)),
        target, "edit-1",
    )
    assert timers == [160]
    assert review._filter_pending_changes[0][(3, 4)][
        "_focused_save_source_witness"
    ] == _save_witness(crop_witness)


@pytest.mark.parametrize("changed", ["image", "section", "section_removed"])
@pytest.mark.parametrize("newer_edit", [False, True])
def test_source_changed_after_display_before_worker_preserves_human_edits(
    tmp_path, changed, newer_edit,
):
    page, pdic, section, target, crop_witness = _files(tmp_path)
    expected = _save_witness(crop_witness)
    review, calls = _review(page, target)
    target["current_word"] = "edit-1"
    review._filter_pending_changes[0] = {
        (3, 4): _edited_change(expected)
    }
    writes = []
    deps, alerts = _save_deps(page, writes)
    # Bind the production ReviewWindow owner method on this lightweight
    # synthetic object: done() schedules it when a newer edit exists.
    review._flush_focused_changes = lambda: flow._flush_focused_changes(review, deps)
    flow._flush_focused_changes(review, deps)
    assert len(calls) == 1 and review._filter_pending_changes == {}
    _name, worker, _done, failed = calls[0][0]
    old_pdic_bytes = pdic.read_bytes()
    if newer_edit:
        target["current_word"] = "edit-2"
        review._filter_pending_changes[0] = {
            (3, 4): _edited_change(expected, word="edit-2")
        }
    _alter(tmp_path, changed, page, section)
    with pytest.raises(RuntimeError, match="(来源|变化|拒绝|SECTION)"):
        worker()
    failed(RuntimeError("PRIVATE_IMAGE_HEADWORD_PATH"), "PRIVATE_TRACE")
    assert writes == [] and pdic.read_bytes() == old_pdic_bytes
    assert review._filter_save_running is False
    assert review._filter_close_after_save is False
    assert target["original_word"] == "old"
    assert review._filter_pending_changes[0][(3, 4)]["new_word"] == (
        "edit-2" if newer_edit else "edit-1"
    )
    assert len(alerts) == 1
    assert "PRIVATE_" not in (
        parent_output := review.parent.status_var.get() + str(alerts)
    )


def test_unchanged_attested_source_saves_exact_human_edit(tmp_path):
    page, pdic, _section, target, crop_witness = _files(tmp_path)
    review, calls = _review(page, target)
    review._filter_close_after_save = False
    review.after = lambda ms, callback: "next"
    review._finish_close_review = lambda: None
    target["current_word"] = "edit-1"
    review._filter_pending_changes[0] = {
        (3, 4): _edited_change(_save_witness(crop_witness))
    }
    writes = []
    deps, _alerts = _save_deps(page, writes)
    flow._flush_focused_changes(review, deps)
    _name, worker, done, _failed = calls[0][0]
    done(worker())
    assert writes == [1]
    assert read_pdic(pdic)[0].word == "edit-1"
    assert target["original_word"] == "edit-1"
    assert review._filter_pending_changes == {}


def test_writer_rechecks_source_after_pdic_read_before_publication(tmp_path):
    page, pdic, section, _target, crop_witness = _files(tmp_path)
    original_pdic = pdic.read_bytes()
    writes = []
    def read_pdic_during_save(path):
        rows = read_pdic(path)
        # Simulates an external SECTION update after initial provenance
        # checks/PDIC parse, but before _write_pdic_atomic publication.
        _replace_without_metadata_change(section, b'{"revision":"B"}')
        return rows
    deps = FocusedPdicDeps(
        pdic_path=pdic_path_for_image, read_pdic=read_pdic_during_save,
        replace=replace, Image=Image,
        _write_pdic_atomic=lambda *a: writes.append(a),
    )
    with pytest.raises(RuntimeError, match="(来源|变化|拒绝|SECTION)"):
        apply_focused_review_page_updates(
            page, [page], 0,
            [_edited_change(_save_witness(crop_witness))], deps=deps,
        )
    assert writes == []
    assert pdic.read_bytes() == original_pdic


def test_missing_render_provenance_cannot_publish_live_filter_edits(tmp_path):
    page, pdic, _section, target, _crop_witness = _files(tmp_path)
    before = pdic.read_bytes()
    review, calls = _review(page, target)
    review._filter_pending_changes[0] = {
        (3, 4): {k: v for k, v in _edited_change(None).items()
                 if k != "_focused_save_source_witness"}
    }
    writes = []
    deps, _alerts = _save_deps(page, writes)
    flow._flush_focused_changes(review, deps)
    worker = calls[0][0][1]
    with pytest.raises(RuntimeError, match="(来源|校验|拒绝)"):
        worker()
    assert writes == [] and pdic.read_bytes() == before


def test_stale_second_page_blocks_first_page_before_any_pdic_publication(tmp_path):
    # All-page preflight matters: otherwise saving page 1 before discovering
    # a stale SECTION on page 2 is an avoidable partial publication.
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    p1, d1, _s1, t1, c1 = _files(first)
    p2, d2, s2, t2, c2 = _files(second)
    t1["current_word"] = "edit-1"
    t2.update(page_index=1, current_word="edit-2")
    review, calls = _review(p1, t1)
    review.parent.project.images = [p1, p2]
    review.filtered_targets = [t1, t2]
    review._filter_pending_changes = {
        0: {(3, 4): _edited_change(_save_witness(c1))},
        1: {(3, 4): {**_edited_change(_save_witness(c2), word="edit-2"),
                     "page_index": 1}},
    }
    baseline = (d1.read_bytes(), d2.read_bytes())
    writes = []
    deps, _alerts = _save_deps(p1, writes)
    flow._flush_focused_changes(review, deps)
    _alter(second, "section", p2, s2)
    _name, worker, _done, failed = calls[0][0]
    with pytest.raises(RuntimeError, match="(来源|变化|拒绝|SECTION)"):
        worker()
    failed(RuntimeError("private pathname"), "private traceback")
    assert writes == []
    assert (d1.read_bytes(), d2.read_bytes()) == baseline
    assert set(review._filter_pending_changes) == {0, 1}
    assert review._filter_pending_changes[0][(3, 4)]["new_word"] == "edit-1"
    assert review._filter_pending_changes[1][(3, 4)]["new_word"] == "edit-2"
    assert not review._filter_close_after_save


def test_new_section_after_originally_sectionless_crop_fails_closed(tmp_path):
    page, pdic, section, target, _ignored = _files(tmp_path)
    section.unlink()
    source = _save_witness(focused_crop_source_witness([page], [target]))
    before = pdic.read_bytes()
    target["current_word"] = "edit-1"
    review, calls = _review(page, target)
    review._filter_pending_changes = {(0): {(3, 4): _edited_change(source)}}
    writes = []
    deps, _alerts = _save_deps(page, writes)
    flow._flush_focused_changes(review, deps)
    section.write_bytes(b'{"revision":"A"}')
    worker = calls[0][0][1]
    with pytest.raises(RuntimeError, match="(来源|变化|拒绝|SECTION)"):
        worker()
    assert writes == [] and pdic.read_bytes() == before


def test_inflight_reversion_reuses_display_witness_and_saves_after_first_commit(tmp_path):
    """User changes back to pre-write text while an older worker runs.

    The older snapshot writes edit-1; done() must queue 'old' relative to
    the newly saved word *with the accepted crop witness*, not mint one
    from the current disk at save time. The second worker must succeed.
    """
    page, pdic, _section, target, crop = _files(tmp_path)
    witness = _save_witness(crop)
    target.update(current_word="edit-1", _focused_save_source_witness=witness)
    review, calls = _review(page, target)
    review._filter_close_after_save = False
    timers = []
    review.after = lambda ms, fn: timers.append((ms, fn)) or "scheduled"
    review._finish_close_review = lambda: None
    review._filter_pending_changes = {0: {(3, 4): _edited_change(witness)}}
    writes = []
    deps, alerts = _save_deps(page, writes)
    review._flush_focused_changes = lambda: flow._flush_focused_changes(review, deps)

    flow._flush_focused_changes(review, deps)
    _name, worker, done, failed = calls[0][0]
    assert review._filter_save_running and not review._filter_pending_changes

    # Real Tk's StringVar trace cancels the old queued edit on reversion,
    # leaving no newer pending row while the first worker still owns disk.
    target["current_word"] = "old"
    done(worker())
    assert not alerts and writes == [1]
    assert read_pdic(pdic)[0].word == "edit-1"
    change = review._filter_pending_changes[0][(3, 4)]
    assert change["original_word"] == "edit-1"
    assert change["new_word"] == "old"
    assert change["_focused_save_source_witness"] == witness
    assert any(ms == 1 for ms, _fn in timers)

    flow._flush_focused_changes(review, deps)
    assert len(calls) == 2
    _name, worker2, done2, failed2 = calls[1][0]
    done2(worker2())
    assert not alerts and writes == [1, 1]
    assert not review._filter_pending_changes
    assert read_pdic(pdic)[0].word == "old"
    assert target["original_word"] == target["current_word"] == "old"


def test_inflight_reversion_cannot_bypass_changed_section_with_retained_witness(tmp_path):
    """A restored queue retains the OLD proof and still rejects later drift."""
    page, pdic, section, target, crop = _files(tmp_path)
    witness = _save_witness(crop)
    target.update(current_word="edit-1", _focused_save_source_witness=witness)
    review, calls = _review(page, target)
    review._filter_close_after_save = False
    review.after = lambda ms, fn: "scheduled"
    review._filter_pending_changes = {0: {(3, 4): _edited_change(witness)}}
    writes = []
    deps, alerts = _save_deps(page, writes)
    review._flush_focused_changes = lambda: flow._flush_focused_changes(review, deps)

    flow._flush_focused_changes(review, deps)
    _name, worker, done, failed = calls[0][0]
    target["current_word"] = "old"
    done(worker())
    assert read_pdic(pdic)[0].word == "edit-1"
    assert review._filter_pending_changes[0][(3, 4)][
        "_focused_save_source_witness"
    ] == witness

    _replace_without_metadata_change(section, b'{"revision":"B"}')
    unchanged_pdic = pdic.read_bytes()
    flow._flush_focused_changes(review, deps)
    _name, worker2, done2, failed2 = calls[1][0]
    with pytest.raises(RuntimeError, match="(来源|变化|拒绝|SECTION)"):
        worker2()
    failed2(RuntimeError("PRIVATE_PAGE_PATH"), "PRIVATE_TRACE")
    assert writes == [1] and pdic.read_bytes() == unchanged_pdic
    assert review._filter_pending_changes[0][(3, 4)]["new_word"] == "old"
    assert not review._filter_close_after_save
    assert alerts and "PRIVATE_" not in str(alerts)


def test_newer_inflight_edit_maintains_original_crop_witness_after_save(tmp_path):
    """A new edit queued during the worker retains its stronger ownership."""
    page, pdic, _section, target, crop = _files(tmp_path)
    witness = _save_witness(crop)
    target.update(current_word="edit-1", _focused_save_source_witness=witness)
    review, calls = _review(page, target)
    review._filter_close_after_save = False
    review.after = lambda ms, fn: "scheduled"
    review._filter_pending_changes = {0: {(3, 4): _edited_change(witness)}}
    writes = []
    deps, alerts = _save_deps(page, writes)
    # Bind the production ReviewWindow owner method on this lightweight
    # synthetic object: done() schedules it when a newer edit exists.
    review._flush_focused_changes = lambda: flow._flush_focused_changes(review, deps)
    flow._flush_focused_changes(review, deps)
    _name, worker, done, _failed = calls[0][0]
    target["current_word"] = "edit-2"
    review._filter_pending_changes[0] = {
        (3, 4): _edited_change(witness, word="edit-2"),
    }
    done(worker())
    queued = review._filter_pending_changes[0][(3, 4)]
    assert queued["original_word"] == "edit-1"
    assert queued["new_word"] == "edit-2"
    assert queued["_focused_save_source_witness"] == witness

    flow._flush_focused_changes(review, deps)
    _name, worker2, done2, _failed2 = calls[1][0]
    done2(worker2())
    assert not review._filter_pending_changes and not alerts
    assert read_pdic(pdic)[0].word == "edit-2"
    assert writes == [1, 1]


def _two_attested_pages(tmp_path):
    """Two separate synthetic directories, avoiding any real scan/word data."""
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    p1, d1, _s1, t1, c1 = _files(first)
    p2, d2, _s2, t2, c2 = _files(second)
    t1.update(
        current_word="edit-one",
        _focused_save_source_witness=_save_witness(c1),
    )
    t2.update(
        page_index=1, current_word="edit-two",
        _focused_save_source_witness=_save_witness(c2),
    )
    review, calls = _review(p1, t1)
    review.parent.project.images = [p1, p2]
    review.filtered_targets = [t1, t2]
    review._filter_pending_changes = {
        0: {(3, 4): _edited_change(_save_witness(c1), word="edit-one")},
        1: {(3, 4): {
            **_edited_change(_save_witness(c2), word="edit-two"),
            "page_index": 1,
        }},
    }
    return (p1, d1, t1), (p2, d2, t2), review, calls


def test_two_page_pdic_conflict_commits_first_once_preserves_second(tmp_path):
    """A page-2 word conflict must not requeue a committed page-1 row.

    Image/SECTION preflight passes for both pages. A foreign PDIC word
    change (which is deliberately excluded from the crop witness) instead
    causes a *per-page* writer conflict, not an all-page provenance error.
    """
    (p1, d1, t1), (p2, d2, t2), review, calls = _two_attested_pages(tmp_path)
    # External PDIC edit is intentionally after display attestation; page 2
    # must remain the foreign owner's data, not our stale human correction.
    foreign = b"external#3#4#37.5#50#001#@#@\n"
    d2.write_bytes(foreign)
    before_second = d2.read_bytes()
    writes, alerts = [], []
    deps, failures = _save_deps(p1, writes)
    deps.messagebox.showwarning = lambda title, message, **kw: alerts.append(
        (title, message)
    )

    flow._flush_focused_changes(review, deps)
    _name, worker, done, failed = calls[0][0]
    saved, conflicts = worker()
    assert saved == [(0, 3, 4, "edit-one")]
    assert len(conflicts) == 1 and "原词已变化" in conflicts[0]
    done((saved, conflicts))

    assert writes == [1]
    assert read_pdic(d1)[0].word == "edit-one"
    assert d2.read_bytes() == before_second
    assert t1["original_word"] == t1["current_word"] == "edit-one"
    assert t2["original_word"] == "old" and t2["current_word"] == "edit-two"
    assert 0 not in review._filter_pending_changes
    assert review._filter_pending_changes[1][(3, 4)]["new_word"] == "edit-two"
    assert review._filter_pending_changes[1][(3, 4)][
        "_focused_save_source_witness"
    ] == t2["_focused_save_source_witness"]
    assert not review._filter_save_running and not review._filter_close_after_save
    assert len(alerts) == 1 and not failures
    assert "已保存 1 条修改" in review.parent.status_var.get()
    assert "1 条冲突" in review.parent.status_var.get()
    assert review.parent.entries[0].word == "edit-one"
    assert (review.parent.entries[0].x, review.parent.entries[0].y) == (3, 4)

    # Even an explicit retry of the remaining unsaved page must NEVER
    # republish page 1 or overwrite the foreign text at page 2.
    committed_first = d1.read_bytes()
    flow._flush_focused_changes(review, deps)
    _name, worker2, done2, failed2 = calls[1][0]
    saved2, conflicts2 = worker2()
    assert saved2 == [] and len(conflicts2) == 1
    done2((saved2, conflicts2))
    assert writes == [1] and d1.read_bytes() == committed_first
    assert d2.read_bytes() == before_second
    assert 0 not in review._filter_pending_changes
    assert review._filter_pending_changes[1][(3, 4)]["new_word"] == "edit-two"
    assert len(alerts) == 2 and not failures


def test_two_page_late_writer_error_keeps_uncertain_edits_no_rollback(tmp_path):
    """Page 2 can fail *after* page 1 commits, even after all-page preflight.

    The callback has no durable, authoritative all-page commit journal; it
    must report failure, retain both human edits and NEVER roll back page 1
    over a potentially newer writer or falsely mark page 1 as confirmed.
    """
    (p1, d1, t1), (_p2, d2, t2), review, calls = _two_attested_pages(tmp_path)
    before_second = d2.read_bytes()
    writes = []
    deps, alerts = _save_deps(p1, writes)
    real_writer = deps._apply_focused_review_page_updates

    def late_failure(page, pages, index, changes):
        if index == 1:
            raise OSError("PRIVATE_SECOND_PAGE_PATH_NEVER_DISPLAY")
        return real_writer(page, pages, index, changes)

    deps._apply_focused_review_page_updates = late_failure
    flow._flush_focused_changes(review, deps)
    _name, worker, done, failed = calls[0][0]
    with pytest.raises(OSError, match="PRIVATE_SECOND_PAGE_PATH"):
        worker()
    assert writes == [1] and read_pdic(d1)[0].word == "edit-one"
    assert d2.read_bytes() == before_second

    failed(
        OSError("PRIVATE_SECOND_PAGE_PATH_NEVER_DISPLAY"),
        "PRIVATE_SECOND_PAGE_TRACEBACK",
    )
    assert not review._filter_save_running and not review._filter_close_after_save
    # Conservative uncertainty: never silently discard the second page or
    # classify the first page as durably reported by a failed all-page job.
    assert set(review._filter_pending_changes) == {0, 1}
    assert review._filter_pending_changes[0][(3, 4)]["new_word"] == "edit-one"
    assert review._filter_pending_changes[1][(3, 4)]["new_word"] == "edit-two"
    assert review._filter_pending_changes[0][(3, 4)][
        "_focused_save_source_witness"
    ] == t1["_focused_save_source_witness"]
    assert review._filter_pending_changes[1][(3, 4)][
        "_focused_save_source_witness"
    ] == t2["_focused_save_source_witness"]
    assert t1["original_word"] == t2["original_word"] == "old"
    assert review.parent.entries[0].word == "old"
    assert d2.read_bytes() == before_second
    assert len(alerts) == 1
    status = review.parent.status_var.get()
    assert "保存失败" in status and "已保留" in status
    assert "PRIVATE_" not in status + str(alerts)
