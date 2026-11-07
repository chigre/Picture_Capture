"""R4.2 synthetic: ReviewWindow crop failure must respect its live page/geometry owner.

The app's background_job_runtime already rejects terminal callbacks from a
superseded same-key *worker generation*.  These tests instead cover a page or
geometry change that occurs before replacement dispatch and a failure to start
the current worker, both outside that generation filter.
"""
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui import review_workspace_workflow as flow


@dataclass
class Entry:
    word: str = "synthetic"
    x: int = 12
    y: int = 34


@dataclass
class Settings:
    review_zoom_percent: int = 100


class Text:
    def get(self):
        return "synthetic"


def _harness():
    page = Path("/synthetic/review-crop-failure/page.png")
    entry = Entry()
    launched = []
    failures = []
    status = []
    existing_editor = object()

    def launch(key, worker, done, failed):
        if failures:
            raise failures.pop(0)
        launched.append((key, worker, done, failed))

    parent = SimpleNamespace(
        project=SimpleNamespace(root=page.parent, images=[page]),
        current_page=page, current_index=0, image=object(),
        settings=Settings(),
        canvas=SimpleNamespace(winfo_width=lambda: 800),
        _ordered_entries_reading_order=lambda: [entry],
        _start_ui_worker=launch,
        status_var=SimpleNamespace(set=lambda message: status.append(message)),
    )
    review = SimpleNamespace(
        parent=parent, vars=[Text()], row_entries=[entry],
        active_index=0, _filter_rows_active=False,
        review_zoom_auto=False, review_zoom=1.0,
        _prefetch_closed=False, _review_render_worker_key="synthetic-review-worker",
        _bound_row_entries=lambda: [entry], _review_image_area_width=lambda: 700,
        winfo_exists=lambda: True,
        rows=SimpleNamespace(winfo_children=lambda: [existing_editor]),
        editors=[existing_editor],
    )
    deps = SimpleNamespace(
        ttk=SimpleNamespace(), tk=SimpleNamespace(TclError=RuntimeError),
        Image=SimpleNamespace(), _format_layout_percent=str,
        _review_crop_context=lambda *a: None,
        _review_line_box=lambda *a, **kw: None,
        sync_review_entry_classification=lambda *_: None,
        normalize_page_rgb=lambda opened: opened,
        review_auto_fit_zoom=lambda *a: 1.0,
        replace=replace,
    )

    def request():
        flow._request_render_rows(review, deps, focus_index=0)

    return parent, review, launched, failures, status, existing_editor, request


def test_old_page_failure_without_replacement_dispatch_cannot_mask_new_page():
    parent, review, launched, _, status, editor, request = _harness()
    request()
    assert len(launched) == 1
    parent.current_page = parent.current_page.with_name("next-page.png")
    parent.current_index = 1
    launched[0][3](RuntimeError("old page crop failed"), "")
    assert status == [], "outdated page crop error masked the new page"
    assert review.editors == [editor]


def test_outdated_geometry_failure_cannot_mask_current_review_state():
    parent, review, launched, _, status, editor, request = _harness()
    request()
    parent.settings.review_zoom_percent = 125
    launched[0][3](RuntimeError("old geometry crop failed"), "")
    assert status == [], "outdated geometry crop error masked current review"
    assert review.editors == [editor]


def test_current_worker_failure_remains_visible_and_editors_survive():
    _, review, launched, _, status, editor, request = _harness()
    request()
    launched[0][3](RuntimeError("active crop failure"), "")
    assert len(status) == 1 and "active crop failure" in status[0]
    assert review.editors == [editor]


def test_failed_thread_launch_is_visible_and_can_be_retried():
    _, review, launched, failures, status, editor, request = _harness()
    failures.append(RuntimeError("synthetic worker start unavailable"))
    request()
    assert len(status) == 1 and "synthetic worker start unavailable" in status[0]
    assert launched == []
    assert review.editors == [editor]
    request()
    assert len(launched) == 1, "a failed launch must not strand future crop requests"


def test_os_error_launch_is_visible_without_destroying_existing_editor():
    _, review, launched, failures, status, editor, request = _harness()
    failures.append(OSError("synthetic thread allocation refused"))
    request()
    assert len(status) == 1 and "synthetic thread allocation refused" in status[0]
    assert launched == []
    assert review.editors == [editor]


def test_normal_worker_launch_has_no_false_failure_banner():
    _, _, launched, _, status, _, request = _harness()
    request()
    assert len(launched) == 1
    assert status == []
