"""G1 fail-first: incomplete filtered-review write must block view/page switches.

These callbacks operate on modeless Tk state; a background filtered PDIC
worker can fail or be delayed after the UI has destroyed the editing rows.
The pre-fix flow silently moves to the next mode/page despite unsaved edits.
"""
from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui import review_page_sync, review_workspace_workflow
from picture_capture.ui import project_session_workflow


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FilterReview:
    _filter_rows_active = True
    _rendered_page_stem = "foreign-target-stem"

    def __init__(self, answer=False):
        self.answer = answer
        self.calls = []

    def winfo_exists(self):
        return True

    def save(self, *, redraw_main=False):
        self.calls.append(("save", redraw_main))
        return self.answer


def _app(answer=False):
    review = FilterReview(answer=answer)
    statuses, selected = [], []
    app = SimpleNamespace(
        project=SimpleNamespace(images=[Path("001.png"), Path("002.png")]),
        current_page=Path("001.png"), current_index=0,
        review_window=review, _batch_active=False,
        _can_save_current_during_batch_navigation=lambda: True,
        _pending_page_index=1, status_var=SimpleNamespace(set=statuses.append),
        _set_page_list_selection=lambda index, **kw: selected.append(index),
        _invalidate_ui_worker=lambda *_: (_ for _ in ()).throw(
            AssertionError("must not invalidate old page before filter save succeeds")
        ),
    )
    return app, review, statuses, selected


def _deps():
    def forbidden(*args, **kwargs):
        raise AssertionError("failed filtered save must not load target or mutate current page")
    return SimpleNamespace(**{name: forbidden for name in (
        "Image", "ImageTk", "json", "touch_recent_project", "ocr_cache_root",
        "pdic_path", "read_page_sections", "read_pdic", "read_ppp",
        "normalize_page_rgb", "normalize_appearance_mode",
    )})


def test_pending_filtered_save_refuses_parent_page_transition():
    app, review, _, _ = _app(False)
    assert review_page_sync.save_review_before_page_change(app, 1) is None
    assert review.calls == [("save", False)]


def test_main_page_commit_cannot_discard_unfinished_filtered_save():
    app, review, statuses, selected = _app(False)
    assert project_session_workflow.load_page(app, _deps(), 1) is False
    assert app.current_index == 0 and app.current_page == Path("001.png")
    assert app._pending_page_index is None
    assert selected == [0]
    assert statuses and review.calls == [("save", False)]


def _mode_fixture(*, running=True, pending=None):
    records = []
    mode = Var("single")
    review = SimpleNamespace(
        review_mode_var=mode,
        _filter_rows_active=True,
        _filter_save_running=False,
        _filter_pending_changes={} if pending is None else pending,
        _flush_focused_changes_now=lambda: (
            records.append("flush"), setattr(review, "_filter_save_running", running)
        ),
        _set_filter_navigation=lambda flag: records.append(("navigation", flag)),
        _request_render_rows=lambda **kwargs: records.append(("render", kwargs)),
        _filter_batch_render_cache={"key": "value"},
        _filter_prefetch_key=("old",),
        parent=SimpleNamespace(
            status_var=SimpleNamespace(set=lambda value: records.append(("status", value))),
            _invalidate_ui_worker=lambda key: records.append(("invalidate", key)),
        ),
    )
    return review, records


def test_switch_to_single_refuses_while_filtered_worker_is_running():
    review, calls = _mode_fixture(running=True)
    review_workspace_workflow._change_review_mode(review, None)
    assert review._filter_rows_active is True
    assert review.review_mode_var.get() == "filter"
    assert not any(x == "render" or isinstance(x, tuple) and x[0] == "render" for x in calls)
    assert review._filter_batch_render_cache == {"key": "value"}


def test_switch_to_single_refuses_if_unsaved_filtered_snapshot_remains():
    review, calls = _mode_fixture(running=False, pending={1: {(10, 11): {"new_word": "人工"}}})
    review_workspace_workflow._change_review_mode(review, None)
    assert review._filter_rows_active is True
    assert review.review_mode_var.get() == "filter"
    assert not any(isinstance(x, tuple) and x[0] == "render" for x in calls)


def test_clean_filtered_switch_to_single_still_works():
    review, calls = _mode_fixture(running=False, pending={})
    review_workspace_workflow._change_review_mode(review, None)
    assert review._filter_rows_active is False
    assert ("navigation", False) in calls
    assert any(isinstance(x, tuple) and x[0] == "render" for x in calls)
