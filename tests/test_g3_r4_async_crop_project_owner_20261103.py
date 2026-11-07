"""R4.2 async crop callbacks cannot inherit a replacement ProjectState.

Disposable BMP/PDIC only. Same-root/same-bytes synthetic project objects
isolate session owner from filesystem-content identity. RED-first E2.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from picture_capture.persistence.project_storage import pdic_path_for_image
from picture_capture.ui import focused_filter_workflow as workflow


@dataclass
class _Settings:
    character_height: int = 18


class _Status:
    def __init__(self):
        self.values = []
    def set(self, value):
        self.values.append(value)


def _case(tmp_path: Path):
    pages, targets = [], []
    for index in range(2):
        page = tmp_path / f"{index + 1:03d}.bmp"
        Image.new("RGB", (8, 8), "black").save(page)
        pdic = pdic_path_for_image(page)
        pdic.parent.mkdir(parents=True, exist_ok=True)
        pdic.write_bytes(
            f"old#3#4#37.5#50#{index + 1:03d}#@#@\\n".encode("utf-8")
        )
        pages.append(page)
        targets.append({
            "page_index": index, "x": 3, "y": 4,
            "original_word": "old", "current_word": "old",
        })
    old_project = SimpleNamespace(root=tmp_path, images=pages)
    new_project = SimpleNamespace(root=tmp_path, images=list(pages))
    callbacks, workspaces, applies, renders = [], [], [], []
    status = _Status()
    parent = SimpleNamespace(
        project=old_project,
        settings=_Settings(),
        canvas=SimpleNamespace(winfo_width=lambda: 700),
        status_var=status,
        _start_ui_worker=lambda *args: callbacks.append(args),
        _invalidate_ui_worker=lambda _key: None,
    )
    review = SimpleNamespace(
        parent=parent,
        _filter_rows_active=True,
        _filter_scan_serial=41,
        _filter_scan_epoch_source_serial=41,
        _filter_scan_epoch_project=old_project,
        _filter_scan_epoch_project_root=tmp_path,
        _filter_scan_epoch_pages=tuple(pages),
        _filter_scan_epoch_source_witnesses={},
        _filter_scan_epoch_invalidated=False,
        _filter_scan_complete=True,
        _filter_scan_failed=False,
        filter_batch_var=_Status(),
        _filter_render_serial=0,
        _filter_batch_render_cache={},
        _filter_prefetch_key=None,
        _focused_timing_session=None,
        _filter_save_running=False,
        _filter_pending_changes={},
        filtered_batch_index=0,
        filtered_targets=targets,
        review_zoom_auto=False,
        review_zoom=1.0,
        _focused_batch_size=lambda: 1,
        _filter_available_target_count=lambda: 2,
        _review_image_area_width=lambda: 640,
        _update_filter_batch_indicator=lambda: None,
        _set_filter_navigation=lambda enabled: None,
        _clear_review_workspace=lambda message: workspaces.append(message),
        _reset_rows_scroll_top=lambda: None,
        _apply_filter_batch_payload=lambda *args: applies.append(args),
        _request_filter_batch_render=lambda: renders.append(True),
    )
    deps = SimpleNamespace(
        replace=replace,
        ReviewWindow=SimpleNamespace(
            _prepare_filter_batch_payload=lambda *_a: ([object()], 1.0, [(1, 1)]),
        ),
    )
    review._filter_batch_snapshot = lambda index: workflow._filter_batch_snapshot(
        review, deps, index,
    )
    review._cache_filter_batch_payload = lambda key, payload: (
        workflow._cache_filter_batch_payload(review, deps, key, payload)
    )
    return SimpleNamespace(
        review=review, deps=deps, parent=parent, old=old_project,
        new=new_project, callbacks=callbacks, workspace=workspaces,
        applies=applies, renders=renders, status=status,
    )


def test_old_prefetch_done_does_not_cache_under_replacement_project(tmp_path):
    c = _case(tmp_path)
    workflow._schedule_filter_next_batch_preload(c.review, c.deps)
    assert len(c.callbacks) == 1
    _key, worker, done, failed = c.callbacks[0]
    payload = worker()
    c.parent.project = c.new

    done(payload)

    assert c.review._filter_batch_render_cache == {}
    assert c.applies == []
    assert c.review._filter_scan_epoch_invalidated is True
    assert c.review._filter_scan_failed is True
    assert c.review._filter_scan_complete is False
    assert any(("项目会话" in str(message) or "来源" in str(message))
               for message in c.status.values)


def test_old_prefetch_failed_does_not_retry_in_replacement_project(tmp_path):
    c = _case(tmp_path)
    workflow._schedule_filter_next_batch_preload(c.review, c.deps)
    c.review.filtered_batch_index = 1
    _key, worker, done, failed = c.callbacks[0]
    c.parent.project = c.new

    failed(OSError("PRIVATE_SYNTHETIC_PATH"), "PRIVATE_TRACE")

    assert c.renders == []
    assert c.applies == []
    assert c.review._filter_scan_epoch_invalidated is True
    assert c.review._filter_scan_failed is True
    assert c.review._filter_scan_complete is False
    assert any(("项目会话" in str(message) or "来源" in str(message))
               for message in c.status.values)


def test_old_direct_render_success_cannot_cache_or_apply_to_new_project(tmp_path):
    c = _case(tmp_path)
    workflow._request_filter_batch_render(c.review, c.deps)
    assert len(c.callbacks) == 1
    _key, worker, done, failed = c.callbacks[0]
    c.parent.project = c.new

    done(([object()], 1.0, [(1, 1)]))

    assert c.review._filter_batch_render_cache == {}
    assert c.applies == []
    assert c.review._filter_scan_epoch_invalidated is True
    assert c.review._filter_scan_failed is True
    assert c.review._filter_scan_complete is False
    assert any(("项目会话" in str(message) or "来源" in str(message))
               for message in c.status.values)


def test_old_direct_render_failure_cannot_clear_new_project_workspace(tmp_path):
    c = _case(tmp_path)
    workflow._request_filter_batch_render(c.review, c.deps)
    assert len(c.callbacks) == 1
    _key, worker, done, failed = c.callbacks[0]
    c.parent.project = c.new

    failed(OSError("PRIVATE_SYNTHETIC_PATH"), "PRIVATE_TRACE")

    assert c.review._filter_batch_render_cache == {}
    assert c.applies == []
    assert c.review._filter_scan_epoch_invalidated is True
    assert c.review._filter_scan_failed is True
    assert c.review._filter_scan_complete is False
    assert any(("项目会话" in str(message) or "来源" in str(message))
               for message in c.status.values)


def test_same_session_prefetch_success_still_populates_expected_cache(tmp_path):
    c = _case(tmp_path)
    workflow._schedule_filter_next_batch_preload(c.review, c.deps)
    _key, worker, done, failed = c.callbacks[0]
    done(worker())
    assert len(c.review._filter_batch_render_cache) == 1
    assert c.applies == []


def test_same_session_direct_render_success_still_applies_payload(tmp_path):
    c = _case(tmp_path)
    workflow._request_filter_batch_render(c.review, c.deps)
    _key, worker, done, failed = c.callbacks[0]
    done(worker())
    assert len(c.review._filter_batch_render_cache) == 1
    assert len(c.applies) == 1
