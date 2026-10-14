"""Ordinary batch CPU scaling and manual PDIC ownership regression tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue
from threading import Event, Lock
from types import SimpleNamespace
import threading

import pytest

from picture_capture.ordinary_parallel import ordinary_draw_workers


def test_ordinary_worker_policy_serializes_even_on_24_core_gpu_machine(monkeypatch):
    """The old setx override must not cause six or eight Paddle GPU models."""
    monkeypatch.setenv("PICTURE_CAPTURE_ORDINARY_WORKERS", "8")
    for pages, cores in ((1, 24), (100, 24), (500, 48), (5, 4)):
        assert ordinary_draw_workers(pages, cpu_count=cores) == 1
        assert ordinary_draw_workers(pages, cpu_count=cores, override="8") == 1
        assert ordinary_draw_workers(pages, cpu_count=cores, override="1") == 1
        assert ordinary_draw_workers(pages, cpu_count=cores, override="") == 1



def test_parallel_path_remains_guarded_but_policy_cannot_activate_gpu_duplication():
    source = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    start = source.index("    def _detect_pages(")
    end = source.index("\n    def clear_entries(", start)
    handler = source[start:end]
    assert 'indices = list(dict.fromkeys(indices))' in handler
    assert ordinary_draw_workers(50, cpu_count=24, override="8") == 1
    assert 'if method == "left_edge" and ordinary_workers > 1:' in handler
    assert "detect_entries_job," in handler
    assert "max_workers=ordinary_workers" in handler
    assert "foreground_page_edit=True," in handler
    assert "page_indexer=lambda index: int(index)" in handler
    assert "if method == \"left_edge\" and ordinary_workers <= 1 else None" in handler
    assert "preserve_prior_pdic(" in handler  # OCR path unchanged
    assert "self.save_pdic(silent=True)" in handler  # foreground flushed first


def test_parallel_batch_manual_claim_prevents_submitting_or_overwriting_pending_page(monkeypatch):
    """Two running pages can finish, a pending manually edited page is skipped."""
    from picture_capture import app as gui

    release = Event()
    started = Event()
    counter_lock = Lock()
    running = []
    executed = []

    class Executor:
        def __init__(self, max_workers, mp_context):
            self.pool = ThreadPoolExecutor(max_workers=max_workers)
            self.count = max_workers
        def submit(self, fn, *args):
            return self.pool.submit(fn, *args)
        def shutdown(self, *, wait, cancel_futures):
            self.pool.shutdown(wait=wait, cancel_futures=cancel_futures)

    monkeypatch.setattr(gui, "ProcessPoolExecutor", Executor)

    class Var:
        def __init__(self): self.value = ""
        def set(self, value): self.value = value
        def get(self): return self.value

    class Button:
        def configure(self, **_kwargs): pass

    class Bar:
        def winfo_manager(self): return True
        def pack(self, **_kwargs): pass

    class Fake:
        def __init__(self):
            self._batch_active = False
            self._ui_close_requested = False
            self._batch_state_lock = Lock()
            self._batch_page_states = {}
            self._batch_pause_event = Event()
            self._batch_stop_event = Event()
            self._batch_queue = Queue()
            self.batch_progress_var = Var()
            self.batch_text_var = Var()
            self.batch_progress = Button()
            self.batch_pause_button = Button()
            self.batch_stop_button = Button()
            self.batch_bar = Bar()
            self.status_var = Var()
            self._batch_refresh_page_quality = True
            self._batch_foreground_pages = False
            self._batch_skipped_count = 0
            self.current_index = 2
            self._updated_pages = []
        def _ui_worker_key_active(self, _): return False
        def _flush_deferred_page_save(self): pass
        def _update_page_row(self, index): self._updated_pages.append(index)
        def after(self, delay, callback): return 123
        def _poll_batch_queue(self): pass

    fake = Fake()

    def worker(page):
        with counter_lock:
            executed.append(page)
            running.append(page)
            if len(running) == 2:
                started.set()
        assert release.wait(5), "test never released workers"
        return page * 10

    got = []
    try:
        assert gui.PictureCaptureApp._start_parallel_batch_task(
            fake, "ordinary", [0, 1, 2], worker,
            lambda item, *_: (item,),
            result_consumer=lambda item, value: {"index": item, "count": value},
            on_done=lambda *args: got.append(args),
            item_label=str, max_workers=2,
            foreground_page_edit=True, page_indexer=int,
        )
        assert started.wait(5), "workers were not dispatched in parallel"
        assert fake._batch_page_states == {
            0: "processing", 1: "processing", 2: "pending",
        }
        # This is the real foreground ownership method: it must mark the
        # pending page manual_locked before another worker can claim it.
        assert gui.PictureCaptureApp._claim_page_for_manual_edit(fake, 2)
        assert fake._batch_page_states[2] == "manual_locked"
    finally:
        release.set()
    fake._batch_thread.join(timeout=6)
    assert not fake._batch_thread.is_alive()
    assert set(executed) == {0, 1}
    assert fake._batch_page_states == {
        0: "done", 1: "done", 2: "manual_locked",
    }
    assert fake._batch_skipped_count == 1
    events = list(fake._batch_queue.queue)
    assert len([e for e in events if e[0] == "parallel_progress"]) == 2
    assert len([e for e in events if e[0] == "skipped"]) == 1
    assert events[-1][0] == "done" and events[-1][1] == 3
    assert len(events[-1][4]) == 2


def test_parallel_progress_events_carry_page_identity_for_safe_foreground_reload():
    source = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    start = source.index("    def _start_parallel_batch_task(")
    end = source.index("    def _finish_batch_task(", start)
    block = source[start:end]
    assert 'self._batch_page_states[item_index] = "processing"' in block
    assert 'self._batch_page_states[item_index] = "done"' in block
    assert 'if state == "manual_locked":' in block
    assert '"skipped", completed, total, label, item_index' in block
    assert "len(futures) < workers" in block  # never pre-queue whole project
    assert "and not self._batch_stop_event.is_set()" in block
    assert 'and self._foreground_batch_state(item_index) == "done"' in block
    assert "self.load_page(item_index)" in block
