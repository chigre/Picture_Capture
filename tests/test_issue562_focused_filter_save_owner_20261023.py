"""Focused edit and save lifecycle ownership/behavior regressions for #562."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture import app as gui
from picture_capture.ui import focused_filter_workflow as focused
from picture_capture.proofreading import focused_pdic_updates as pdic_owner

ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture"
NAMES = (
    "_persist_focused_filter_settings", "_set_filter_active", "_focus_filter_index",
    "_filter_ocr_word", "_fill_filter_ocr_result", "_commit_filter_editor_value",
    "_on_filter_key", "_queue_focused_change", "_flush_focused_changes_now",
    "_flush_focused_changes",
)


def test_edit_save_has_physical_owners_and_original_callback_abi():
    tree = ast.parse((ROOT / "ui/focused_filter_workflow.py").read_text("utf-8"))
    app_tree = ast.parse((ROOT / "app.py").read_text("utf-8"))
    methods = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    cls = next(n for n in app_tree.body if isinstance(n, ast.ClassDef) and n.name == "ReviewWindow")
    adapters = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
    for name in NAMES:
        assert methods[name].end_lineno - methods[name].lineno >= 4
        assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and isinstance(n.func.value, ast.Name) and n.func.value.id == "_focused_filter"
                   and n.func.attr == name for n in ast.walk(adapters[name]))
    assert list(inspect.signature(gui.ReviewWindow._on_filter_key).parameters) == ["self", "event", "index"]
    assert list(inspect.signature(gui.ReviewWindow._queue_focused_change).parameters) == ["self", "target", "value"]
    assert list(inspect.signature(gui.ReviewWindow._flush_focused_changes).parameters) == ["self"]
    pdic_tree = ast.parse((ROOT / "proofreading/focused_pdic_updates.py").read_text("utf-8"))
    assert any(isinstance(n, ast.FunctionDef) and n.name == "apply_focused_review_page_updates" for n in pdic_tree.body)
    for node in (tree, pdic_tree):
        assert not any(isinstance(n, ast.ImportFrom) and n.module == "app" for n in ast.walk(node))


def test_live_writer_patchpoint_for_background_worker(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(gui, "_apply_focused_review_page_updates", sentinel)
    assert gui._focused_filter_deps()._apply_focused_review_page_updates is sentinel
    assert len(focused.FocusedFilterDeps.__dataclass_fields__) == 29


def test_queue_sanitizes_uses_160ms_and_cancels_reverted_edit():
    scheduled, canceled = [], []
    review = SimpleNamespace(
        _filter_pending_changes={}, _filter_save_job=None,
        after=lambda ms, fn: scheduled.append((ms, fn)) or "timer",
        after_cancel=canceled.append,
        _flush_focused_changes=lambda: None,
    )
    deps = SimpleNamespace(tk=SimpleNamespace(TclError=Exception))
    target = {"page_index": 2, "x": 10, "y": 20, "original_word": "甲"}
    focused._queue_focused_change(review, deps, target, "  改\n# ")
    assert review._filter_pending_changes[2][(10, 20)]["new_word"] == "改 ＃"
    assert scheduled[-1][0] == 160
    focused._queue_focused_change(review, deps, target, "甲")
    assert review._filter_pending_changes == {}
    assert canceled == ["timer"]
    assert len(scheduled) == 2


def test_serial_save_updates_original_word_and_pending_guard():
    sessions, statuses, scheduled, closed = [], [], [], []
    parent = SimpleNamespace(
        project=SimpleNamespace(images=[Path("0001.png")]),
        current_index=0,
        entries=[SimpleNamespace(x=10, y=20, word="甲", confidence=0.2,
                                 ocr_source="old", final_engine="old", manually_selected=False)],
        status_var=SimpleNamespace(set=statuses.append),
        _start_ui_worker=lambda *a, **kw: sessions.append((a, kw)),
    )
    target = {"page_index": 0, "x": 10, "y": 20, "original_word": "甲"}
    review = SimpleNamespace(
        parent=parent, _filter_save_job=None, _filter_save_running=False,
        _filter_pending_changes={0: {(10, 20): {"page_index": 0, "x": 10, "y": 20,
                                               "original_word": "甲", "new_word": "乙"}}},
        filtered_targets=[target], _filter_close_after_save=False,
        after=lambda ms, cb: scheduled.append((ms, cb)) or "next",
        _flush_focused_changes=lambda: None,
        _finish_close_review=lambda: closed.append(True),
    )
    writes = []
    deps = SimpleNamespace(
        messagebox=SimpleNamespace(showwarning=lambda *a, **k: pytest.fail("unexpected conflict")),
        _apply_focused_review_page_updates=lambda *a: writes.append(a) or ([(0, 10, 20, "乙")], []),
    )
    focused._flush_focused_changes(review, deps)
    assert review._filter_save_running and review._filter_pending_changes == {}
    (name, worker, done, failed), kw = sessions[0]
    assert name.startswith("focused-filter-save-") and kw["wait_on_close"] is True
    review._filter_pending_changes[0] = {(10, 20): {"original_word": "甲", "new_word": "丙", "x": 10, "y": 20}}
    done(worker())
    assert len(writes) == 1
    assert target["original_word"] == "乙"
    assert review._filter_pending_changes[0][(10, 20)]["original_word"] == "乙"
    assert parent.entries[0].word == "乙" and parent.entries[0].ocr_source == "manual"
    assert parent.entries[0].manually_selected
    assert scheduled[0][0] == 1 and not closed
    assert statuses[-1] == "筛选校对已保存 1 条修改"


def test_save_failure_restores_snapshot_and_reports_error():
    callbacks, errors, statuses = [], [], []
    review = SimpleNamespace(
        parent=SimpleNamespace(
            project=SimpleNamespace(images=[Path("0001.png")]),
            _start_ui_worker=lambda *a, **k: callbacks.append(a),
            status_var=SimpleNamespace(set=statuses.append),
        ),
        _filter_save_job=None, _filter_save_running=False,
        _filter_pending_changes={0: {(10, 20): {"page_index": 0, "x": 10, "y": 20,
                                               "original_word": "甲", "new_word": "乙"}}},
    )
    deps = SimpleNamespace(
        _apply_focused_review_page_updates=lambda *args: (_ for _ in ()).throw(OSError("disk")),
        messagebox=SimpleNamespace(showerror=lambda *a, **k: errors.append((a, k))),
    )
    focused._flush_focused_changes(review, deps)
    callbacks[0][3](OSError("disk"), "")
    assert not review._filter_save_running
    assert review._filter_pending_changes[0][(10, 20)]["new_word"] == "乙"
    assert len(errors) == 1 and "保存失败" in statuses[-1]


def test_focused_setting_write_validation_and_clamp():
    class Variable:
        def __init__(self, value):
            self.value = value
        def get(self):
            return self.value
        def set(self, value):
            self.value = value
    settings, saved = SimpleNamespace(), []
    review = SimpleNamespace(
        parent=SimpleNamespace(settings=settings, save_settings=lambda: saved.append(True)),
        focused_include_mismatch_var=Variable(True),
        focused_include_characters_var=Variable(False),
        focused_exclude_single_var=Variable(True),
        focused_exclude_reference_var=Variable(False),
        focused_characters_var=Variable("  字  "),
        focused_batch_size_var=Variable("999"),
    )
    focused._persist_focused_filter_settings(review, SimpleNamespace())
    assert settings.focused_review_batch_size == 500
    assert review.focused_batch_size_var.get() == "500"
    assert settings.focused_review_characters == "字" and len(saved) == 1
    review.focused_batch_size_var.set("bad")
    with pytest.raises(ValueError, match="整数"):
        focused._persist_focused_filter_settings(review, SimpleNamespace())
    assert len(saved) == 1
