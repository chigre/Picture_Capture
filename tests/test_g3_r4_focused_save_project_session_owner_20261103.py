"""R4.2 focused save must retain the exact ProjectState scan-session owner.

Synthetic 8×8 BMP/PDIC and simulated project object replacement; no
real operator sessions or private pages. RED-first regression evidence.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.persistence.project_storage import pdic_path_for_image
from picture_capture.proofreading.focused_crop_source_fingerprint import (
    focused_save_source_witness,
)
from picture_capture.ui import focused_filter_workflow as workflow


class _Status:
    def __init__(self):
        self.values = []
    def set(self, value):
        self.values.append(value)


def _case(tmp_path: Path, *, close_after_save=False):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (8, 8), "black").save(page)
    pdic = pdic_path_for_image(page)
    pdic.parent.mkdir(parents=True, exist_ok=True)
    pdic.write_bytes(b"old#3#4#37.5#50#001#@#@\n")
    source = focused_save_source_witness(page)

    # Deliberately use two different ProjectState objects pointing to the
    # identical root, page and bytes: a path or hash check alone cannot
    # distinguish their ownership.
    owner_project = SimpleNamespace(root=tmp_path, images=[page])
    replacement_project = SimpleNamespace(root=tmp_path, images=[page])
    target = {
        "page_index": 0, "x": 3, "y": 4,
        "original_word": "old", "current_word": "human",
        "_focused_save_source_witness": source,
    }
    change = {
        "page_index": 0, "x": 3, "y": 4,
        "original_word": "old", "new_word": "human",
        "_focused_save_source_witness": source,
    }
    dispatch, writes, closes, dialogs = [], [], [], []
    parent = SimpleNamespace(
        project=owner_project,
        current_index=0,
        entries=[SimpleNamespace(
            x=3, y=4, word="old", confidence=0.2,
            ocr_source="ocr", final_engine="ocr", manually_selected=False,
        )],
        status_var=_Status(),
        _start_ui_worker=lambda *args, **kw: dispatch.append((args, kw)),
    )
    review = SimpleNamespace(
        parent=parent,
        filtered_targets=[target],
        _filter_rows_active=True,
        _filter_scan_serial=47,
        _filter_scan_epoch_source_serial=47,
        _filter_scan_epoch_project=owner_project,
        _filter_scan_epoch_project_root=tmp_path,
        _filter_scan_epoch_pages=(page,),
        _filter_scan_epoch_source_witnesses={},
        _filter_scan_epoch_invalidated=False,
        _filter_pending_changes={0: {(3, 4): change}},
        _filter_save_job=None,
        _filter_save_running=False,
        _filter_close_after_save=close_after_save,
        _focused_timing_session=None,
        _finish_close_review=lambda: closes.append(True),
    )
    def writer(*args):
        writes.append(args)
        return [(0, 3, 4, "human")], []
    deps = SimpleNamespace(
        _apply_focused_review_page_updates=writer,
        messagebox=SimpleNamespace(
            showerror=lambda *a, **kw: dialogs.append(("error", a)),
            showwarning=lambda *a, **kw: dialogs.append(("warning", a)),
        ),
    )
    return SimpleNamespace(
        review=review, parent=parent, owner=owner_project,
        replacement=replacement_project, target=target, page=page,
        pdic=pdic, dispatch=dispatch, writes=writes, closes=closes,
        dialogs=dialogs, deps=deps, change=change,
    )


def test_replaced_project_before_save_launch_keeps_human_queue_and_refuses_writer(tmp_path):
    case = _case(tmp_path)
    original_pdic = case.pdic.read_bytes()
    case.parent.project = case.replacement

    workflow._flush_focused_changes(case.review, case.deps)

    assert case.dispatch == [], "a foreign ProjectState obtained the old edit"
    assert case.writes == []
    assert case.pdic.read_bytes() == original_pdic
    assert case.review._filter_pending_changes[0][(3, 4)] is case.change
    assert case.review._filter_save_running is False
    assert case.review._filter_close_after_save is False


def test_project_replaced_after_launch_before_worker_preflight_cannot_write(tmp_path):
    case = _case(tmp_path)
    workflow._flush_focused_changes(case.review, case.deps)
    assert len(case.dispatch) == 1
    _key, worker, done, failed = case.dispatch[0][0]
    case.parent.project = case.replacement

    with pytest.raises(RuntimeError, match="(项目|会话|ProjectState|source)"):
        worker()
    assert case.writes == []
    failed(RuntimeError("PRIVATE_PROJECT_PATH"), "PRIVATE_TRACE")
    assert case.review._filter_pending_changes[0][(3, 4)]["new_word"] == "human"
    assert case.target["original_word"] == "old"
    assert case.closes == []


def test_project_replaced_after_worker_before_done_cannot_reconcile_foreign_ui(tmp_path):
    case = _case(tmp_path, close_after_save=True)
    workflow._flush_focused_changes(case.review, case.deps)
    _key, worker, done, failed = case.dispatch[0][0]
    payload = worker()
    assert len(case.writes) == 1
    case.parent.project = case.replacement
    before_ui = (
        case.target["original_word"],
        case.parent.entries[0].word,
        case.parent.entries[0].manually_selected,
    )

    done(payload)

    assert (
        case.target["original_word"],
        case.parent.entries[0].word,
        case.parent.entries[0].manually_selected,
    ) == before_ui
    assert case.closes == []
    assert not case.review._filter_close_after_save
    assert case.review._filter_pending_changes[0][(3, 4)]["new_word"] == "human"
    assert case.review._filter_save_uncertain_pages == {0}


def test_unchanged_project_session_still_commits_valid_human_edit(tmp_path):
    case = _case(tmp_path)
    case.review.after = lambda ms, fn: "next"
    workflow._flush_focused_changes(case.review, case.deps)
    assert len(case.dispatch) == 1
    _key, worker, done, failed = case.dispatch[0][0]
    done(worker())

    assert len(case.writes) == 1
    assert case.target["original_word"] == "human"
    assert case.parent.entries[0].word == "human"
    assert case.review._filter_pending_changes == {}
    assert case.closes == []
