"""Isolated GPU preflight / CPU-only ordinary page processing (synthetic).

These tests never construct PaddleOCR or transfer a GPU model to CPU jobs.
They verify strict reuse of the same detector settings and manual page locks.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue
from threading import Event, Lock
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.ordinary_gpu_pipeline import (
    PreparedLayoutEstimate,
    detect_entries_staged_job,
    prepare_gpu_layout_job,
    reject_cpu_worker_detector,
    staged_pipeline_enabled,
    take_prepared_layout,
    use_prepared_layout,
    validate_prepared_layout,
    verify_prepared_source,
)


def test_staged_pipeline_opt_in_and_unsupported_settings_default_to_serial(monkeypatch):
    settings = SimpleNamespace(
        ordinary_auto_layout=True,
        layout_mask_illustrations=False,
        layout_transform="identity",
    )
    monkeypatch.delenv("PICTURE_CAPTURE_ORDINARY_GPU_PIPELINE", raising=False)
    assert not staged_pipeline_enabled(settings, 80)
    assert staged_pipeline_enabled(settings, 80, flag="1")
    assert not staged_pipeline_enabled(settings, 1, flag="1")
    assert not staged_pipeline_enabled(settings, 80, flag="8")
    settings.layout_mask_illustrations = True
    assert not staged_pipeline_enabled(settings, 80, flag="1")
    settings.layout_mask_illustrations = False
    settings.layout_transform = "rotate_ccw90"
    assert not staged_pipeline_enabled(settings, 80, flag="1")
    settings.layout_transform = "identity"
    settings.ordinary_auto_layout = False
    assert not staged_pipeline_enabled(settings, 80, flag="1")


def test_single_use_preflight_is_transferred_by_value_without_gpu(monkeypatch):
    from picture_capture import dictionary_page_layout_policy as policy
    from picture_capture import layout_detection

    image = Image.new("RGB", (320, 470), "white")
    settings = SimpleNamespace(ordinary_auto_layout=True, layout_columns_policy="detect")
    prepared = PreparedLayoutEstimate(
        value={"columns": 2, "manual_x": 43},
        page_size=image.size, source_size_bytes=128,
        source_mtime_ns=1234, detector_settings_repr=repr(settings),
        page_index=0,
    )
    monkeypatch.setattr(
        layout_detection, "detect_layout_parameters",
        lambda *_args, **_kw: pytest.fail("CPU must not run GPU detector"),
    )
    with use_prepared_layout(prepared) as state:
        assert policy.detect_layout_parameters(image, settings) == prepared.value
        assert state.consumed == 1
        with pytest.raises(RuntimeError, match="mismatch/repeated"):
            policy.detect_layout_parameters(image, settings)
        with pytest.raises(RuntimeError, match="not consumed exactly once"):
            validate_prepared_layout(state)

    with use_prepared_layout(prepared) as state:
        altered = SimpleNamespace(ordinary_auto_layout=False, layout_columns_policy="detect")
        with pytest.raises(RuntimeError, match="mismatch/repeated"):
            policy.detect_layout_parameters(image, altered)
        with pytest.raises(RuntimeError, match="not consumed exactly once"):
            validate_prepared_layout(state)

    with use_prepared_layout(prepared) as state:
        assert take_prepared_layout(image, settings) == prepared.value
        validate_prepared_layout(state)
    image.close()


def test_unexpected_cpu_paddle_model_guard_invalidates_page():
    prepared = PreparedLayoutEstimate(
        value=123, page_size=(10, 20), source_size_bytes=1,
        source_mtime_ns=1, detector_settings_repr="settings", page_index=1,
    )
    with use_prepared_layout(prepared) as state:
        with pytest.raises(RuntimeError, match="another Paddle GPU"):
            reject_cpu_worker_detector()
        with pytest.raises(RuntimeError, match="not consumed exactly once"):
            validate_prepared_layout(state)
    # The guard must not break normal GPU producer or legacy serial workers.
    reject_cpu_worker_detector()


def test_real_paddle_detector_entrypoint_refuses_cpu_stage_before_import():
    from picture_capture.layout_detection_legacy import _get_text_detector

    prepared = PreparedLayoutEstimate(
        value="geom", page_size=(30, 40), source_size_bytes=100,
        source_mtime_ns=1, detector_settings_repr="settings", page_index=2,
    )
    with use_prepared_layout(prepared) as state:
        with pytest.raises(RuntimeError, match="another Paddle GPU"):
            _get_text_detector(SimpleNamespace())
        with pytest.raises(RuntimeError, match="not consumed exactly once"):
            validate_prepared_layout(state)


def test_gui_pipeline_displays_per_page_gpu_and_cpu_stage_markers():
    source = (
        Path(__file__).resolve().parents[1] / "src"
        / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    start = source.index("    def _start_parallel_batch_task(")
    end = source.index("    def _finish_batch_task(", start)
    part = source[start:end]
    assert 'ProcessPoolExecutor(max_workers=1, mp_context=context)' in part
    assert '"pipeline_stage", position, total, label, "GPU版面预检"' in part
    assert '"pipeline_stage", position, total, label, "CPU画线与保存"' in part
    assert "gpu_executor.shutdown(wait=True, cancel_futures=True)" in part


def test_gpu_preflight_matches_page_policy_and_refuses_changed_image(tmp_path, monkeypatch):
    from picture_capture.models import AppSettings
    from picture_capture import layout_detection
    from picture_capture.profile_semantics import effective_page_settings
    from picture_capture.image_utils import build_analysis_image

    page = tmp_path / "001.png"
    Image.new("RGB", (160, 220), "white").save(page)
    settings = AppSettings()
    settings.ordinary_auto_layout = True
    settings.layout_mask_illustrations = False
    settings.layout_transform = "identity"
    settings.ordinary_auto_columns = True

    seen = []
    def fake_detector(image, actual_settings):
        seen.append((image.size, repr(actual_settings)))
        return {"source": "fake-gpu", "column_count": 2}

    monkeypatch.setattr(layout_detection, "detect_layout_parameters", fake_detector)
    prepared = prepare_gpu_layout_job(str(page), settings, 0)
    assert prepared.value == {"source": "fake-gpu", "column_count": 2}
    assert len(seen) == 1
    with Image.open(page) as raw:
        effective = effective_page_settings(settings, raw.size, 0)
        analysis = build_analysis_image(raw, effective)
        try:
            assert seen[0][0] == analysis.size
        finally:
            if analysis is not raw:
                analysis.close()
    verify_prepared_source(str(page), 0, prepared)
    with pytest.raises(RuntimeError, match="identity"):
        verify_prepared_source(str(page), 1, prepared)
    # Not enough to have the same basename; a new scan invalidates preflight.
    Image.new("RGB", (161, 220), "white").save(page)
    with pytest.raises(RuntimeError, match="identity"):
        verify_prepared_source(str(page), 0, prepared)


def test_staged_worker_does_not_commit_when_preflight_source_changed(tmp_path, monkeypatch):
    from picture_capture import processing

    page = tmp_path / "002.png"
    page.write_bytes(b"fresh initial source")
    stat = page.stat()
    prepared = PreparedLayoutEstimate(
        value={"text": 1}, page_size=(10, 20),
        source_size_bytes=stat.st_size, source_mtime_ns=stat.st_mtime_ns,
        detector_settings_repr="settings", page_index=3,
    )
    monkeypatch.setattr(
        processing, "detect_entries_job",
        lambda *_a, **_k: pytest.fail("CPU worker must not be launched"),
    )
    page.write_bytes(b"changed! new source")
    with pytest.raises(RuntimeError, match="identity"):
        detect_entries_staged_job(str(page), object(), ("a", "@", "@"), 3, prepared)


def test_one_gpu_preflight_process_two_cpu_pages_bounded_and_manual_skip(monkeypatch):
    from picture_capture import app as gui

    gpu_active = 0
    gpu_peak = 0
    cpu_running = 0
    cpu_peak = 0
    counts = []
    lock = Lock()
    cpu_release = Event()
    both_cpu_started = Event()

    class Executor:
        def __init__(self, max_workers, mp_context):
            counts.append(max_workers)
            self.pool = ThreadPoolExecutor(max_workers=max_workers)
        def submit(self, fn, *args):
            return self.pool.submit(fn, *args)
        def shutdown(self, *, wait, cancel_futures):
            self.pool.shutdown(wait=wait, cancel_futures=cancel_futures)

    monkeypatch.setattr(gui, "ProcessPoolExecutor", Executor)

    class Variable:
        def __init__(self): self.value = ""
        def set(self, value): self.value = value
        def get(self): return self.value

    class Fake:
        def __init__(self):
            self._batch_active = False
            self._ui_close_requested = False
            self._batch_state_lock = Lock()
            self._batch_page_states = {}
            self._batch_pause_event = Event()
            self._batch_stop_event = Event()
            self._batch_queue = Queue()
            self.batch_progress_var = Variable()
            self.batch_text_var = Variable()
            self.batch_progress = SimpleNamespace(configure=lambda **_: None)
            self.batch_pause_button = SimpleNamespace(configure=lambda **_: None)
            self.batch_stop_button = SimpleNamespace(configure=lambda **_: None)
            self.batch_bar = SimpleNamespace(
                winfo_manager=lambda: True, pack=lambda **_: None,
            )
            self.status_var = Variable()
            self.current_index = 2
            self._batch_skipped_count = 0
        def _ui_worker_key_active(self, _): return False
        def _flush_deferred_page_save(self): pass
        def _update_page_row(self, index): pass
        def after(self, delay, callback): return 1
        def _poll_batch_queue(self): pass

    def gpu_stage(page):
        nonlocal gpu_active, gpu_peak
        with lock:
            gpu_active += 1
            gpu_peak = max(gpu_peak, gpu_active)
        try:
            return page + 100
        finally:
            with lock:
                gpu_active -= 1

    def cpu_stage(page, gpu_estimate):
        nonlocal cpu_running, cpu_peak
        assert gpu_estimate == page + 100
        with lock:
            cpu_running += 1
            cpu_peak = max(cpu_peak, cpu_running)
            if cpu_running == 2:
                both_cpu_started.set()
        try:
            assert cpu_release.wait(8), "CPU workers not released"
            return page * 10
        finally:
            with lock:
                cpu_running -= 1

    fake = Fake()
    try:
        assert gui.PictureCaptureApp._start_parallel_batch_task(
            fake, "staged ordinary", [0, 1, 2], cpu_stage,
            lambda page, *_: (page,),
            result_consumer=lambda page, raw: {"index": page, "count": raw},
            item_label=str, max_workers=2,
            foreground_page_edit=True, page_indexer=int,
            gpu_preflight_func=gpu_stage,
            gpu_job_builder=lambda page, *_: (page,),
        )
        assert both_cpu_started.wait(8)
        assert fake._batch_page_states == {
            0: "processing", 1: "processing", 2: "pending",
        }
        assert gui.PictureCaptureApp._claim_page_for_manual_edit(fake, 2)
    finally:
        cpu_release.set()
    fake._batch_thread.join(timeout=10)
    assert not fake._batch_thread.is_alive()
    assert counts == [2, 1]  # exactly one GPU model owner, two CPU workers
    assert gpu_peak == 1
    assert cpu_peak == 2
    assert fake._batch_page_states == {
        0: "done", 1: "done", 2: "manual_locked",
    }
    event_types = [event[0] for event in list(fake._batch_queue.queue)]
    assert event_types.count("parallel_progress") == 2
    assert event_types.count("skipped") == 1
    assert event_types[-1] == "done"
