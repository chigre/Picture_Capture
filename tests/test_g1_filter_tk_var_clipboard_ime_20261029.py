"""G1 fail-first: filtered Tk editor must capture paste/IME without KeyRelease.

Run the actual batch-render callback against small headless Tk-like controls.
These tests verify source page/X/Y and that obsolete row variables cannot
write into a different preloaded batch. No display server or OCR is needed.
"""
from __future__ import annotations

from types import SimpleNamespace

from picture_capture.ui import focused_filter_workflow as focused


class Var:
    def __init__(self, value):
        self.value = value
        self.traces = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        for fn in list(self.traces):
            fn("name", "index", "write")

    def trace_add(self, mode, fn):
        assert mode == "write"
        self.traces.append(fn)
        return f"trace-{len(self.traces)}"


class Widget:
    def __init__(self, *args, **kwargs):
        self.bindings = {}
        self.textvariable = kwargs.get("textvariable")

    def winfo_children(self):
        return []

    def destroy(self):
        pass

    def grid(self, *args, **kwargs):
        pass

    def columnconfigure(self, *args, **kwargs):
        pass

    def pack(self, *args, **kwargs):
        pass

    def configure(self, *args, **kwargs):
        pass

    def bind(self, sequence, fn):
        self.bindings[sequence] = fn

    def focus_set(self):
        pass


class Tk:
    TclError = RuntimeError
    StringVar = Var
    Entry = Widget


def _rendered(targets):
    scheduled, cancelled, statuses = [], [], []
    parent = SimpleNamespace(
        settings=SimpleNamespace(
            review_entry_font_family="default",
            ocr_language="chi_sim",
            review_entry_font_bold=False,
            review_entry_font_italic=False,
            review_entry_vertical_padding=0,
        ),
        _project_words=set(),
        appearance_mode="light",
        status_var=SimpleNamespace(set=statuses.append),
    )
    review = SimpleNamespace(
        rows=Widget(), parent=parent, _filter_rows_active=True,
        filter_vars=[], filter_editors=[], filter_thumbnails=[],
        _filter_current_batch_targets=[],
        _filter_pending_changes={}, _filter_save_job=None,
        _review_membership_colors=lambda _: ("white", "black", "blue", "white"),
        after=lambda ms, fn: scheduled.append((ms, fn)) or str(len(scheduled)),
        after_cancel=cancelled.append,
        _flush_focused_changes=lambda: None,
        scroll_rows=lambda *_: None,
        scroll_rows_linux=lambda *_: None,
    )
    dep_tk = Tk()
    review._queue_focused_change = lambda target, value: focused._queue_focused_change(
        review, SimpleNamespace(tk=dep_tk), target, value
    )
    review._commit_filter_editor_value = lambda index: focused._commit_filter_editor_value(
        review, SimpleNamespace(tk=dep_tk), index
    )
    review._on_filter_key = lambda event, index: focused._on_filter_key(
        review, SimpleNamespace(tk=dep_tk), event, index
    )
    review._set_filter_active = lambda index: setattr(review, "filter_active_local_index", index)
    review._focus_filter_index = lambda index: "break"

    dep = SimpleNamespace(
        Image=SimpleNamespace(new=lambda *args, **kwargs: object()),
        tk=dep_tk,
        ttk=SimpleNamespace(Frame=Widget, Label=Widget, Button=Widget),
        ImageTk=SimpleNamespace(PhotoImage=lambda _: object()),
        resolve_content_font_family=lambda *args: "Arial",
        _review_editor_font_size=lambda *args: 12,
        _entry_font_spec=lambda *args: ("Arial", 12),
        themed_display_image=lambda crop, mode: crop,
    )
    def render(items):
        focused._render_filter_batch(review, dep, items, [object() for _ in items])

    render(targets)
    return SimpleNamespace(review=review, scheduled=scheduled, cancelled=cancelled, render=render)


def _target(page_index=2, x=17, y=29, original="甲"):
    return {"page_index": page_index, "page_name": f"{page_index:04d}.png",
            "x": x, "y": y, "original_word": original}


def test_clipboard_or_ime_var_change_queues_exact_source_without_keyrelease():
    f = _rendered([_target()])
    variable = f.review.filter_vars[0]
    variable.set("乙")
    change = f.review._filter_pending_changes[2][(17, 29)]
    assert change == {
        "page_index": 2, "x": 17, "y": 29,
        "original_word": "甲", "new_word": "乙",
    }
    assert f.scheduled[-1][0] == 160
    assert f.review._filter_current_batch_targets[0]["current_word"] == "乙"


def test_focusout_is_bound_and_idempotent_after_var_change():
    f = _rendered([_target()])
    editor = f.review.filter_editors[0]
    variable = f.review.filter_vars[0]
    variable.set("乙")
    queued = len(f.scheduled)
    assert "<FocusOut>" in editor.bindings
    editor.bindings["<FocusOut>"](SimpleNamespace())
    assert len(f.scheduled) == queued
    assert f.review._filter_pending_changes[2][(17, 29)]["new_word"] == "乙"


def test_paste_and_ime_revert_removes_queued_change_even_without_keyrelease():
    f = _rendered([_target()])
    variable = f.review.filter_vars[0]
    variable.set("乙")
    variable.set("甲")
    assert f.review._filter_pending_changes == {}
    assert f.review._filter_current_batch_targets[0]["current_word"] == "甲"
    assert len(f.cancelled) >= 1


def test_obsolete_var_trace_cannot_mutate_new_batch_at_same_local_row():
    f = _rendered([_target()])
    stale_variable = f.review.filter_vars[0]
    f.render([_target(page_index=4, x=80, y=91, original="丙")])
    stale_variable.set("过期输入")
    assert f.review._filter_pending_changes == {}
    assert f.review._filter_current_batch_targets[0].get("current_word") is None
    f.review.filter_vars[0].set("丁")
    assert f.review._filter_pending_changes[4][(80, 91)]["new_word"] == "丁"
    assert 2 not in f.review._filter_pending_changes


def test_normal_initial_render_never_marks_original_text_dirty():
    f = _rendered([_target()])
    assert f.review._filter_pending_changes == {}
    assert f.scheduled == []
