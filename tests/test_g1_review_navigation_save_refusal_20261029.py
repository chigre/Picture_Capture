"""G1 fail-first: a refused ReviewWindow save must cancel page navigation.

Exercise real source callbacks with lightweight owners, not textual assertions.
The pre-fix page-sync helper mistakes a False return for a successful save,
while both navigation entry points continue and can discard unsaved text.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui.review_page_sync import save_review_before_page_change
from picture_capture.ui import project_session_workflow, review_page_lifecycle
from picture_capture.ui.controllers.page import PageController


class RefusingReview:
    _rendered_page_stem = "001"
    _filter_rows_active = False

    def __init__(self):
        self.attempts = 0

    def winfo_exists(self):
        return True

    def save(self, *, redraw_main=False):
        self.attempts += 1
        return False


def _app_with_refusing_review():
    review = RefusingReview()
    statuses = []
    selections = []
    page = Path("001.png")
    app = SimpleNamespace(
        project=SimpleNamespace(images=[page, Path("002.png")]),
        current_page=page,
        current_index=0,
        _pending_page_index=1,
        _batch_active=False,
        _can_save_current_during_batch_navigation=lambda: True,
        review_window=review,
        status_var=SimpleNamespace(set=statuses.append),
        _set_page_list_selection=lambda idx, **kw: selections.append(idx),
        _invalidate_ui_worker=lambda *_: (_ for _ in ()).throw(
            AssertionError("navigation invalidated current page despite refused save")
        ),
    )
    return app, review, statuses, selections


def _deps():
    # load_page must reject the failed old-page save before reading the target.
    def never(*args, **kwargs):
        raise AssertionError("target page must not be opened after failed review save")
    names = (
        "Image", "ImageTk", "json", "touch_recent_project", "ocr_cache_root",
        "pdic_path", "read_page_sections", "read_pdic", "read_ppp",
        "normalize_page_rgb", "normalize_appearance_mode",
    )
    return SimpleNamespace(**{name: never for name in names})


def test_refused_save_is_not_treated_as_committed_review():
    app, review, _, _ = _app_with_refusing_review()
    result = save_review_before_page_change(app, 1)
    assert result is None, "None is the fail-closed review-save outcome"
    assert review.attempts == 1


def test_main_load_page_cancels_on_refused_review_save():
    app, review, statuses, selections = _app_with_refusing_review()
    result = project_session_workflow.load_page(app, _deps(), 1)
    assert result is False
    assert app.current_index == 0
    assert app.current_page == Path("001.png")
    assert app._pending_page_index is None
    assert selections == [0]
    assert statuses
    assert review.attempts == 1


def test_review_pager_does_not_preload_or_request_next_page_on_refused_save():
    calls = []
    parent = SimpleNamespace(
        current_index=0,
        change_page=lambda *args, **kw: calls.append(("change", args, kw)),
    )
    review = SimpleNamespace(
        parent=parent,
        save=lambda **kw: False,
        _take_prefetched_page=lambda *_: calls.append(("prefetch",)) or {},
    )
    assert review_page_lifecycle.change_page(review, None, 1) is None
    assert calls == []


def test_page_controller_reports_refused_synchronous_load(tmp_path):
    # A navigation request must not claim success after the underlying load
    # explicitly refused to abandon a dirty ReviewWindow.
    page = Path("001.png")
    app = SimpleNamespace(
        project=SimpleNamespace(images=[page, Path("002.png")]),
        current_index=0,
        _pending_page_index=None,
        _batch_active=False,
        image=object(),
        load_page=lambda *_a, **_kw: False,
    )
    assert PageController(app).change_page(1, async_allowed=False) is False
