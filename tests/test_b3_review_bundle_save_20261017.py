"""R3 paired-save failure injection with synthetic data, never private scans."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.formats import pdic_path, write_pdic
from picture_capture.models import Entry
from picture_capture.project_storage import simplified_review_path_for_image
from picture_capture.proofreading_transactions import snapshot_review, _recovery_path
from picture_capture.proofreading_save_safety import protect_review_pdic_commit
from picture_capture.proofreading_review_bundle import commit_review_bundle
from picture_capture import proofreading_review_bundle as bundle


def case(tmp_path):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic-only-not-private-pixels")
    entry = Entry("old", 10, 20)
    write_pdic(pdic_path(page), [entry], 100, ("synthetic", "@", "@"))
    app = SimpleNamespace(
        current_page=page, project=SimpleNamespace(root=tmp_path, images=[page]),
        entries=[entry], image=SimpleNamespace(width=100), current_index=0,
        settings=SimpleNamespace(proofreading_event_capture=False),
        _batch_active=False, _pending_manual_override_payload=None,
        ocr_review_candidates=[], entry_editor_bindings=[],
        _manual_selection_path=lambda: tmp_path / "manual_selection.json",
        _paddle_cache_path=lambda: tmp_path / "ocr.json",
        _sort_entries_reading_order=lambda: None,
        pages_tuple=lambda: ("synthetic", "@", "@"),
        _flush_pending_manual_override=lambda: None,
        _flush_proofreading_candidate_evidence=lambda: None,
        _flush_proofreading_add_evidence=lambda: None,
        _refresh_word_fill_check_from_line_count=lambda *args, **kwargs: None,
        _update_page_row=lambda *args: None,
        status_var=SimpleNamespace(set=lambda *args: None),
    )
    vars = [SimpleNamespace(get=lambda: "new")]
    records = {"10,20": {"x": 10, "y": 20, "source_word": "old", "text": "manual", "manual": True}}
    review = SimpleNamespace(
        parent=app, _rendered_page_stem=page.stem, vars=vars,
        _filter_rows_active=False, _bound_row_entries=lambda: app.entries,
        _simplified_page_cache={page.stem: records},
        _simplified_dirty_pages={page.stem},
        simplified_manual_flags=[True], simplified_actual_values=["manual"],
        _simplified_page_records=lambda stem: review._simplified_page_cache[stem],
    )
    def change():
        entry.word = "new"
        records["10,20"]["source_word"] = "new"
    review._commit_edits = change
    return page, entry, review


@pytest.mark.parametrize("role", ["pdic", "simplified"])
def test_failed_post_replace_rolls_back_exact_pair_and_ui(tmp_path, monkeypatch, role):
    page, entry, review = case(tmp_path)
    before = snapshot_review(review)
    assert before is not None
    original = pdic_path(page).read_bytes()
    original_publish = bundle._publish
    failed = [False]
    target = pdic_path(page) if role == "pdic" else simplified_review_path_for_image(page)
    def injected(path, data):
        original_publish(path, data)
        if path == target and not failed[0]:
            failed[0] = True
            raise OSError("injected failure after file replace")
    monkeypatch.setattr(bundle, "_publish", injected)
    with pytest.raises(OSError, match="injected failure"):
        with protect_review_pdic_commit(review):
            review._commit_edits()
            commit_review_bundle(review, before)
    assert pdic_path(page).read_bytes() == original
    assert not simplified_review_path_for_image(page).exists()
    assert entry.word == "old"
    assert review.vars[0].get() == "new"
    assert not _recovery_path(page).exists()


def test_review_bundle_success_commits_both_files(tmp_path):
    page, entry, review = case(tmp_path)
    source = snapshot_review(review)
    with protect_review_pdic_commit(review):
        review._commit_edits()
        commit_review_bundle(review, source)
    assert entry.word == "new"
    assert b"new#" in pdic_path(page).read_bytes()
    assert simplified_review_path_for_image(page).exists()
    assert not _recovery_path(page).exists()


def test_external_pdic_modification_blocks_and_preserves_human_bytes(tmp_path):
    page, entry, review = case(tmp_path)
    source = snapshot_review(review)
    pdic_path(page).write_bytes(b"external human data")
    with pytest.raises(RuntimeError, match="指纹"):
        with protect_review_pdic_commit(review):
            review._commit_edits()
            commit_review_bundle(review, source)
    assert pdic_path(page).read_bytes() == b"external human data"


def test_success_discards_stale_deferred_checkbox_snapshot(tmp_path):
    page, entry, review = case(tmp_path)
    review.parent._deferred_save_job = "job-1"
    review.parent._deferred_save_snapshot = ("stale",)
    review.parent._deferred_save_page = page
    cancelled = []
    review.parent.after_cancel = cancelled.append
    before = snapshot_review(review)
    with protect_review_pdic_commit(review):
        review._commit_edits()
        commit_review_bundle(review, before)
    assert cancelled == ["job-1"]
    assert review.parent._deferred_save_snapshot is None
    assert review.parent._deferred_save_page is None


def test_r2_opt_in_source_can_commit_but_undo_remains_denied(tmp_path):
    from picture_capture.ui.review_transaction_actions import capture_review_before
    page, entry, review = case(tmp_path)
    review.parent.settings.proofreading_event_capture = True
    assert snapshot_review(review) is None
    before = capture_review_before(review)
    assert before is not None
    with protect_review_pdic_commit(review):
        review._commit_edits()
        commit_review_bundle(review, before)
    assert entry.word == "new"
    assert snapshot_review(review) is None
