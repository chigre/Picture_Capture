"""R4.2 synthetic async ReviewWindow crop owner: input revision must match crop.

Capture production worker callback without starting a thread or opening a real
image. Source Entry remains unchanged; human Tk text changes before delivery.
No user images, private words, persisted sidecars, or real OCR.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui import review_workspace_workflow as workflow


@dataclass
class Entry:
    word: str = "first"
    x: int = 12
    y: int = 34


@dataclass
class Settings:
    review_zoom_percent: int = 100


class Value:
    def __init__(self, value):
        self.text = value

    def get(self):
        return self.text

    def set(self, value):
        self.text = value


def _case():
    page = Path("/synthetic/async-review/page-01.png")
    row = Entry()
    text = Value(row.word)
    observed, rendered, retried = [], [], []
    parent = SimpleNamespace(
        project=SimpleNamespace(root=page.parent, images=[page]),
        current_page=page, current_index=0, image=object(), settings=Settings(),
        canvas=SimpleNamespace(winfo_width=lambda: 800),
        _ordered_entries_reading_order=lambda: [row],
        _start_ui_worker=lambda key, worker, done, failed: observed.append(
            (key, worker, done, failed)
        ),
    )
    review = SimpleNamespace(
        parent=parent, vars=[text], row_entries=[row], active_index=0,
        _filter_rows_active=False, review_zoom_auto=False, review_zoom=1.0,
        _prefetch_closed=False, _review_render_worker_key="review-render",
        _bound_row_entries=lambda: [row],
        _review_image_area_width=lambda: 700,
        winfo_exists=lambda: True,
        render_rows=lambda **kw: rendered.append(kw),
        _request_render_rows=lambda **kw: retried.append(kw),
        editors=[],
    )
    deps = SimpleNamespace(
        ttk=SimpleNamespace(), tk=SimpleNamespace(TclError=RuntimeError),
        Image=SimpleNamespace(),
        _format_layout_percent=lambda value: str(value),
        _review_crop_context=lambda *args: None,
        _review_line_box=lambda *args, **kwargs: None,
        sync_review_entry_classification=lambda _review: None,
        normalize_page_rgb=lambda opened: opened,
        review_auto_fit_zoom=lambda *args: 1.0,
        replace=replace,
    )
    workflow._request_render_rows(review, deps, focus_index=0)
    assert len(observed) == 1
    done = observed[0][2]
    signature = ((id(row), row.x, row.y, row.word),)
    crop = object()
    return review, text, rendered, retried, lambda: done(
        (page.stem, signature, [crop], 1.0, False)
    )


def test_async_crop_with_changed_live_editor_text_is_rejected_and_requeued():
    _view, text, rendered, retried, deliver = _case()
    text.set("first was revised into a much longer human edit")
    deliver()
    assert rendered == [], "stale crop length was accepted despite changed Tk text"
    assert len(retried) == 1, "new editor revision needs its own crop worker"
    assert text.get() == "first was revised into a much longer human edit"


def test_async_crop_with_unchanged_live_editor_text_is_accepted():
    _view, _text, rendered, retried, deliver = _case()
    deliver()
    assert len(rendered) == 1
    assert retried == []
