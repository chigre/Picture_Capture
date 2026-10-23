"""#562 GUI batch ownership: foreground edit locks, queue lifecycle and Tk signatures."""
from __future__ import annotations

from dataclasses import fields
from inspect import signature
from types import SimpleNamespace
import subprocess
import sys
import threading

from picture_capture import app as app_module
from picture_capture.ui import batch_workflow as owner


NAMES = (
    "_foreground_batch_state", "_set_foreground_batch_state",
    "_claim_page_for_manual_edit", "_can_save_current_during_batch_navigation",
    "_entry_keypress_batch_guard", "_start_batch_task",
    "_start_parallel_batch_task", "_poll_batch_queue",
    "_finish_batch_task", "_hide_batch_bar_if_idle",
    "_toggle_batch_pause", "_request_batch_stop",
)


def test_leaf_import_does_not_import_tk_application_or_native_ocr_engines():
    subprocess.run([sys.executable, "-c", """
import sys
from picture_capture.ui.batch_workflow import BatchWorkflowDeps
assert 'picture_capture.app' not in sys.modules
assert 'picture_capture.paddle_headwords_core' not in sys.modules
assert 'paddle' not in sys.modules
"""], check=True)


def test_all_twelve_original_batch_method_names_and_signatures_remain():
    for name in NAMES:
        old = getattr(app_module.PictureCaptureApp, name)
        new = getattr(owner, name)
        old_sig = signature(old)
        new_sig = signature(new)
        assert list(old_sig.parameters) == list(new_sig.parameters)[1:]
        for param in old_sig.parameters:
            assert old_sig.parameters[param].default == new_sig.parameters[param].default
    assert signature(app_module.PictureCaptureApp._start_batch_task).parameters[
        "foreground_page_edit"
    ].default is False
    assert signature(app_module.PictureCaptureApp._start_parallel_batch_task).parameters[
        "respect_cpu_workers"
    ].default is False


def test_dynamic_original_app_globals_bound_each_call(monkeypatch):
    names = {f.name for f in fields(owner.BatchWorkflowDeps)}
    assert len(names) == 11
    assert {"threading", "multiprocessing", "ProcessPoolExecutor",
            "FIRST_COMPLETED", "wait", "queue", "messagebox",
            "resolve_crop_worker_count"} <= names
    snap = app_module._batch_workflow_deps()
    assert snap.threading is app_module.threading
    assert snap.ProcessPoolExecutor is app_module.ProcessPoolExecutor
    fake = object()
    monkeypatch.setattr(app_module, "ProcessPoolExecutor", fake)
    assert app_module._batch_workflow_deps().ProcessPoolExecutor is fake


def test_batch_entrypoint_forwards_full_parallel_arguments(monkeypatch):
    received = {}
    marker = object()

    def replacement(deps, self, *args, **kwargs):
        received.update(deps=deps, instance=self, args=args, kwargs=kwargs)
        return marker

    monkeypatch.setattr(owner, "_start_parallel_batch_task", replacement)
    instance = object()
    executor_fn = object()
    builder = object()
    returned = app_module.PictureCaptureApp._start_parallel_batch_task(
        instance, "检测", [1, 2], executor_fn, builder,
        result_consumer=lambda *a: None, on_done=lambda *a: None,
        item_label=str, max_workers=3, allow_page_navigation=False,
        allow_pdic_edits=True, foreground_page_edit=True,
        page_indexer=int, gpu_preflight_func=object(),
        gpu_job_builder=object(), respect_cpu_workers=True,
        isolate_worker=True,
    )
    assert returned is marker
    assert received["instance"] is instance
    assert received["args"][:4] == ("检测", [1, 2], executor_fn, builder)
    assert received["kwargs"]["max_workers"] == 3
    assert received["kwargs"]["foreground_page_edit"] is True
    assert received["kwargs"]["isolate_worker"] is True
    assert isinstance(received["deps"], owner.BatchWorkflowDeps)


def test_foreground_page_ownership_blocks_active_worker_and_claims_pending():
    labels = []
    statuses = SimpleNamespace(set=lambda value: labels.append(value))
    changed = []
    instance = SimpleNamespace(
        _batch_active=True, _batch_foreground_pages=True,
        _batch_state_lock=threading.RLock(),
        _batch_page_states={2: "processing", 3: "pending"},
        current_index=3,
        status_var=statuses,
        _update_page_row=lambda value: changed.append(value),
    )
    assert not owner._claim_page_for_manual_edit(
        app_module._batch_workflow_deps(), instance, 2)
    assert owner._claim_page_for_manual_edit(
        app_module._batch_workflow_deps(), instance, 3)
    assert instance._batch_page_states[3] == "manual_locked"
    assert changed == [3]
    assert owner._foreground_batch_state(
        app_module._batch_workflow_deps(), instance, 3) == "manual_locked"
    assert labels


def test_batch_navigation_never_saves_stale_pending_or_processing_page():
    instance = SimpleNamespace(
        _batch_active=True, _batch_foreground_pages=True,
        _batch_state_lock=threading.RLock(),
        _batch_page_states={1: "pending", 2: "processing", 3: "manual_locked"},
        current_index=1,
    )
    instance._foreground_batch_state = lambda index: instance._batch_page_states[index]
    deps = app_module._batch_workflow_deps()
    assert owner._can_save_current_during_batch_navigation(deps, instance) is False
    instance.current_index = 2
    assert owner._can_save_current_during_batch_navigation(deps, instance) is False
    instance.current_index = 3
    assert owner._can_save_current_during_batch_navigation(deps, instance) is True


def test_stop_request_unpauses_paused_worker_without_discarding_completed_results():
    shown = []
    updates = []
    stop = threading.Event()
    pause = threading.Event()
    instance = SimpleNamespace(
        _batch_active=True,
        _batch_stop_event=stop, _batch_pause_event=pause,
        batch_pause_button=SimpleNamespace(configure=lambda **kw: updates.append(kw)),
        batch_stop_button=SimpleNamespace(configure=lambda **kw: updates.append(kw)),
        batch_text_var=SimpleNamespace(set=lambda text: shown.append(text)),
        status_var=SimpleNamespace(set=lambda text: shown.append(text)),
        _batch_title="批量检测", _batch_parallel=True,
    )
    owner._request_batch_stop(app_module._batch_workflow_deps(), instance)
    assert stop.is_set() and pause.is_set()
    assert any(x.get("state") == "disabled" for x in updates)
    assert any("安全停止" in x for x in shown)


def test_nonediting_navigation_key_does_not_claim_page():
    calls = []
    instance = SimpleNamespace(
        _batch_active=True,
        _claim_page_for_manual_edit=lambda: calls.append("claimed") or True,
    )
    deps = app_module._batch_workflow_deps()
    assert owner._entry_keypress_batch_guard(
        deps, instance, SimpleNamespace(keysym="Left")) is None
    assert calls == []
    assert owner._entry_keypress_batch_guard(
        deps, instance, SimpleNamespace(keysym="a")) is None
    assert calls == ["claimed"]
