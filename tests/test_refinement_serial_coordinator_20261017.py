"""No stall at the first completed Auto Layout refinement page.

Exercise the actual legacy PR #543 batch runner with a synthetic Tk-less
application. Compute and guarded publication stay on the background thread.
"""
from __future__ import annotations

import queue
import threading
from pathlib import Path
from types import SimpleNamespace

from picture_capture import app as gui
from picture_capture import refinement_serial_coordinator as coordinator


class _Var:
    def __init__(self):
        self.values = []

    def set(self, value):
        self.values.append(value)


class _Widget:
    def configure(self, **kwargs):
        pass

    def winfo_manager(self):
        return True

    def pack(self, **kwargs):
        pass


def _app():
    app = SimpleNamespace(
        _batch_active=False,
        _batch_parallel=False,
        _batch_state_lock=threading.Lock(),
        _batch_page_states={},
        _batch_queue=queue.Queue(),
        _batch_stop_event=threading.Event(),
        _batch_pause_event=threading.Event(),
        _ui_close_requested=False,
        _ui_worker_key_active=lambda _: False,
        _flush_deferred_page_save=lambda: None,
        _update_page_row=lambda _: None,
        batch_progress_var=_Var(),
        batch_text_var=_Var(),
        status_var=_Var(),
        batch_progress=_Widget(),
        batch_pause_button=_Widget(),
        batch_stop_button=_Widget(),
        batch_bar=_Widget(),
        after=lambda *_: None,
    )
    app._start_batch_task = lambda *args, **kwargs: gui.PictureCaptureApp._start_batch_task(
        app, *args, **kwargs,
    )
    return app


def _drain(app):
    app._batch_thread.join(5)
    assert not app._batch_thread.is_alive(), "Batch stalled after first page"
    events = []
    while not app._batch_queue.empty():
        events.append(app._batch_queue.get_nowait())
    return events


def test_real_serial_scheduler_advances_from_first_page_to_end(monkeypatch):
    app = _app()
    calls = []
    done = []
    main_thread = threading.get_ident()

    def calculate(page, _settings, index):
        assert threading.get_ident() != main_thread
        calls.append(("compute", index))
        return {"index": index, "page": page}

    def commit(index, result, owned):
        assert owned(index)
        assert result["index"] == index
        calls.append(("commit", index))
        return {"index": index, "moved": 1, "skipped": 0}

    monkeypatch.setattr(coordinator, "refine_page_job", calculate)
    monkeypatch.setattr(coordinator, "commit_refined_page_result", commit)
    pages = [Path(f"page_{i:03}.png") for i in range(4)]
    assert coordinator.start_layout_refinement_batch(
        app, [0, 1, 2, 3], pages, object(), lambda *args: done.append(args),
    )
    events = _drain(app)
    assert calls == [
        ("compute", 0), ("commit", 0),
        ("compute", 1), ("commit", 1),
        ("compute", 2), ("commit", 2),
        ("compute", 3), ("commit", 3),
    ]
    assert [row[0] for row in events] == ["item", "progress"] * 4 + ["done"]
    assert events[-1][1:4] == (4, 4, False)
    assert app._batch_page_states == {0: "done", 1: "done", 2: "done", 3: "done"}
    assert not done  # Tk poller, not compute thread, owns the completion callback


def test_manual_lock_before_next_page_is_respected(monkeypatch):
    app = _app()
    started_first = threading.Event()
    continue_first = threading.Event()
    processed = []

    def calculate(page, settings, index):
        processed.append(index)
        if index == 0:
            started_first.set()
            assert continue_first.wait(3), "Test release timed out"
        return {"index": index, "page": page}

    def commit(index, result, owned):
        assert owned(index)
        return {"index": index, "moved": 1}

    monkeypatch.setattr(coordinator, "refine_page_job", calculate)
    monkeypatch.setattr(coordinator, "commit_refined_page_result", commit)
    pages = [Path(f"page_{i:03}.png") for i in range(3)]
    assert coordinator.start_layout_refinement_batch(
        app, [0, 1, 2], pages, object(), lambda *args: None,
    )
    assert started_first.wait(2)
    with app._batch_state_lock:
        assert app._batch_page_states[2] == "pending"
        app._batch_page_states[2] = "manual_locked"
    continue_first.set()
    events = _drain(app)
    assert processed == [0, 1]
    assert [x[0] for x in events] == [
        "item", "progress", "item", "progress", "skipped", "done",
    ]
    assert events[-1][1:4] == (3, 3, False)
    assert app._batch_page_states[2] == "manual_locked"


def test_only_auto_layout_path_uses_legacy_serial_scheduler():
    app_source = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    block = app_source.split("    def refine_lines_selected_scope(", 1)[1].split(
        "    def ocr_ordinary_lines_text_selected_scope(", 1
    )[0]
    assert "if needs_layout:" in block
    assert "start_layout_refinement_batch(self, indices, pages, settings, done)" in block
    assert block.index("start_layout_refinement_batch(") < block.index(
        'self._start_parallel_batch_task('
    )
    assert 'foreground_page_edit=True, allow_pdic_edits=True' in block
    assert "commit_refined_page_result" in block
