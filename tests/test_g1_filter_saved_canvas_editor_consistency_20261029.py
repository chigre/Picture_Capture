"""G1 fail-first: filtered saved PDIC must not be undone by stale canvas editors.

The focused worker commits words to PDIC and updates Entry.word on the Tk
thread. An existing main-canvas Entry widget may still contain the old word;
a subsequent ordinary page-switch save calls _sync_entry_editor_texts and
would revert the already-committed human correction.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui import focused_filter_workflow as focused
from picture_capture.ui import main_pdic_persistence


class Editor:
    def __init__(self, text):
        self.text = text

    def get(self):
        return self.text

    def delete(self, _start, _end):
        self.text = ""

    def insert(self, _start, value):
        self.text = value


def test_filtered_success_reconciles_only_saved_canvas_row():
    callbacks, statuses = [], []
    primary = SimpleNamespace(x=10, y=20, word="甲", confidence=0.9,
                              ocr_source="old", final_engine="old",
                              manually_selected=False)
    unrelated = SimpleNamespace(x=30, y=40, word="丙", confidence=0.9,
                                ocr_source="old", final_engine="old",
                                manually_selected=False)
    primary_editor, unrelated_editor = Editor("甲"), Editor("丙")
    app = SimpleNamespace(
        project=SimpleNamespace(images=[Path("001.png")]),
        current_index=0,
        entries=[primary, unrelated],
        entry_editor_bindings=[
            (primary_editor, primary), (unrelated_editor, unrelated),
        ],
        status_var=SimpleNamespace(set=statuses.append),
        _start_ui_worker=lambda *args, **kwargs: callbacks.append(args),
    )
    review = SimpleNamespace(
        parent=app,
        _filter_save_job=None,
        _filter_save_running=False,
        _filter_pending_changes={0: {(10, 20): {
            "page_index": 0, "x": 10, "y": 20,
            "original_word": "甲", "new_word": "乙",
        }}},
        filtered_targets=[{
            "page_index": 0, "x": 10, "y": 20, "original_word": "甲",
        }],
        _filter_close_after_save=False,
        after=lambda *_: "timer",
    )
    deps = SimpleNamespace(
        messagebox=SimpleNamespace(showwarning=lambda *_a, **_k: None),
        _apply_focused_review_page_updates=lambda *_a: (
            [(0, 10, 20, "乙")], [],
        ),
    )
    focused._flush_focused_changes(review, deps)
    name, worker, done, failed = callbacks[0]
    assert name.startswith("focused-filter-save-")
    done(worker())
    assert primary.word == "乙"

    # This is the critical follow-on navigation save; the already-written
    # PDIC word must not be reverted from the stale Tk canvas buffer.
    main_pdic_persistence._sync_entry_editor_texts(
        app, deps={"tk": SimpleNamespace(TclError=RuntimeError)},
    )
    assert primary.word == "乙"
    assert primary_editor.get() == "乙"

    # An unrelated canvas row must never be repainted by a filtered write.
    assert unrelated.word == "丙" and unrelated_editor.get() == "丙"


@pytest.mark.parametrize("change_kind", [
    "word_and_editor", "editor_buffer_only", "entry_replaced", "editor_replaced",
])
def test_inflight_main_canvas_change_survives_verified_focused_save(change_kind):
    """The saved PDIC word must not silently overwrite a *newer* canvas edit.

    A verified worker result proves disk publication for the focused snapshot,
    not ownership of an independently editable main-canvas Entry/widget whose
    text, binding, or identity changed after the dispatch.
    """
    callbacks, statuses = [], []
    main_entry = SimpleNamespace(
        x=10, y=20, word="old", confidence=0.9,
        ocr_source="ocr", final_engine="ocr", manually_selected=False,
    )
    editor = Editor("old")
    app = SimpleNamespace(
        project=SimpleNamespace(images=[Path("synthetic-only.png")]),
        current_index=0,
        entries=[main_entry],
        entry_editor_bindings=[(editor, main_entry)],
        status_var=SimpleNamespace(set=statuses.append),
        _start_ui_worker=lambda *args, **kwargs: callbacks.append(args),
    )
    review = SimpleNamespace(
        parent=app, _filter_save_job=None, _filter_save_running=False,
        _filter_pending_changes={0: {(10, 20): {
            "page_index": 0, "x": 10, "y": 20,
            "original_word": "old", "new_word": "focused-saved",
        }}},
        filtered_targets=[{
            "page_index": 0, "x": 10, "y": 20,
            "original_word": "old", "current_word": "focused-saved",
        }],
        _filter_close_after_save=False, after=lambda *_args: "synthetic-timer",
    )
    deps = SimpleNamespace(
        messagebox=SimpleNamespace(showwarning=lambda *_a, **_k: None),
        _apply_focused_review_page_updates=lambda *_a: (
            [(0, 10, 20, "focused-saved")], [],
        ),
    )

    focused._flush_focused_changes(review, deps)
    assert len(callbacks) == 1
    _name, worker, done, _failed = callbacks[0]
    assert review._filter_save_running

    if change_kind == "word_and_editor":
        main_entry.word = "newer-human"
        editor.text = "newer-human"
    elif change_kind == "editor_buffer_only":
        editor.text = "newer-uncommitted"
    elif change_kind == "entry_replaced":
        main_entry = SimpleNamespace(
            x=10, y=20, word="newer-entry", confidence=0.9,
            ocr_source="ocr", final_engine="ocr", manually_selected=False,
        )
        editor = Editor("newer-entry")
        app.entries = [main_entry]
        app.entry_editor_bindings = [(editor, main_entry)]
    else:
        editor = Editor("newer-editor")
        app.entry_editor_bindings = [(editor, main_entry)]

    before_word, before_buffer = main_entry.word, editor.get()
    done(worker())
    assert main_entry.word == before_word
    assert editor.get() == before_buffer
    assert main_entry.ocr_source == "ocr"
    assert main_entry.manually_selected is False
    assert review.filtered_targets[0]["original_word"] == "focused-saved"
    assert review._filter_save_running is False


def test_unmodified_canvas_snapshot_still_reconciles_verified_focused_save():
    """Positive control: stale, unchanged canvas text is replaced as before."""
    statuses, callbacks = [], []
    main_entry = SimpleNamespace(
        x=10, y=20, word="old", confidence=0.9,
        ocr_source="ocr", final_engine="ocr", manually_selected=False,
    )
    editor = Editor("old")
    app = SimpleNamespace(
        project=SimpleNamespace(images=[Path("synthetic-only.png")]),
        current_index=0, entries=[main_entry],
        entry_editor_bindings=[(editor, main_entry)],
        status_var=SimpleNamespace(set=statuses.append),
        _start_ui_worker=lambda *args, **kwargs: callbacks.append(args),
    )
    review = SimpleNamespace(
        parent=app, _filter_save_job=None, _filter_save_running=False,
        _filter_pending_changes={0: {(10, 20): {
            "page_index": 0, "x": 10, "y": 20,
            "original_word": "old", "new_word": "focused-saved",
        }}},
        filtered_targets=[{
            "page_index": 0, "x": 10, "y": 20,
            "original_word": "old", "current_word": "focused-saved",
        }],
        _filter_close_after_save=False, after=lambda *_args: "synthetic-timer",
    )
    deps = SimpleNamespace(
        messagebox=SimpleNamespace(showwarning=lambda *_a, **_k: None),
        _apply_focused_review_page_updates=lambda *_a: (
            [(0, 10, 20, "focused-saved")], [],
        ),
    )
    focused._flush_focused_changes(review, deps)
    _name, worker, done, _failed = callbacks[0]
    done(worker())
    assert main_entry.word == "focused-saved"
    assert editor.get() == "focused-saved"
    assert main_entry.manually_selected is True
