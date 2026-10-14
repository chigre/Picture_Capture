"""R3: conservative same-window undo/redo of committed PDIC-only text edits."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.proofreading_transactions import (
    ReviewSessionHistory, snapshot_review,
)
from picture_capture import proofreading_transactions as module


class Var:
    def __init__(self, text):
        self.text = text

    def get(self):
        return self.text

    def set(self, value):
        self.text = value


def _case(tmp_path):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic-image-not-actual-private-scan")
    rows = [Entry("one", 10, 20), Entry("two", 30, 40)]
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    app = SimpleNamespace(
        current_page=page, entries=rows, project=SimpleNamespace(root=tmp_path),
        settings=SimpleNamespace(proofreading_event_capture=False),
        _batch_active=False, _pending_manual_override_payload=None,
        ocr_review_candidates=[],
        _manual_selection_path=lambda: tmp_path / "manual_selection.json",
        _paddle_cache_path=lambda: tmp_path / "cache.json",
    )
    review = SimpleNamespace(
        parent=app, _filter_rows_active=False, _rendered_page_stem=page.stem,
        vars=[Var(row.word) for row in rows],
        _bound_row_entries=lambda: app.entries,
    )
    return page, rows, review


def _save_words(page, rows, review, *words):
    before = snapshot_review(review)
    assert before is not None
    for entry, word in zip(rows, words):
        entry.word = word
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    for v, entry in zip(review.vars, rows):
        v.set(entry.word)
    after = snapshot_review(review)
    assert after is not None
    return before, after


def test_saved_text_undo_redo_roundtrip_preserves_exact_pdic_bytes(tmp_path):
    page, rows, review = _case(tmp_path)
    original = pdic_path(page).read_bytes()
    history = ReviewSessionHistory()
    old, new = _save_words(page, rows, review, "ONE", "two")
    assert history.record(old, new)
    changed = pdic_path(page).read_bytes()
    assert history.undo(review)
    assert pdic_path(page).read_bytes() == original
    assert [r.word for r in rows] == ["one", "two"]
    assert [v.get() for v in review.vars] == ["one", "two"]
    assert history.redo(review)
    assert pdic_path(page).read_bytes() == changed
    assert [r.word for r in rows] == ["ONE", "two"]


def test_two_saved_edits_replay_without_row_index_matching(tmp_path):
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    assert history.record(*_save_words(page, rows, review, "ONE", "TWO"))
    rows.reverse()
    review.vars.reverse()
    assert history.undo(review)
    assert {r.word for r in rows} == {"ONE", "two"}
    assert history.undo(review)
    assert {r.word for r in rows} == {"one", "two"}
    assert history.redo(review) and history.redo(review)
    assert {r.word for r in rows} == {"ONE", "TWO"}


def test_new_commit_after_undo_drops_redo(tmp_path):
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    assert history.undo(review)
    assert history.record(*_save_words(page, rows, review, "fresh", "two"))
    assert not history.redo(review)
    assert [r.word for r in rows] == ["fresh", "two"]


def test_dirty_editor_refuses_undo_without_changing_disk(tmp_path):
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    committed = pdic_path(page).read_bytes()
    review.vars[0].set("typed-but-not-saved")
    assert not history.undo(review)
    assert pdic_path(page).read_bytes() == committed
    assert rows[0].word == "ONE"


def test_external_pdic_drift_invalidates_history(tmp_path):
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    pdic_path(page).write_text("external#10#20#1#2#synthetic#@#@\n", encoding="utf-8")
    saved = pdic_path(page).read_bytes()
    assert not history.undo(review)
    assert pdic_path(page).read_bytes() == saved
    assert not history.undo_stack and not history.redo_stack


@pytest.mark.parametrize("sidecar", ["manual_selection.json", "cache.json"])
def test_ocr_or_override_drift_refuses_snapshot_and_undo(tmp_path, sidecar):
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    (tmp_path / sidecar).write_text('{"changed": true}', encoding="utf-8")
    assert not history.undo(review)
    assert rows[0].word == "ONE"


def test_simplified_sidecar_change_is_reversed_with_saved_pdic(tmp_path):
    from picture_capture.project_storage import simplified_review_path_for_image
    page, rows, review = _case(tmp_path)
    before = snapshot_review(review)
    assert before
    rows[0].word = "ONE"
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    simplified = simplified_review_path_for_image(page)
    simplified.parent.mkdir(parents=True, exist_ok=True)
    simplified.write_text('{"entries":[]}', encoding="utf-8")
    review.vars[0].set("ONE")  # Saved ReviewWindow editor, not an unsaved edit.
    after = snapshot_review(review)
    history = ReviewSessionHistory()
    assert after is not None
    assert history.record(before, after)
    assert history.undo(review)
    assert [e.word for e in read_pdic(pdic_path(page))] == ["one", "two"]
    assert not simplified.exists()
    assert history.redo(review)
    assert [e.word for e in read_pdic(pdic_path(page))] == ["ONE", "two"]
    assert simplified.is_file()


def test_reordered_entries_still_refer_to_same_objects_not_text_similarity(tmp_path):
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    # A page swap must never restore a different page's PDIC.
    other = tmp_path / "other.png"
    other.write_bytes(b"other")
    review.parent.current_page = other
    assert not history.undo(review)
    assert rows[0].word == "ONE"


def test_atomic_pdic_failure_never_changes_in_memory(tmp_path, monkeypatch):
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    old = pdic_path(page).read_bytes()

    def fail(*args):
        raise OSError("simulated full disk")

    monkeypatch.setattr(module, "_atomic_bytes", fail)
    assert not history.undo(review)
    assert pdic_path(page).read_bytes() == old
    assert [e.word for e in rows] == ["ONE", "two"]
    assert len(history.undo_stack) == 1


def test_opted_in_r2_evidence_and_background_batch_do_not_undo(tmp_path):
    page, rows, review = _case(tmp_path)
    review.parent.settings.proofreading_event_capture = True
    assert snapshot_review(review) is None
    review.parent.settings.proofreading_event_capture = False
    review.parent._batch_active = True
    assert snapshot_review(review) is None


def test_unrelated_row_deletion_is_not_a_pure_text_transaction(tmp_path):
    page, rows, review = _case(tmp_path)
    before = snapshot_review(review)
    rows.pop()
    review.vars.pop()
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    after = snapshot_review(review)
    history = ReviewSessionHistory()
    assert not history.record(before, after)
    assert not history.undo_stack


def test_ui_wiring_exposes_explicit_review_save_undo_redo():
    from picture_capture import app as gui
    source = Path(gui.__file__).read_text("utf-8")
    assert 'self._review_flat_button(row1, "撤销保存"' in source
    assert 'self._review_flat_button(row1, "重做保存"' in source
    assert "record_review_after(self, transaction_before)" in source
    assert "invalidate_review_history(self)" in source



def test_multi_file_interruption_rolls_back_without_changing_ui(tmp_path, monkeypatch):
    from picture_capture.project_storage import simplified_review_path_for_image
    page, rows, review = _case(tmp_path)
    simplified = simplified_review_path_for_image(page)
    simplified.parent.mkdir(parents=True, exist_ok=True)
    simplified.write_text('{"entries":[]}', encoding="utf-8")
    before = snapshot_review(review)
    assert before
    rows[0].word = "ONE"
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    simplified.write_text('{"entries":[{"x":10,"y":20,"source_word":"ONE","text":"AUTO","manual":false}]}', encoding="utf-8")
    review.vars[0].set("ONE")  # Simulate post-commit ReviewWindow text.
    after = snapshot_review(review)
    assert after
    history = ReviewSessionHistory()
    assert history.record(before, after)
    original_pdic, original_simplified = pdic_path(page).read_bytes(), simplified.read_bytes()
    publish = module._publish

    def fail_simplified(path, data):
        if path == simplified and data != original_simplified:
            raise OSError("simulated disk full during second file")
        return publish(path, data)

    monkeypatch.setattr(module, "_publish", fail_simplified)
    assert not history.undo(review)
    assert pdic_path(page).read_bytes() == original_pdic
    assert simplified.read_bytes() == original_simplified
    assert rows[0].word == "ONE"
    assert not module._recovery_path(page).exists()


def test_crash_recovery_rolls_back_partial_two_file_update(tmp_path):
    from picture_capture.project_storage import simplified_review_path_for_image
    page, rows, review = _case(tmp_path)
    simplified = simplified_review_path_for_image(page)
    simplified.parent.mkdir(parents=True, exist_ok=True)
    simplified.write_bytes(b"original companion")
    orig = pdic_path(page).read_bytes()
    target = orig.replace(b"one", b"ONE")
    staging = [
        ("pdic", orig, target),
        ("simplified", b"original companion", b"restored companion"),
    ]
    marker = module._stage_recovery(page, staging)
    assert marker.is_file()
    module._publish(pdic_path(page), target)  # Crash between first and second.
    assert module.recover_pending_for_page(page)
    assert pdic_path(page).read_bytes() == orig
    assert simplified.read_bytes() == b"original companion"
    assert not marker.exists()


def test_complete_multifile_recovery_keeps_target_and_clears_marker(tmp_path):
    from picture_capture.project_storage import simplified_review_path_for_image
    page, rows, review = _case(tmp_path)
    simplified = simplified_review_path_for_image(page)
    original = pdic_path(page).read_bytes()
    new = original.replace(b"one", b"ONE")
    marker = module._stage_recovery(page, [
        ("pdic", original, new),
        ("simplified", None, b"new-simplified"),
    ])
    module._publish(pdic_path(page), new)
    module._publish(simplified, b"new-simplified")
    assert module.recover_pending_for_page(page)
    assert pdic_path(page).read_bytes() == new
    assert simplified.read_bytes() == b"new-simplified"
    assert not marker.exists()


def test_external_file_change_blocks_recovery_and_preserves_user_bytes(tmp_path):
    page, _, _ = _case(tmp_path)
    original = pdic_path(page).read_bytes()
    module._stage_recovery(page, [("pdic", original, original.replace(b"one", b"ONE"))])
    pdic_path(page).write_bytes(b"external human edit")
    assert not module.recover_pending_for_page(page)
    assert pdic_path(page).read_bytes() == b"external human edit"
    assert module._recovery_path(page).exists()


def test_dirty_simplified_widget_blocks_even_when_pdic_clean(tmp_path):
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    review._simplified_dirty_pages = {page.stem}
    assert not history.undo(review)
    assert rows[0].word == "ONE"


def test_ocr_candidate_owned_word_is_not_undoable_by_plain_text_transaction(tmp_path):
    page, rows, review = _case(tmp_path)
    rows[0].candidate_id = "candidate-0"
    before = snapshot_review(review)
    assert before is not None
    rows[0].word = "ONE"
    review.vars[0].set("ONE")
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    after = snapshot_review(review)
    assert after is not None
    history = ReviewSessionHistory()
    assert not history.record(before, after)
    assert not history.undo_stack


def test_metadata_only_pdic_change_is_not_a_text_undo(tmp_path):
    page, rows, review = _case(tmp_path)
    before = snapshot_review(review)
    assert before
    text = pdic_path(page).read_text(encoding="utf-8")
    pdic_path(page).write_text(text.replace("#synthetic#@#@", "#synthetic#previous#@"), encoding="utf-8")
    after = snapshot_review(review)
    assert after is not None
    history = ReviewSessionHistory()
    assert not history.record(before, after)


def test_external_edit_between_preflight_and_publish_refuses_undo(tmp_path, monkeypatch):
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    original = pdic_path(page).read_bytes()
    check = module._publish_restored_snapshot

    def concurrent_write(before, target):
        pdic_path(page).write_bytes(b"concurrently altered PDIC")
        return check(before, target)

    monkeypatch.setattr(module, "_publish_restored_snapshot", concurrent_write)
    assert not history.undo(review)
    assert pdic_path(page).read_bytes() == b"concurrently altered PDIC"
    assert rows[0].word == "ONE"



def test_single_row_deletion_undo_redo_restores_original_entry_object(tmp_path):
    page, rows, review = _case(tmp_path)
    original_ids = {id(e) for e in rows}
    before = snapshot_review(review)
    assert before
    removed = rows.pop(0)
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    # GUI row widgets are intentionally stale until async re-render.
    after = snapshot_review(review, allow_unbound=True)
    assert after
    history = ReviewSessionHistory()
    assert history.record(before, after)
    # GUI async repaint now catches up with persisted parent.entries.
    review.vars = [Var(rows[0].word)]
    assert history.undo(review)
    assert {id(e) for e in review.parent.entries} == original_ids
    assert any(e is removed for e in review.parent.entries)
    assert len(read_pdic(pdic_path(page))) == 2
    review.vars = [Var(e.word) for e in review.parent.entries]
    assert history.redo(review)
    assert len(review.parent.entries) == 1
    assert removed not in review.parent.entries
    assert len(read_pdic(pdic_path(page))) == 1


def test_delete_last_row_can_undo_from_empty_saved_pdic(tmp_path):
    page, rows, review = _case(tmp_path)
    rows.pop()
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    before = snapshot_review(review)
    assert before
    deleted = rows.pop()
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    after = snapshot_review(review, allow_unbound=True)
    assert after and not after.entries
    history = ReviewSessionHistory()
    assert history.record(before, after)
    review.vars = []
    assert history.undo(review)
    assert review.parent.entries == [deleted]
    assert len(read_pdic(pdic_path(page))) == 1


def test_candidate_linked_deletion_refuses_deselection_rollback(tmp_path):
    page, rows, review = _case(tmp_path)
    rows[0].candidate_id = "candidate"
    before = snapshot_review(review)
    assert before
    rows.pop(0)
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    after = snapshot_review(review, allow_unbound=True)
    assert after
    history = ReviewSessionHistory()
    assert not history.record(before, after)
    assert not history.undo_stack


def test_two_row_delete_or_geometry_move_is_not_undoable(tmp_path):
    page, rows, review = _case(tmp_path)
    before = snapshot_review(review)
    assert before
    rows.clear()
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    after = snapshot_review(review, allow_unbound=True)
    assert after
    assert not ReviewSessionHistory().record(before, after)


def test_unrendered_row_bindings_do_not_destroy_history_before_repaint(tmp_path):
    page, rows, review = _case(tmp_path)
    before = snapshot_review(review)
    assert before
    rows.pop()
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    after = snapshot_review(review, allow_unbound=True)
    history = ReviewSessionHistory()
    assert after and history.record(before, after)
    assert not history.undo(review)  # widgets still bound to deleted row
    assert len(history.undo_stack) == 1
    review.vars = [Var(rows[0].word)]
    assert history.undo(review)
