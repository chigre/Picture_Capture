"""G3 R4.2: failed next-batch crop prefetch must not strand its visible UI.

All images and image/PDIC/SECTION source witnesses are disposable 8x8 synthetic
BMP/sidecars. Fail-first test: no private image or real Windows E3 evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.persistence.project_storage import (
    page_sections_read_path_for_image, pdic_path_for_image,
)
from picture_capture.ui import focused_filter_workflow as workflow


@dataclass
class Settings:
    character_height: int = 18


class Var:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


def _case(tmp_path):
    images = []
    targets = []
    for i in (1, 2):
        page = tmp_path / f"{i:03d}.bmp"
        Image.new("RGB", (8, 8), "black").save(page)
        pdic = pdic_path_for_image(page)
        pdic.parent.mkdir(parents=True, exist_ok=True)
        pdic.write_bytes(f"old#3#4#1#1#{i:03d}#@#@\n".encode("utf-8"))
        section = page_sections_read_path_for_image(page)
        section.parent.mkdir(parents=True, exist_ok=True)
        section.write_bytes(b'{"revision":"A"}')
        images.append(page)
        targets.append({
            "page_index": i - 1, "x": 3, "y": 4,
            "original_word": "old", "current_word": "old",
        })

    workers, workspaces, applied = [], [], []
    status = Var("existing")
    review = SimpleNamespace(
        parent=SimpleNamespace(
            project=SimpleNamespace(root=tmp_path, images=images),
            settings=Settings(),
            canvas=SimpleNamespace(winfo_width=lambda: 700),
            status_var=status,
            _start_ui_worker=lambda *args: workers.append(args),
        ),
        _filter_rows_active=True,
        _filter_scan_serial=71,
        _filter_render_serial=2,
        _filter_scan_complete=True,
        filtered_batch_index=0,
        filtered_targets=targets,
        _filter_batch_render_cache={},
        _filter_prefetch_key=None,
        _filter_save_running=False,
        _filter_pending_changes={},
        _focused_timing_session=None,
        review_zoom_auto=False,
        review_zoom=1.0,
        _focused_batch_size=lambda: 1,
        _filter_available_target_count=lambda: 2,
        _review_image_area_width=lambda: 640,
        _update_filter_batch_indicator=lambda: None,
        _set_filter_navigation=lambda _enabled: None,
        _clear_review_workspace=lambda message: workspaces.append(message),
        _apply_filter_batch_payload=lambda *args: applied.append(args),
    )
    deps = SimpleNamespace(
        replace=replace,
        ReviewWindow=SimpleNamespace(
            _prepare_filter_batch_payload=lambda *_a: ([object()], 1.0, [(1, 1)]),
        ),
    )
    review._filter_batch_snapshot = lambda index: workflow._filter_batch_snapshot(
        review, deps, index
    )
    review._cache_filter_batch_payload = lambda key, payload: workflow._cache_filter_batch_payload(
        review, deps, key, payload
    )
    review._request_filter_batch_render = lambda: workflow._request_filter_batch_render(
        review, deps
    )
    workflow._schedule_filter_next_batch_preload(review, deps)
    assert len(workers) == 1
    assert workers[0][0].startswith("focused-filter-prefetch-")
    return SimpleNamespace(
        review=review, deps=deps, workers=workers,
        workspace=workspaces, applied=applied, status=status,
        images=images,
    )


def _same_size_replace(path, data):
    before = path.stat()
    assert len(data) == before.st_size
    path.write_bytes(data)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    assert path.stat().st_mtime_ns == before.st_mtime_ns


def test_failed_prefetch_after_navigation_recovers_via_new_owned_render(tmp_path, capsys):
    case = _case(tmp_path)
    review = case.review
    frozen_key = review._filter_prefetch_key
    # A human already clicked Next while N+1 was still prefetching.
    review.filtered_batch_index = 1
    case.workspace.append("下一批已在后台预生成，即将显示…")
    failed = case.workers[0][3]
    failed(OSError("PRIVATE_PREFETCH_SOURCE"), "TRACE_PRIVATE_PREFETCH_SOURCE")
    # The old code silently leaves the waiting workspace stranded.
    assert review._filter_prefetch_key is None
    assert len(case.workers) == 2
    key, render_worker, render_done, _render_failed = case.workers[1]
    assert key.startswith("focused-filter-render-")
    assert review._filter_batch_snapshot(1)[0] == frozen_key
    render_done(render_worker())
    assert len(case.applied) == 1
    assert case.applied[0][0] == 1
    assert case.applied[0][1] == frozen_key
    assert "PRIVATE_PREFETCH_SOURCE" not in repr(capsys.readouterr())


def test_same_failed_callback_delivers_at_most_one_current_batch_recovery(tmp_path):
    case = _case(tmp_path)
    case.review.filtered_batch_index = 1
    failed = case.workers[0][3]
    failed(OSError("one"), "PRIVATE_TRACE")
    failed(OSError("duplicate"), "PRIVATE_TRACE")
    assert len(case.workers) == 2


@pytest.mark.parametrize("source", ("image", "pdic", "section"))
def test_prefetch_failure_after_source_byte_drift_refuses_automatic_rebuild(
    tmp_path, source, capsys,
):
    case = _case(tmp_path)
    review = case.review
    stale_key = review._filter_prefetch_key
    review.filtered_batch_index = 1
    page = case.images[1]
    if source == "image":
        replacement = tmp_path / "replacement.bmp"
        Image.new("RGB", (8, 8), "red").save(replacement)
        _same_size_replace(page, replacement.read_bytes())
    elif source == "pdic":
        _same_size_replace(
            pdic_path_for_image(page),
            b"new#3#4#1#1#002#@#@\n",
        )
    else:
        _same_size_replace(
            page_sections_read_path_for_image(page),
            b'{"revision":"B"}',
        )
    assert review._filter_batch_snapshot(1)[0] != stale_key
    case.workers[0][3](
        OSError("PRIVATE_DISK_PATH"), "TRACE_PRIVATE_DISK_PATH"
    )
    # Fail closed: no crop from a new or old source is silently installed.
    assert len(case.workers) == 1
    assert case.applied == []
    assert review._filter_prefetch_key is None
    assert "重新筛选" in case.status.get()
    assert "PRIVATE_DISK_PATH" not in repr(case.status.get())
    assert "PRIVATE_DISK_PATH" not in repr(capsys.readouterr())


def test_stale_epoch_prefetch_failure_cannot_rerender_or_clear_new_epoch(tmp_path):
    case = _case(tmp_path)
    case.review.filtered_batch_index = 1
    case.review._filter_scan_serial += 1
    case.review._filter_prefetch_key = ("new-epoch",)
    case.status.set("new scan")
    case.workers[0][3](OSError("PRIVATE_OLD"), "PRIVATE_OLD")
    assert len(case.workers) == 1
    assert case.review._filter_prefetch_key == ("new-epoch",)
    assert case.status.get() == "new scan"


def test_prefetch_failure_with_human_pending_changes_never_clears_editors(
    tmp_path, capsys,
):
    case = _case(tmp_path)
    case.review.filtered_batch_index = 1
    case.review._filter_pending_changes = {1: {(3, 4): {"new_word": "human"}}}
    case.workspace.append("HUMAN_VISIBLE_EDITOR")
    case.workers[0][3](OSError("PRIVATE_PENDING"), "PRIVATE_PENDING")
    assert len(case.workers) == 1
    assert case.workspace == ["HUMAN_VISIBLE_EDITOR"]
    assert case.review._filter_pending_changes[1][(3, 4)]["new_word"] == "human"
    assert "PRIVATE_PENDING" not in repr(capsys.readouterr())


def test_prefetch_failure_for_no_longer_selected_batch_remains_silent(tmp_path):
    case = _case(tmp_path)
    case.workers[0][3](OSError("not-visible"), "PRIVATE_TRACE")
    assert len(case.workers) == 1
    assert case.review._filter_prefetch_key is None
    assert case.status.get() == "existing"


@pytest.mark.parametrize("source", ("image", "pdic", "section"))
def test_successful_prefetch_cannot_publish_drifted_source(
    tmp_path, source, capsys,
):
    """A successful worker result is not evidence that its source is current."""
    case = _case(tmp_path)
    case.review.filtered_batch_index = 1
    stale_key = case.review._filter_prefetch_key
    # Worker finished under the original source. Drift occurs before Tk done.
    payload = case.workers[0][1]()
    page = case.images[1]
    if source == "image":
        replacement = tmp_path / "replacement.bmp"
        Image.new("RGB", (8, 8), "red").save(replacement)
        _same_size_replace(page, replacement.read_bytes())
    elif source == "pdic":
        _same_size_replace(
            pdic_path_for_image(page), b"new#3#4#1#1#002#@#@\n",
        )
    else:
        _same_size_replace(
            page_sections_read_path_for_image(page), b'{"revision":"B"}',
        )
    assert case.review._filter_batch_snapshot(1)[0] != stale_key
    _worker_name, worker, done, _failed = case.workers[0]
    done(payload)
    assert case.review._filter_prefetch_key is None
    assert case.review._filter_batch_render_cache == {}
    assert case.applied == []
    assert "重新筛选" in case.status.get()
    assert "PRIVATE" not in repr(case.status.get())
    assert "PRIVATE" not in repr(capsys.readouterr())


def test_successful_old_key_callback_cannot_steal_new_prefetch(tmp_path):
    case = _case(tmp_path)
    case.review.filtered_batch_index = 1
    case.review._filter_prefetch_key = ("new-owner",)
    _worker_name, worker, done, _failed = case.workers[0]
    done(worker())
    assert case.review._filter_prefetch_key == ("new-owner",)
    assert case.review._filter_batch_render_cache == {}
    assert case.applied == []
    assert case.status.get() == "existing"


def test_successful_prefetch_does_not_overwrite_outstanding_human_edit(tmp_path):
    case = _case(tmp_path)
    case.review.filtered_batch_index = 1
    human = {1: {(3, 4): {"new_word": "human"}}}
    case.review._filter_pending_changes = human
    case.workspace.append("HUMAN_VISIBLE_EDITOR")
    _worker_name, worker, done, _failed = case.workers[0]
    done(worker())
    assert case.applied == []
    assert case.workspace == ["HUMAN_VISIBLE_EDITOR"]
    assert case.review._filter_pending_changes is human
    assert human[1][(3, 4)]["new_word"] == "human"


def test_prefetch_worker_detects_source_change_during_crop(tmp_path):
    """Worker must not label a different PDIC as the initial cache key."""
    case = _case(tmp_path)
    page = case.images[1]
    old_prepare = case.deps.ReviewWindow._prepare_filter_batch_payload

    def prepare_with_drift(*args):
        _same_size_replace(
            pdic_path_for_image(page), b"new#3#4#1#1#002#@#@\n",
        )
        return old_prepare(*args)

    case.deps.ReviewWindow._prepare_filter_batch_payload = prepare_with_drift
    _worker_name, worker, _done, _failed = case.workers[0]
    with pytest.raises((OSError, ValueError)):
        worker()


def _direct_case(tmp_path):
    """Start an owned visible direct render with disposable real source sidecars."""
    case = _case(tmp_path)
    case.review.filtered_batch_index = 1
    case.review._filter_prefetch_key = None
    case.review._request_filter_batch_render()
    assert len(case.workers) == 2
    assert case.workers[1][0].startswith("focused-filter-render-")
    return case


@pytest.mark.parametrize("source", ("image", "pdic", "section"))
def test_direct_render_success_does_not_cache_source_drift(
    tmp_path, source, capsys,
):
    case = _direct_case(tmp_path)
    review = case.review
    old_key = review._filter_batch_snapshot(1)[0]
    _key, worker, done, _failed = case.workers[1]
    payload = worker()  # Crop finished before disk changes and delayed Tk done.
    page = case.images[1]
    if source == "image":
        replacement = tmp_path / "replacement.bmp"
        Image.new("RGB", (8, 8), "red").save(replacement)
        _same_size_replace(page, replacement.read_bytes())
    elif source == "pdic":
        _same_size_replace(
            pdic_path_for_image(page), b"new#3#4#1#1#002#@#@\n",
        )
    else:
        _same_size_replace(
            page_sections_read_path_for_image(page), b'{"revision":"B"}',
        )
    assert review._filter_batch_snapshot(1)[0] != old_key
    done(payload)
    assert review._filter_batch_render_cache == {}
    assert case.applied == []
    assert "重新筛选" in case.status.get()
    assert "PRIVATE" not in repr(capsys.readouterr())


def test_direct_render_worker_rejects_source_drift_while_cropping(tmp_path):
    case = _direct_case(tmp_path)
    page = case.images[1]
    original = case.deps.ReviewWindow._prepare_filter_batch_payload

    def produce_after_drift(*args):
        _same_size_replace(
            pdic_path_for_image(page), b"new#3#4#1#1#002#@#@\n",
        )
        return original(*args)

    case.deps.ReviewWindow._prepare_filter_batch_payload = produce_after_drift
    with pytest.raises((OSError, ValueError)):
        case.workers[1][1]()
    assert case.review._filter_batch_render_cache == {}


@pytest.mark.parametrize("pending", ("edit", "save"))
def test_direct_render_success_does_not_overwrite_human_or_inflight_save(
    tmp_path, pending,
):
    case = _direct_case(tmp_path)
    _key, worker, done, _failed = case.workers[1]
    payload = worker()
    if pending == "edit":
        edits = {1: {(3, 4): {"new_word": "human"}}}
        case.review._filter_pending_changes = edits
    else:
        case.review._filter_save_running = True
    case.workspace.append("HUMAN_EDITOR")
    done(payload)
    assert case.applied == []
    assert case.workspace[-1] == "HUMAN_EDITOR"
    assert case.review._filter_batch_render_cache == {}
    if pending == "edit":
        assert case.review._filter_pending_changes is edits
        assert edits[1][(3, 4)]["new_word"] == "human"


@pytest.mark.parametrize("pending", ("edit", "save"))
def test_direct_render_failure_does_not_clear_human_or_inflight_save(
    tmp_path, pending, capsys,
):
    case = _direct_case(tmp_path)
    if pending == "edit":
        edits = {1: {(3, 4): {"new_word": "human"}}}
        case.review._filter_pending_changes = edits
    else:
        case.review._filter_save_running = True
    case.workspace.append("HUMAN_EDITOR")
    case.workers[1][3](OSError("PRIVATE_PAGE"), "PRIVATE_TRACE")
    assert case.workspace[-1] == "HUMAN_EDITOR"
    assert case.status.get() == "existing"
    if pending == "edit":
        assert case.review._filter_pending_changes is edits
    assert "PRIVATE" not in repr(capsys.readouterr())


def test_direct_cached_payload_cannot_repaint_pending_human_edit(tmp_path):
    case = _direct_case(tmp_path)
    valid_key = case.review._filter_batch_snapshot(1)[0]
    case.review._filter_batch_render_cache[valid_key] = (
        [object()], 1.0, [(1, 1)],
    )
    edits = {1: {(3, 4): {"new_word": "human"}}}
    case.review._filter_pending_changes = edits
    case.workspace.append("HUMAN_EDITOR")
    case.review._request_filter_batch_render()
    assert case.applied == []
    assert case.workspace[-1] == "HUMAN_EDITOR"
    assert edits[1][(3, 4)]["new_word"] == "human"


def test_direct_render_stable_source_still_publishes_once(tmp_path):
    case = _direct_case(tmp_path)
    valid_key = case.review._filter_batch_snapshot(1)[0]
    _key, worker, done, _failed = case.workers[1]
    done(worker())
    assert list(case.review._filter_batch_render_cache) == [valid_key]
    assert len(case.applied) == 1
    assert case.applied[0][0:2] == (1, valid_key)


def test_direct_render_old_serial_success_cannot_publish(tmp_path):
    case = _direct_case(tmp_path)
    previous_key, old_worker, old_done, _old_failed = case.workers[1]
    assert previous_key.startswith("focused-filter-render-")
    case.review._request_filter_batch_render()
    assert len(case.workers) == 3
    old_done(old_worker())
    assert case.review._filter_batch_render_cache == {}
    assert case.applied == []
