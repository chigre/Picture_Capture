"""All main-window navigation paths must update the live proofreading window."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui.review_page_sync import (
    save_review_before_page_change, refresh_review_after_page_change,
)
from picture_capture.ui.controllers.page import PageController


class ReviewStub:
    def __init__(self):
        self._rendered_page_stem = "001"
        self._filter_rows_active = False
        self.review_zoom_auto = False
        self.review_mode_var = SimpleNamespace(set=lambda value: self.events.append(("mode", value)))
        self.events = []
        self.active_index = 7
        self._active_crop_fixed_size = (200, 80)
        self._active_crop_page_stem = "001"
        self._review_display_crops = [object()]
        self.calls = []

    def winfo_exists(self):
        return True

    def save(self, *, redraw_main):
        self.calls.append(("save", redraw_main))

    def _clear_review_workspace(self, msg):
        self.calls.append(("clear", msg))

    def _sync_review_height_vars(self):
        self.calls.append(("heights",))

    def _set_filter_navigation(self, flag):
        self.calls.append(("navigation", flag))

    def _review_prefetch_key(self):
        return ("fresh",)

    def render_rows(self, *, preloaded_crops):
        self.calls.append(("prefetched", preloaded_crops))

    def _request_render_rows(self, *, focus_index, reset_scroll):
        self.calls.append(("render", focus_index, reset_scroll))

    def _reset_rows_scroll_top(self):
        self.calls.append(("scroll",))

    def _update_title(self):
        self.calls.append(("title",))

    def _flush_focused_changes_now(self):
        self.calls.append(("filter-flush",))

    def _change_review_mode(self):
        self.calls.append(("single-mode",))


def make_app():
    return SimpleNamespace(
        review_window=ReviewStub(),
        current_page=Path("001.png"),
        current_index=0,
        entries=[object()],
    )


def test_save_old_review_edits_before_parent_commits_new_index():
    app = make_app()
    assert save_review_before_page_change(app, 1)
    assert app.review_window.calls == [("save", False)]
    assert not save_review_before_page_change(app, 1, already_saved=True)
    app.review_window._rendered_page_stem = "unrelated"
    assert not save_review_before_page_change(app, 1)
    assert app.review_window.calls == [("save", False)]


def test_commit_new_page_refreshes_focus_rows_scroll_title_and_parameter_values():
    app = make_app()
    app.current_page = Path("002.png")
    refresh_review_after_page_change(app)
    review = app.review_window
    assert review.active_index == 0
    assert review._active_crop_fixed_size is None
    assert review._review_display_crops == []
    assert ("render", 0, True) in review.calls
    assert review.calls.index(("clear", "正在加载当前页词条切片…")) < review.calls.index(("render", 0, True))
    assert ("heights",) in review.calls
    assert ("scroll",) in review.calls
    assert review.calls[-1] == ("title",)


def test_prefetched_review_crop_is_used_only_with_matching_signature():
    app = make_app()
    refresh_review_after_page_change(app, {"review_key": ("fresh",), "review_crops": ["crop"]})
    assert ("prefetched", ["crop"]) in app.review_window.calls
    assert not any(e[0] == "render" for e in app.review_window.calls)

    app = make_app()
    refresh_review_after_page_change(app, {"review_key": ("old",), "review_crops": ["old"]})
    assert ("render", 0, True) in app.review_window.calls
    assert not any(e[0] == "prefetched" for e in app.review_window.calls)


def test_filtered_review_flushes_before_switch_to_page_based_view():
    app = make_app()
    review = app.review_window
    review._filter_rows_active = True
    assert not save_review_before_page_change(app, 1)
    refresh_review_after_page_change(app)
    assert review.calls.index(("filter-flush",)) < review.calls.index(
        ("clear", "正在加载当前页词条切片…")
    )
    assert ("mode", "single") in review.events
    assert ("single-mode",) in review.calls


def test_destroyed_review_is_not_refreshed_or_saved():
    app = make_app()
    app.review_window.winfo_exists = lambda: False
    assert not save_review_before_page_change(app, 1)
    assert app.review_window is None
    app.review_window = ReviewStub()
    app.review_window.winfo_exists = lambda: False
    refresh_review_after_page_change(app)
    assert app.review_window is None


def test_all_page_navigation_enters_same_shared_load_page_commit_path():
    import picture_capture.app as module

    path = Path(module.__file__).read_text(encoding="utf-8")
    load_page = path.split("    def load_page(", 1)[1].split("    def change_page(", 1)[0]
    assert "save_review_before_page_change(self, index" in load_page
    assert "self._save_current_page_by_mode(sync_editors=not review_saved)" in load_page
    assert "refresh_review_after_page_change(self, preloaded if use_preloaded else None)" in load_page
    review_change = path.split("    def change_page(self, delta: int) -> None:", 1)[1].split(
        "\n\n\nclass PictureCaptureApp", 1
    )[0]
    assert review_change.count("_request_render_rows(") == 0
    assert "current_already_saved=True" in review_change
    page_module = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "ui" / "controllers" / "page.py"
    page_text = page_module.read_text(encoding="utf-8")
    assert "app.load_page(" in page_text


def test_double_page_selection_only_commits_final_new_page():
    # Async page controller passes the chosen page to load_page after decoding.
    selected = []
    app = SimpleNamespace(
        _batch_active=False, _pending_page_index=None, current_index=0,
        project=SimpleNamespace(images=[Path("001.png"), Path("002.png")]),
        image=object(),
        _invalidate_ui_worker=lambda *_: None,
        _set_page_list_selection=lambda *a, **kw: None,
        status_var=SimpleNamespace(set=lambda *_: None),
        load_page=lambda index, **kw: selected.append(index),
    )
    controller = PageController(app)
    assert controller.change_page(1, async_allowed=False)
    assert selected == [1]
