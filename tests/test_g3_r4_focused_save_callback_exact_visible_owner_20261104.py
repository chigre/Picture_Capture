"""R4.2 synthetic callback owner: exact displayed page and source XY only.

No OCR, GUI, real PDIC publication, dictionary or human acceptance. The
injected scheduler returns a success/failure payload for a *valid* edit while
the visible target can no longer prove the same source marker.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui import focused_filter_workflow as workflow


class _Status:
    def __init__(self):
        self.messages = []

    def set(self, value):
        self.messages.append(value)


INVALID_VISIBLE_OWNER = [
    ("page_index", 0.0), ("page_index", "0"), ("page_index", False),
    ("x", 3.9), ("x", "3"), ("x", "malformed"),
    ("y", 4.9), ("y", "4"), ("y", "malformed"),
]


def _case(*, bad=None, visible_word="old", main_entry=None):
    valid = {"page_index": 0, "x": 3, "y": 4,
             "original_word": "old", "current_word": visible_word}
    if bad is not None:
        valid[bad[0]] = bad[1]
    change = {"page_index": 0, "x": 3, "y": 4,
              "original_word": "old", "new_word": "edited"}
    dispatch, alerts, timers = [], [], []
    parent = SimpleNamespace(
        project=SimpleNamespace(images=[Path("synthetic.png")]),
        status_var=_Status(),
        current_index=0 if main_entry is not None else None,
        entries=[] if main_entry is None else [main_entry],
        _start_ui_worker=lambda *args, **kwargs: dispatch.append((args, kwargs)),
    )
    review = SimpleNamespace(
        parent=parent, filtered_targets=[valid],
        _filter_rows_active=False,  # isolated callback adapter; no real scan
        _filter_pending_changes={0: {(3, 4): change}},
        _filter_save_job=None, _filter_save_running=False,
        _filter_close_after_save=False, _focused_timing_session=None,
        after=lambda ms, callback: timers.append(ms) or "synthetic-after",
    )
    deps = SimpleNamespace(
        _apply_focused_review_page_updates=lambda *_args: ([], []),
        messagebox=SimpleNamespace(
            showerror=lambda *args, **kwargs: alerts.append(("error", args)),
            showwarning=lambda *args, **kwargs: alerts.append(("warning", args)),
        ),
    )
    workflow._flush_focused_changes(review, deps)
    assert len(dispatch) == 1
    assert review._filter_pending_changes == {}
    key, worker, done, failed = dispatch[0][0]
    assert callable(worker) and callable(done) and callable(failed)
    return SimpleNamespace(review=review, parent=parent, target=valid,
                           change=change, done=done, failed=failed,
                           alerts=alerts, timers=timers)


@pytest.mark.parametrize(("field", "bad_value"), INVALID_VISIBLE_OWNER)
def test_failed_save_restores_valid_edit_even_if_display_owner_is_invalid(
    field, bad_value,
):
    """Invalid visible rows cannot masquerade as the original user's revert."""
    case = _case(bad=(field, bad_value), visible_word="old")
    case.failed(RuntimeError("SYNTHETIC_IO_FAILURE"), "PRIVATE_SYNTHETIC_PATH")
    assert case.review._filter_save_running is False
    assert case.review._filter_pending_changes[0][(3, 4)] is case.change
    assert case.target["original_word"] == "old"
    assert len(case.alerts) == 1
    assert "PRIVATE_SYNTHETIC_PATH" not in str(case.parent.status_var.messages)


@pytest.mark.parametrize(("field", "bad_value"), INVALID_VISIBLE_OWNER)
def test_successful_save_never_reconciles_aliased_invalid_display_target(
    field, bad_value,
):
    """A verified PDIC row cannot assign ownership to a coerced Tk target."""
    case = _case(bad=(field, bad_value), visible_word="old")
    case.done(([(0, 3, 4, "edited")], []))
    assert case.review._filter_save_running is False
    assert case.target["original_word"] == "old"
    assert case.target["current_word"] == "old"
    assert case.review._filter_pending_changes == {}
    assert case.alerts == []


@pytest.mark.parametrize(("field", "bad_value"), [
    ("x", 3.9), ("x", "3"), ("y", 4.9), ("y", "4"),
])
def test_successful_save_never_overwrites_aliased_invalid_main_canvas_entry(
    field, bad_value,
):
    """Main canvas may be stale or malformed independently of ReviewWindow."""
    main = SimpleNamespace(
        x=3, y=4, word="main-old", confidence=0.6,
        ocr_source="ocr", final_engine="ocr", manually_selected=False,
    )
    setattr(main, field, bad_value)
    case = _case(visible_word="edited", main_entry=main)
    case.done(([(0, 3, 4, "edited")], []))
    assert main.word == "main-old"
    assert main.confidence == 0.6
    assert main.ocr_source == "ocr"
    assert main.manually_selected is False
    assert case.review._filter_pending_changes == {}


def test_valid_visible_owner_and_canvas_entry_still_reconcile():
    """Positive control: all genuine int page/XY identities behave unchanged."""
    main = SimpleNamespace(
        x=3, y=4, word="main-old", confidence=0.6,
        ocr_source="ocr", final_engine="ocr", manually_selected=False,
    )
    case = _case(visible_word="edited", main_entry=main)
    case.done(([(0, 3, 4, "edited")], []))
    assert case.target["original_word"] == "edited"
    assert case.review._filter_pending_changes == {}
    assert main.word == "edited"
    assert main.confidence is None
    assert main.ocr_source == "manual"
    assert main.final_engine == "manual"
    assert main.manually_selected is True


def test_valid_display_owner_failed_save_restores_unsaved_edit():
    case = _case(visible_word="edited")
    case.failed(RuntimeError("synthetic-failure"), "PRIVATE_SYNTHETIC_PATH")
    assert case.review._filter_pending_changes[0][(3, 4)] is case.change
    assert case.target["original_word"] == "old"


@pytest.mark.parametrize("outcome", ["failure", "success"])
def test_duplicate_visible_owner_never_claims_save_callback(outcome):
    """A duplicated source XY cannot prove which Tk row owns this change."""
    case = _case(visible_word="edited")
    other = {
        "page_index": 0, "x": 3, "y": 4,
        "original_word": "old", "current_word": "old",
    }
    case.review.filtered_targets.append(other)
    if outcome == "failure":
        case.failed(RuntimeError("synthetic-failure"), "PRIVATE_SYNTHETIC_PATH")
        assert case.review._filter_pending_changes[0][(3, 4)] is case.change
    else:
        case.done(([(0, 3, 4, "edited")], []))
        assert case.review._filter_pending_changes == {}
    assert case.target["original_word"] == "old"
    assert other["original_word"] == "old"


def test_duplicate_main_canvas_source_xy_never_updates_either_entry():
    """A valid PDIC commit is not evidence for either ambiguous live Entry."""
    first = SimpleNamespace(
        x=3, y=4, word="first-old", confidence=0.6,
        ocr_source="ocr", final_engine="ocr", manually_selected=False,
    )
    second = SimpleNamespace(
        x=3, y=4, word="second-old", confidence=0.7,
        ocr_source="ocr", final_engine="ocr", manually_selected=False,
    )
    case = _case(visible_word="edited", main_entry=first)
    case.parent.entries.append(second)
    case.done(([(0, 3, 4, "edited")], []))
    assert case.target["original_word"] == "edited"
    assert (first.word, second.word) == ("first-old", "second-old")
    assert first.manually_selected is False
    assert second.manually_selected is False


@pytest.mark.parametrize("index", [0.0, "0", False, "invalid"])
def test_nonintegral_or_noninteger_main_page_index_cannot_alias_saved_page(index):
    """Cross-page main canvas synchronization requires a genuine page index."""
    main = SimpleNamespace(
        x=3, y=4, word="main-old", confidence=0.6,
        ocr_source="ocr", final_engine="ocr", manually_selected=False,
    )
    case = _case(visible_word="edited", main_entry=main)
    case.parent.current_index = index
    case.done(([(0, 3, 4, "edited")], []))
    assert case.target["original_word"] == "edited"
    assert main.word == "main-old"
    assert main.manually_selected is False
    assert case.review._filter_pending_changes == {}
