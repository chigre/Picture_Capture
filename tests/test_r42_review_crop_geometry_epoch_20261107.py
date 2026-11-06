"""R4.2 synthetic: stale ReviewWindow crop callback must not undo UI geometry."""
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

def _launch():
    page = Path("/synthetic/review-geometry/page.png")
    row = Entry()
    width = [800]
    launched, rendered, retried = [], [], []
    parent = SimpleNamespace(
        project=SimpleNamespace(root=page.parent, images=[page]),
        current_page=page, current_index=0, image=object(),
        settings=Settings(),
        canvas=SimpleNamespace(winfo_width=lambda: width[0]),
        _ordered_entries_reading_order=lambda: [row],
        _start_ui_worker=lambda key, work, done, fail: launched.append(done),
    )
    review = SimpleNamespace(
        parent=parent, vars=[Text()], row_entries=[row], active_index=0,
        _filter_rows_active=False, review_zoom_auto=False, review_zoom=1.0,
        _prefetch_closed=False, _review_render_worker_key="geometry-worker",
        _bound_row_entries=lambda: [row], _review_image_area_width=lambda: 700,
        winfo_exists=lambda: True,
        render_rows=lambda **kw: rendered.append(kw),
        _request_render_rows=lambda **kw: retried.append(kw),
        editors=[],
    )
    deps = SimpleNamespace(
        ttk=SimpleNamespace(), tk=SimpleNamespace(TclError=RuntimeError),
        Image=SimpleNamespace(), _format_layout_percent=str,
        _review_crop_context=lambda *a: None,
        _review_line_box=lambda *a, **kw: None,
        sync_review_entry_classification=lambda *_: None,
        normalize_page_rgb=lambda opened: opened,
        review_auto_fit_zoom=lambda *a: 1.0, replace=replace,
    )
    flow._request_render_rows(review, deps, focus_index=0)
    assert len(launched) == 1
    def deliver():
        launched[0]((page.stem, ((id(row), row.x, row.y, row.word),), [object()], 1.0, False))
    return review, width, rendered, retried, deliver

def test_stale_zoom_is_rejected_before_crop_publish():
    review, width, rendered, retried, deliver = _launch()
    review.review_zoom = 1.5
    deliver()
    assert not rendered, "stale zoom crop was painted"
    assert len(retried) == 1

def test_stale_viewport_is_rejected_before_crop_publish():
    review, width, rendered, retried, deliver = _launch()
    width[0] = 540
    deliver()
    assert not rendered, "stale viewer-width crop was painted"
    assert len(retried) == 1

def test_stale_settings_are_rejected_before_crop_publish():
    review, width, rendered, retried, deliver = _launch()
    review.parent.settings.review_zoom_percent = 125
    deliver()
    assert not rendered, "stale settings crop was painted"
    assert len(retried) == 1

def test_identical_crop_geometry_is_accepted():
    review, width, rendered, retried, deliver = _launch()
    deliver()
    assert len(rendered) == 1
    assert not retried
