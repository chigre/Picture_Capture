"""Synthetic R3 explicit Save/Next ownership regression on pending pages.

Do not let an incomplete simplified editor redraw be acknowledged as an
unchanged page merely because a dirty event has not been published yet.
Uses synthetic Tk-like text buffers, never reads or saves real user files.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui import review_page_lifecycle as lifecycle


class Value:
    def __init__(self, text):
        self.text = text

    def get(self):
        return self.text


def _case(*, complete=False, with_simplified=True):
    root = Path("/synthetic/r3-pending-review")
    page = root / "page-01.png"
    row = SimpleNamespace(word="原词", x=10, y=20)
    messages = []
    navigation = []
    claims = []
    project = SimpleNamespace(root=root, images=[page, root / "page-02.png"])
    parent = SimpleNamespace(
        project=project,
        current_page=page, current_index=0,
        entries=[row],
        entry_editor_bindings=[],
        settings=SimpleNamespace(review_zoom_percent=100),
        status_var=SimpleNamespace(set=messages.append),
        _foreground_batch_state=lambda index: "pending",
        _claim_page_for_manual_edit=lambda: claims.append("claim") or True,
        change_page=lambda delta, **kw: navigation.append((delta, kw)),
    )
    review = SimpleNamespace(
        parent=parent,
        row_entries=[row],
        vars=[Value("原词")],
        _filter_rows_active=False,
        _rendered_page_stem=page.stem,
        _simplified_dirty_pages=set(),
        _r3_autosave_unconfirmed=False,
        _stored_review_zoom_percent=lambda: 100,
        _simplified_display_from_value=lambda word, actual, manual: actual or word,
        _take_prefetched_page=lambda index: {"index": index},
    )
    review._bound_row_entries = lambda: list(review.row_entries)
    if with_simplified:
        review.simplified_vars = [Value("自动简体" if complete else "未确认人工简体")]
        review.simplified_actual_values = ["自动简体"] if complete else []
        review.simplified_manual_flags = [False] if complete else []
    deps = SimpleNamespace(settings_path=lambda root: root / "settings.json")
    review.save = lambda **kw: lifecycle.save(review, deps, **kw)
    return review, deps, messages, navigation, claims


def test_pending_explicit_save_refuses_incomplete_simplified_row_owner():
    review, deps, messages, navigation, claims = _case(complete=False)
    assert lifecycle.save(review, deps, redraw_main=False) is False
    assert review.simplified_vars[0].get() == "未确认人工简体"
    assert review._r3_autosave_unconfirmed is True
    assert any("简体" in msg and ("绑定" in msg or "未确认" in msg) for msg in messages)
    assert navigation == []
    assert claims == []


def test_pending_next_page_refuses_navigation_while_simplified_owner_partial():
    review, deps, messages, navigation, claims = _case(complete=False)
    lifecycle.change_page(review, deps, 1)
    assert navigation == []
    assert review.simplified_vars[0].get() == "未确认人工简体"
    assert review._r3_autosave_unconfirmed is True
    assert claims == []
    assert any("简体" in msg for msg in messages)


def test_fully_bound_pending_unchanged_review_remains_clean_noop():
    review, deps, messages, navigation, claims = _case(complete=True)
    assert lifecycle.save(review, deps, redraw_main=False) is True
    assert review._r3_autosave_unconfirmed is False
    assert messages == [] and navigation == [] and claims == []


def test_legacy_original_only_review_without_simplified_column_still_noop():
    review, deps, messages, navigation, claims = _case(with_simplified=False)
    assert lifecycle.save(review, deps, redraw_main=False) is True
    assert messages == [] and claims == []
