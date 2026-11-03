"""R3 synthetic ReviewWindow autosave owner guard; no real dictionary data.

A partially replaced Tk row binding must not consume the main autosave tick
with neither a PDIC transaction nor a visible failure. Tests use the actual
lifecycle function and fake Tk-style values, not private project files.
"""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui import review_page_lifecycle as lifecycle
from picture_capture.proofreading import main_editor_sync


class Value:
    def __init__(self, text):
        self.text = text

    def get(self):
        return self.text


def review_case(monkeypatch, *, live, bound, values, rendered_stem="synthetic"):
    statuses, bridges, commits = [], [], []
    app = SimpleNamespace(
        project=object(), current_page=Path("synthetic.bmp"), current_index=0,
        entries=live, _foreground_batch_state=lambda _index: "idle",
        status_var=SimpleNamespace(set=statuses.append),
        settings=SimpleNamespace(review_zoom_percent=100),
    )
    review = SimpleNamespace(
        parent=app, vars=[Value(value) for value in values],
        row_entries=list(bound), _rendered_page_stem=rendered_stem,
        _filter_rows_active=False, _simplified_dirty_pages=set(),
        _bound_row_entries=lambda: list(bound),
        _commit_edits=lambda: commits.append("edit"),
        _review_evidence_before_save=lambda: None,
        _review_evidence_after_save=lambda _evidence: commits.append("evidence"),
        _stored_review_zoom_percent=lambda: 100,
    )
    monkeypatch.setattr(
        main_editor_sync, "bridge_main_canvas_text_into_review",
        lambda _review: bridges.append("bridge"),
    )
    monkeypatch.setattr(lifecycle, "_has_unreported_simplified_input", lambda _review: False)
    return review, statuses, bridges, commits


@pytest.mark.parametrize("broken", [
    "extra_widget", "missing_widget", "reloaded_same_word",
    "duplicate_entry", "missing_live_entry", "wrong_page",
    "empty_rows_with_live_entry",
])
def test_autosave_rejects_unowned_rendered_rows_before_edit_or_bridge(monkeypatch, broken):
    a, b = SimpleNamespace(word="old-a"), SimpleNamespace(word="old-b")
    live, bound, values, stem = [a], [a], ["old-a"], "synthetic"
    if broken == "extra_widget":
        values = ["old-a", "unsaved-human-word"]
    elif broken == "missing_widget":
        live, bound = [a, b], [a, b]
    elif broken == "reloaded_same_word":
        # Matching text/index is not proof that a row owns this Entry object.
        bound = [SimpleNamespace(word="old-a")]
    elif broken == "duplicate_entry":
        live, bound, values = [a, b], [a, a], ["old-a", "old-a"]
    elif broken == "missing_live_entry":
        live = [a, b]
    elif broken == "wrong_page":
        stem = "another-page"
    elif broken == "empty_rows_with_live_entry":
        bound, values = [], []
    review, statuses, bridges, commits = review_case(
        monkeypatch, live=live, bound=bound, values=values, rendered_stem=stem,
    )
    assert lifecycle.autosave_commit(review, None) is True
    assert statuses and ("未保存" in statuses[-1] or "未确认" in statuses[-1]), (
        broken, "a stale Tk binding silently consumed the main autosave"
    )
    assert bridges == []  # Do not copy any stale view text onto a live row.
    assert commits == []  # Neither commit nor optimistic save acknowledgement.
    assert [v.get() for v in review.vars] == values


def test_valid_unchanged_review_keeps_noop_behavior(monkeypatch):
    row = SimpleNamespace(word="old")
    review, statuses, bridges, commits = review_case(
        monkeypatch, live=[row], bound=[row], values=["old"],
    )
    assert lifecycle.autosave_commit(review, None) is True
    assert not statuses and not commits and bridges == ["bridge"]


def test_valid_dirty_review_still_commits_exact_owned_row(monkeypatch):
    from picture_capture.ui import review_transaction_actions
    from picture_capture.proofreading import save_safety, review_bundle

    row = SimpleNamespace(word="old")
    review, statuses, bridges, commits = review_case(
        monkeypatch, live=[row], bound=[row], values=["new"],
    )
    monkeypatch.setattr(review_transaction_actions, "capture_review_before", lambda _r: "before")
    monkeypatch.setattr(review_transaction_actions, "record_review_after", lambda _r, _before: commits.append("after"))
    monkeypatch.setattr(save_safety, "protect_review_pdic_commit", lambda _r: nullcontext())
    monkeypatch.setattr(review_bundle, "commit_review_bundle", lambda _r, _before: commits.append("bundle"))
    assert lifecycle.autosave_commit(review, None) is True
    assert not statuses and bridges == ["bridge"]
    assert commits == ["edit", "bundle", "evidence", "after"]


@pytest.mark.parametrize("pending", [False, True])
def test_existing_filtered_mode_keeps_main_autosave_handoff(monkeypatch, pending):
    row = SimpleNamespace(word="old")
    review, statuses, bridges, commits = review_case(
        monkeypatch, live=[row], bound=[row], values=["old"],
    )
    flushed = []
    review._filter_rows_active = True
    review._filter_pending_changes = {0: {(1, 2): {}}} if pending else {}
    review._filter_save_running = False
    review._flush_focused_changes_now = lambda: flushed.append(True)
    assert lifecycle.autosave_commit(review, None) is pending
    assert flushed == [True] and not bridges and not commits
    assert bool(statuses) is pending
