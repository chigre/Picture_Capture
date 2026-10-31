"""R3: conservative same-window undo/redo of committed PDIC-only text edits."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.io.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.proofreading.transactions import (
    ReviewSessionHistory, snapshot_review,
)
from picture_capture.proofreading import transactions as module


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
    # Until actual ReviewWindow redraw, the old widgets still own the
    # previous reversed row bindings. Do not make one widget silently
    # take another Entry's value merely to let a second Undo proceed.
    assert [var.get() for var in review.vars] == ["two", "ONE"]
    assert history.undo(review) is False
    assert len(history.undo_stack) == 1
    assert len(history.redo_stack) == 1
    # The ordinary UI coordinator requests a full row repaint after every
    # committed replay. Model that explicit rebind, not an implicit index
    # reassignment of the old StringVars.
    review.vars = [Var(row.word) for row in rows]
    assert history.undo(review)
    assert {r.word for r in rows} == {"one", "two"}
    review.vars = [Var(row.word) for row in rows]
    assert history.redo(review)
    review.vars = [Var(row.word) for row in rows]
    assert history.redo(review)
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
    from picture_capture.persistence.project_storage import simplified_review_path_for_image
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


def test_single_unlinked_deleted_row_is_undoable(tmp_path):
    page, rows, review = _case(tmp_path)
    before = snapshot_review(review)
    rows.pop()
    review.vars.pop()
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    after = snapshot_review(review)
    history = ReviewSessionHistory()
    assert history.record(before, after)
    assert history.undo(review)
    assert len(read_pdic(pdic_path(page))) == 2


def test_ui_wiring_exposes_explicit_review_save_undo_redo():
    from picture_capture import app as gui
    source = Path(gui.__file__).read_text("utf-8")
    review_source = (Path(gui.__file__).parent / "ui/review_workspace_workflow.py").read_text("utf-8")
    assert 'self._review_flat_button(row1, "撤销保存"' in review_source
    assert 'self._review_flat_button(row1, "重做保存"' in review_source
    page_source = (Path(gui.__file__).parent / "ui/review_page_lifecycle.py").read_text("utf-8")
    entry_source = (Path(gui.__file__).parent / "ui/review_entry_actions.py").read_text("utf-8")
    assert "record_review_after(self, transaction_before)" in page_source
    assert "record_review_after(self, transaction_before, allow_unbound=True)" in entry_source



def test_multi_file_interruption_rolls_back_without_changing_ui(tmp_path, monkeypatch):
    from picture_capture.persistence.project_storage import simplified_review_path_for_image
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
    from picture_capture.persistence.project_storage import simplified_review_path_for_image
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
    from picture_capture.persistence.project_storage import simplified_review_path_for_image
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
    stale_widgets = list(rows)  # Real Tk rows are not refreshed synchronously.
    review._bound_row_entries = lambda: stale_widgets
    before = snapshot_review(review)
    assert before
    rows.pop()
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    after = snapshot_review(review, allow_unbound=True)
    history = ReviewSessionHistory()
    assert after and history.record(before, after)
    assert not history.undo(review)  # widgets still bound to deleted row
    assert len(history.undo_stack) == 1
    review._bound_row_entries = lambda: rows
    review.vars = [Var(rows[0].word)]
    assert history.undo(review)


def test_unowned_new_entry_during_save_cannot_create_deletion_undo(tmp_path):
    page, rows, review = _case(tmp_path)
    before = snapshot_review(review)
    assert before
    rows.append(Entry("unowned-extra", 61, 82))
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    after = snapshot_review(review, allow_unbound=True)
    assert after
    history = ReviewSessionHistory()
    assert not history.record(before, after)
    assert not history.undo_stack


def test_candidate_ownership_is_frozen_at_snapshot_time(tmp_path):
    """An Entry cannot acquire or shed an OCR owner after a saved snapshot."""
    page, rows, review = _case(tmp_path)
    before = snapshot_review(review)
    assert before is not None
    rows[0].candidate_id = "new-ocr-owner"
    rows[1].word = "TWO"
    review.vars[1].set("TWO")
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    after = snapshot_review(review)
    assert after is not None
    history = ReviewSessionHistory()
    assert not history.record(before, after)
    assert not history.undo_stack


def test_candidate_ownership_drift_after_record_refuses_undo(tmp_path):
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    unchanged = pdic_path(page).read_bytes()
    rows[0].candidate_id = "linked-after-save"
    assert not history.undo(review)
    assert pdic_path(page).read_bytes() == unchanged
    assert rows[0].word == "ONE"
    assert not history.undo_stack


@pytest.mark.parametrize("sidecar", ["manual_selection.json", "cache.json"])
def test_external_sidecar_change_at_last_preflight_refuses_undo(tmp_path, monkeypatch, sidecar):
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    committed = pdic_path(page).read_bytes()
    original = module._publish_restored_snapshot

    def concurrent_write(expected, target):
        (tmp_path / sidecar).write_bytes(b"external-human-or-ocr-change")
        return original(expected, target)

    monkeypatch.setattr(module, "_publish_restored_snapshot", concurrent_write)
    assert not history.undo(review)
    assert pdic_path(page).read_bytes() == committed
    assert rows[0].word == "ONE"
    assert (tmp_path / sidecar).read_bytes() == b"external-human-or-ocr-change"


@pytest.mark.parametrize("source", ["section", "profile"])
def test_section_or_profile_drift_invalidates_saved_history(tmp_path, source):
    from picture_capture.persistence.project_storage import (
        page_sections_path_for_image, profile_path,
    )
    page, rows, review = _case(tmp_path)
    hist = ReviewSessionHistory()
    assert hist.record(*_save_words(page, rows, review, "ONE", "two"))
    committed = pdic_path(page).read_bytes()
    external = (
        page_sections_path_for_image(page)
        if source == "section" else profile_path(tmp_path)
    )
    external.parent.mkdir(parents=True, exist_ok=True)
    external.write_bytes(b'{"external": "human edit"}')
    assert not hist.undo(review)
    assert pdic_path(page).read_bytes() == committed
    assert rows[0].word == "ONE"
    assert not hist.undo_stack and not hist.redo_stack


@pytest.mark.parametrize("source", ["section", "profile"])
def test_section_or_profile_last_moment_source_race_refuses_undo(tmp_path, monkeypatch, source):
    from picture_capture.persistence.project_storage import (
        page_sections_path_for_image, profile_path,
    )
    page, rows, review = _case(tmp_path)
    hist = ReviewSessionHistory()
    assert hist.record(*_save_words(page, rows, review, "ONE", "two"))
    committed = pdic_path(page).read_bytes()
    external = (
        page_sections_path_for_image(page)
        if source == "section" else profile_path(tmp_path)
    )
    original = module._publish_restored_snapshot

    def concurrent_human_edit(expected, target):
        external.parent.mkdir(parents=True, exist_ok=True)
        external.write_bytes(b'{"modified_while_undo_pending": true}')
        return original(expected, target)

    monkeypatch.setattr(module, "_publish_restored_snapshot", concurrent_human_edit)
    assert not hist.undo(review)
    assert pdic_path(page).read_bytes() == committed
    assert rows[0].word == "ONE"
    assert external.read_bytes() == b'{"modified_while_undo_pending": true}'


def test_unrelated_ocr_owner_change_cannot_piggyback_plain_saved_text(tmp_path):
    page, rows, review = _case(tmp_path)
    hist = ReviewSessionHistory()
    before = snapshot_review(review)
    assert before is not None
    rows[0].candidate_id = "new"
    rows[1].word = "TWO"
    review.vars[1].set("TWO")
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    after = snapshot_review(review)
    assert after is not None
    assert not hist.record(before, after)
    assert not hist.undo_stack


def test_source_chain_change_between_commits_clears_preexisting_undo(tmp_path):
    page, rows, review = _case(tmp_path)
    hist = ReviewSessionHistory()
    assert hist.record(*_save_words(page, rows, review, "ONE", "two"))
    assert len(hist.undo_stack) == 1
    cache = tmp_path / "cache.json"
    cache.write_bytes(b'{"ocr": "external new run"}')
    before, after = _save_words(page, rows, review, "ONE", "TWO")
    assert hist.record(before, after)
    # The new save is valid itself, but the old chain must not be replayable
    # after an intervening OCR cache change that could change word ownership.
    assert len(hist.undo_stack) == 1
    assert hist.undo_stack[0].before.pdic_bytes == before.pdic_bytes


def _manual_owned_case(tmp_path):
    """Synthetic project-local candidate files; no private scans."""
    page, rows, review = _case(tmp_path)
    directory = tmp_path / "QT" / "PaddleOCR"
    directory.mkdir(parents=True, exist_ok=True)
    override = directory / f"{page.stem}_manual_selection.json"
    cache = directory / f"{page.stem}.json"
    review.parent._manual_selection_path = lambda: override
    review.parent._paddle_cache_path = lambda: cache
    return page, rows, review, override, cache


def test_three_file_owned_bundle_atomic_commit_without_editing_live_rows(tmp_path):
    from picture_capture.persistence.project_storage import simplified_review_path_for_image
    page, rows, review, override, _cache = _manual_owned_case(tmp_path)
    simplified = simplified_review_path_for_image(page)
    simplified.parent.mkdir(parents=True, exist_ok=True)
    simplified.write_bytes(b'{"entries":[]}')
    expected = snapshot_review(review)
    assert expected is not None
    target_pdic = expected.pdic_bytes.replace(b"one", b"ONE")
    manual_data = b'{"version":1,"overrides":{"candidate":{"selected":false}}}'
    new_simplified = b'{"entries":[{"x":10,"y":20,"text":"ONE"}]}'
    assert module.publish_owned_review_bundle(
        expected, pdic_bytes=target_pdic, manual_bytes=manual_data,
        simplified_bytes=new_simplified,
    )
    assert pdic_path(page).read_bytes() == target_pdic
    assert override.read_bytes() == manual_data
    assert simplified.read_bytes() == new_simplified
    assert [row.word for row in rows] == ["one", "two"]
    assert not module._recovery_path(page).exists()


@pytest.mark.parametrize("failed_role", ["manual", "simplified"])
def test_three_file_owned_bundle_write_failure_recovers_without_ui_mutation(
    tmp_path, monkeypatch, failed_role,
):
    from picture_capture.persistence.project_storage import simplified_review_path_for_image
    page, rows, review, override, _cache = _manual_owned_case(tmp_path)
    simplified = simplified_review_path_for_image(page)
    simplified.parent.mkdir(parents=True, exist_ok=True)
    simplified.write_bytes(b"original simplified")
    before = snapshot_review(review)
    assert before
    target_pdic = before.pdic_bytes.replace(b"one", b"ONE")
    new_manual = b'{"overrides":{"candidate":{"selected":false}}}'
    new_simplified = b"new simplified"
    chosen = override if failed_role == "manual" else simplified
    original_publish = module._publish
    failed = False

    def injected_failure(path, contents):
        nonlocal failed
        if path == chosen and not failed:
            failed = True
            raise OSError("simulated disk write failed")
        return original_publish(path, contents)

    monkeypatch.setattr(module, "_publish", injected_failure)
    with pytest.raises(OSError):
        module.publish_owned_review_bundle(
            before, pdic_bytes=target_pdic, manual_bytes=new_manual,
            simplified_bytes=new_simplified,
        )
    assert pdic_path(page).read_bytes() == before.pdic_bytes
    assert not override.exists()
    assert simplified.read_bytes() == b"original simplified"
    assert [row.word for row in rows] == ["one", "two"]
    assert not module._recovery_path(page).exists()


def test_three_file_crash_mid_commit_reopens_with_trusted_manual_path(tmp_path):
    from picture_capture.persistence.project_storage import simplified_review_path_for_image
    page, _, _, override, _cache = _manual_owned_case(tmp_path)
    simplified = simplified_review_path_for_image(page)
    original_pdic = pdic_path(page).read_bytes()
    changes = [
        ("pdic", original_pdic, original_pdic.replace(b"one", b"ONE")),
        ("manual", None, b'{"selected":false}'),
        ("simplified", None, b'{"entries":[]}'),
    ]
    marker = module._stage_recovery(page, changes, manual_path=override)
    module._publish(pdic_path(page), changes[0][2])
    module._publish(override, changes[1][2])
    assert marker.is_file()
    with pytest.raises(ValueError):
        module.recover_pending_for_page(page)
    assert marker.is_file()
    with pytest.raises(ValueError):
        module.recover_pending_for_page(
            page, manual_path=override.with_name("different_manual_selection.json"),
        )
    assert module.recover_pending_for_page(page, manual_path=override)
    assert pdic_path(page).read_bytes() == original_pdic
    assert not override.exists()
    assert not simplified.exists()
    assert not marker.exists()


def test_three_file_completed_commit_recovery_keeps_all_targets(tmp_path):
    from picture_capture.persistence.project_storage import simplified_review_path_for_image
    page, _, _, override, _cache = _manual_owned_case(tmp_path)
    simplified = simplified_review_path_for_image(page)
    old = pdic_path(page).read_bytes()
    stages = [
        ("pdic", old, old.replace(b"two", b"TWO")),
        ("manual", None, b'{"selected":false}'),
        ("simplified", None, b'{"entries":[]}'),
    ]
    marker = module._stage_recovery(page, stages, manual_path=override)
    for role, _, contents in stages:
        target = {"pdic": pdic_path(page), "manual": override, "simplified": simplified}[role]
        module._publish(target, contents)
    assert module.recover_pending_for_page(page, manual_path=override)
    assert pdic_path(page).read_bytes() == stages[0][2]
    assert override.read_bytes() == stages[1][2]
    assert simplified.read_bytes() == stages[2][2]
    assert not marker.exists()


def test_owned_bundle_rejects_external_manual_or_ocr_drift_before_write(tmp_path):
    page, rows, review, override, cache = _manual_owned_case(tmp_path)
    before = snapshot_review(review)
    assert before
    override.write_bytes(b"external manual choice")
    assert not module.publish_owned_review_bundle(
        before, pdic_bytes=before.pdic_bytes.replace(b"one", b"ONE"),
        manual_bytes=b"new", simplified_bytes=None,
    )
    assert pdic_path(page).read_bytes() == before.pdic_bytes
    assert not module._recovery_path(page).exists()
    override.unlink()
    cache.write_bytes(b"new OCR cache")
    assert not module.publish_owned_review_bundle(
        before, pdic_bytes=before.pdic_bytes.replace(b"one", b"ONE"),
        manual_bytes=b"new", simplified_bytes=None,
    )
    assert pdic_path(page).read_bytes() == before.pdic_bytes
    assert [row.word for row in rows] == ["one", "two"]


def test_owned_bundle_rechecks_sources_after_writing_intent_marker(tmp_path, monkeypatch):
    page, _, review, override, cache = _manual_owned_case(tmp_path)
    before = snapshot_review(review)
    assert before
    stage = module._stage_recovery

    def concurrent_ocr_write(*args, **kwargs):
        result = stage(*args, **kwargs)
        cache.write_bytes(b"raced OCR cache")
        return result

    monkeypatch.setattr(module, "_stage_recovery", concurrent_ocr_write)
    assert not module.publish_owned_review_bundle(
        before, pdic_bytes=before.pdic_bytes.replace(b"one", b"ONE"),
        manual_bytes=b"new", simplified_bytes=None,
    )
    assert pdic_path(page).read_bytes() == before.pdic_bytes
    assert cache.read_bytes() == b"raced OCR cache"
    assert not override.exists()
    assert not module._recovery_path(page).exists()


def test_manual_recovery_never_trusts_ambiguous_path(tmp_path):
    page, _, _, override, _cache = _manual_owned_case(tmp_path)
    with pytest.raises(ValueError):
        module._stage_recovery(page, [
            ("pdic", b"old", b"new"), ("manual", None, b"payload"),
        ], manual_path=tmp_path / "unrelated.txt")
    assert not module._recovery_path(page).exists()


def test_application_page_reopen_supplies_trusted_candidate_override_path():
    from picture_capture import app as gui
    code = (Path(gui.__file__).parent / "ui/project_session_workflow.py").read_text(encoding="utf-8")
    assert "recover_pending_for_page(target_page, manual_path=trusted_manual_path)" in code


def test_silent_rollback_keeps_marker_and_blocks_page_reopen(tmp_path, monkeypatch):
    page, _, _, override, _cache = _manual_owned_case(tmp_path)
    old_pdic = pdic_path(page).read_bytes()
    new_pdic = old_pdic.replace(b"one", b"ONE")
    assert new_pdic != old_pdic
    marker = module._stage_recovery(page, [
        ("pdic", old_pdic, new_pdic),
        ("manual", None, b'{"selected":false}'),
    ], manual_path=override)
    module._publish(pdic_path(page), new_pdic)
    original_publish = module._publish

    def skip_rollback(path, contents):
        if path == pdic_path(page) and contents == old_pdic:
            return None  # silently skipped disk write
        return original_publish(path, contents)

    monkeypatch.setattr(module, "_publish", skip_rollback)
    assert not module.recover_pending_for_page(page, manual_path=override)
    assert marker.exists()
    assert pdic_path(page).read_bytes() == new_pdic
    monkeypatch.setattr(module, "_publish", original_publish)
    assert module.recover_pending_for_page(page, manual_path=override)
    assert pdic_path(page).read_bytes() == old_pdic
    assert not marker.exists()


def test_silent_single_file_undo_does_not_mutate_ui(tmp_path, monkeypatch):
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    committed = pdic_path(page).read_bytes()
    original_publish = module._publish

    def skip_pdic_restore(path, contents):
        if path == pdic_path(page):
            return None
        return original_publish(path, contents)

    monkeypatch.setattr(module, "_publish", skip_pdic_restore)
    assert not history.undo(review)
    assert pdic_path(page).read_bytes() == committed
    assert rows[0].word == "ONE"
    assert len(history.undo_stack) == 1



def test_live_rollback_only_marker_recovers_before_even_if_all_files_landed(tmp_path):
    page, _, _, override, _cache = _manual_owned_case(tmp_path)
    old = pdic_path(page).read_bytes()
    stages = [
        ("pdic", old, old.replace(b"two", b"TWO")),
        ("manual", None, b'{"selected":false}'),
    ]
    marker = module._stage_recovery(
        page, stages, manual_path=override, rollback_required=True,
    )
    for role, _, contents in stages:
        module._publish(pdic_path(page) if role == "pdic" else override, contents)
    assert module.recover_pending_for_page(page, manual_path=override)
    assert pdic_path(page).read_bytes() == old
    assert not override.exists()
    assert not marker.exists()


def test_single_file_write_then_raise_undo_restores_before_state(tmp_path, monkeypatch):
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    committed = pdic_path(page).read_bytes()
    target = history.undo_stack[-1].before.pdic_bytes
    original_publish = module._publish
    raised = False

    def write_then_raise(path, contents):
        nonlocal raised
        result = original_publish(path, contents)
        if path == pdic_path(page) and contents == target and not raised:
            raised = True
            raise OSError("post-replace bookkeeping failed")
        return result

    monkeypatch.setattr(module, "_publish", write_then_raise)
    assert not history.undo(review)
    assert raised
    assert pdic_path(page).read_bytes() == committed
    assert rows[0].word == "ONE"
    assert review.vars[0].get() == "ONE"
    assert len(history.undo_stack) == 1
    assert not module._recovery_path(page).exists()


@pytest.mark.parametrize("source", ["pdic", "manual", "ocr", "section", "profile"])
def test_undo_refuses_source_drift_during_recovery_marker_stage(
    tmp_path, monkeypatch, source,
):
    """No staged ordinary Undo may overwrite a later human/source version."""
    from picture_capture.persistence.project_storage import (
        page_sections_path_for_image, profile_path,
    )
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    assert history.record(*_save_words(page, rows, review, "ONE", "two"))
    committed = pdic_path(page).read_bytes()
    drift_path = {
        "pdic": pdic_path(page),
        "manual": tmp_path / "manual_selection.json",
        "ocr": tmp_path / "cache.json",
        "section": page_sections_path_for_image(page),
        "profile": profile_path(tmp_path),
    }[source]
    human_bytes = b"independent-human-or-source-version"
    stage = module._stage_recovery

    def stage_then_external_edit(*args, **kwargs):
        marker = stage(*args, **kwargs)
        drift_path.parent.mkdir(parents=True, exist_ok=True)
        drift_path.write_bytes(human_bytes)
        return marker

    monkeypatch.setattr(module, "_stage_recovery", stage_then_external_edit)
    assert not history.undo(review)
    assert drift_path.read_bytes() == human_bytes
    assert rows[0].word == "ONE"
    assert review.vars[0].get() == "ONE"
    assert len(history.undo_stack) == 1
    if source == "pdic":
        # A third-party PDIC version cannot be auto-reconciled as old/new.
        assert module._recovery_path(page).exists()
        assert not module.recover_pending_for_page(page)
    else:
        assert pdic_path(page).read_bytes() == committed
        assert not module._recovery_path(page).exists()


def test_undo_refuses_human_simplified_edit_between_two_file_writes(
    tmp_path, monkeypatch,
):
    from picture_capture.persistence.project_storage import simplified_review_path_for_image
    page, rows, review = _case(tmp_path)
    simplified = simplified_review_path_for_image(page)
    simplified.parent.mkdir(parents=True, exist_ok=True)
    simplified.write_bytes(b'{"entries":[]}')
    before = snapshot_review(review)
    rows[0].word = "ONE"
    write_pdic(pdic_path(page), rows, 120, ("synthetic", "@", "@"))
    review.vars[0].set("ONE")
    simplified.write_bytes(b'{"entries":[{"text":"saved"}]}')
    after = snapshot_review(review)
    history = ReviewSessionHistory()
    assert history.record(before, after)
    committed = pdic_path(page).read_bytes()
    human_bytes = b"human-edited-simplified-after-first-publish"
    publish = module._publish

    def race_after_pdic(path, data):
        result = publish(path, data)
        if path == pdic_path(page) and data == before.pdic_bytes:
            simplified.write_bytes(human_bytes)
        return result

    monkeypatch.setattr(module, "_publish", race_after_pdic)
    assert not history.undo(review)
    # A conflicting human sidecar makes the whole bundle unresolved. The
    # rollback policy intentionally leaves the already-landed PDIC target
    # in place instead of silently treating a partial rollback as complete.
    assert pdic_path(page).read_bytes() == before.pdic_bytes
    assert pdic_path(page).read_bytes() != committed
    assert simplified.read_bytes() == human_bytes
    assert rows[0].word == "ONE"
    assert module._recovery_path(page).exists()
    assert not module.recover_pending_for_page(page)


def test_candidate_bundle_refuses_human_manual_edit_after_pdic_publication(
    tmp_path, monkeypatch,
):
    page, rows, review, override, _cache = _manual_owned_case(tmp_path)
    before = snapshot_review(review)
    assert before is not None
    target_pdic = before.pdic_bytes.replace(b"one", b"ONE")
    human_bytes = b"third-party-manual-choice"
    publish = module._publish

    def race_after_pdic(path, data):
        result = publish(path, data)
        if path == pdic_path(page) and data == target_pdic:
            override.write_bytes(human_bytes)
        return result

    monkeypatch.setattr(module, "_publish", race_after_pdic)
    with pytest.raises(RuntimeError, match="source drift"):
        module.publish_owned_review_bundle(
            before, pdic_bytes=target_pdic,
            manual_bytes=b'{"overrides":{"candidate":{"selected":false}}}',
            simplified_bytes=before.simplified_bytes,
        )
    # Preserve the mixed on-disk state for explicit recovery; a third-party
    # manual override prevents claiming that the PDIC rollback completed.
    assert pdic_path(page).read_bytes() == target_pdic
    assert override.read_bytes() == human_bytes
    assert [row.word for row in rows] == ["one", "two"]
    assert module._recovery_path(page).exists()
    assert not module.recover_pending_for_page(page, manual_path=override)


@pytest.mark.parametrize("damage", [
    "missing_before", "missing_after", "missing_both", "boolean_version",
])
def test_r3_incomplete_journal_keeps_quarantine(tmp_path, damage):
    """A syntactically valid but incomplete recovery intent is never trusted."""
    page, _rows, _review = _case(tmp_path)
    original = pdic_path(page).read_bytes()
    published = original.replace(b"one", b"ONE")
    assert published != original
    marker = module._stage_recovery(page, [
        ("pdic", original, published),
    ])
    module._publish(pdic_path(page), published)
    document = json.loads(marker.read_text(encoding="utf-8"))
    if damage in {"missing_before", "missing_both"}:
        del document["files"][0]["before"]
    if damage in {"missing_after", "missing_both"}:
        del document["files"][0]["after"]
    if damage == "boolean_version":
        document["version"] = True  # bool is an int subclass in Python.
    marker.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="R3 recovery"):
        module.recover_pending_for_page(page)
    assert pdic_path(page).read_bytes() == published
    assert marker.is_file()  # Manual intervention, never silent unquarantine.


@pytest.mark.parametrize("operation", ["restart_recovery", "failed_live_publish"])
@pytest.mark.parametrize("tamper", ["rollback_policy", "owned_file_intent"])
def test_r3_journal_replacement_quarantines_after_parse(
    tmp_path, monkeypatch, operation, tamper,
):
    """A peer's new intent must not be combined with our old file list."""
    page, _rows, _review = _case(tmp_path)
    original = pdic_path(page).read_bytes()
    target = original.replace(b"one", b"ONE")
    assert target != original
    marker = module._stage_recovery(page, [
        ("pdic", original, target),
    ], rollback_required=True)
    module._publish(pdic_path(page), target)
    verified = module._verified_recovery

    def change_journal_after_parse(*args, **kwargs):
        result = verified(*args, **kwargs)
        doc = json.loads(marker.read_text(encoding="utf-8"))
        if tamper == "rollback_policy":
            doc["rollback_required"] = False
        else:
            doc["files"][0]["before"] = module._encode(b"wrong-owner-data")
        marker.write_text(json.dumps(doc), encoding="utf-8")
        return result

    monkeypatch.setattr(module, "_verified_recovery", change_journal_after_parse)
    if operation == "restart_recovery":
        assert not module.recover_pending_for_page(page)
    else:
        assert not module._rollback_failed_publish(page)
    assert pdic_path(page).read_bytes() == target
    assert marker.is_file()
    assert not module.snapshot_review(_review)


@pytest.mark.parametrize("operation", ["restart_recovery", "failed_live_publish"])
@pytest.mark.parametrize("tamper", ["rollback_policy", "owned_file_intent"])
def test_r3_journal_replacement_during_first_rollback_stops_next_file(
    tmp_path, monkeypatch, operation, tamper,
):
    """Do not finish an old transaction or erase a newly changed marker."""
    from picture_capture.persistence.project_storage import simplified_review_path_for_image
    page, _rows, _review = _case(tmp_path)
    companion = simplified_review_path_for_image(page)
    companion.parent.mkdir(parents=True, exist_ok=True)
    old_companion, new_companion = b"manual-old", b"manual-new"
    companion.write_bytes(old_companion)
    old_pdic = pdic_path(page).read_bytes()
    new_pdic = old_pdic.replace(b"one", b"ONE")
    marker = module._stage_recovery(page, [
        ("pdic", old_pdic, new_pdic),
        ("simplified", old_companion, new_companion),
    ], rollback_required=True)
    module._publish(pdic_path(page), new_pdic)
    module._publish(companion, new_companion)
    actual_publish = module._publish

    def replace_journal_after_first_file(path, data):
        actual_publish(path, data)
        if path == pdic_path(page) and data == old_pdic:
            doc = json.loads(marker.read_text(encoding="utf-8"))
            if tamper == "rollback_policy":
                doc["rollback_required"] = False
            else:
                doc["files"][1]["after"] = module._encode(b"other-owned-version")
            marker.write_text(json.dumps(doc), encoding="utf-8")

    monkeypatch.setattr(module, "_publish", replace_journal_after_first_file)
    if operation == "restart_recovery":
        assert not module.recover_pending_for_page(page)
    else:
        assert not module._rollback_failed_publish(page)
    assert pdic_path(page).read_bytes() == old_pdic
    assert companion.read_bytes() == new_companion
    assert marker.is_file()


def test_r3_untouched_marker_recovery_preserves_complete_after_state(tmp_path):
    page, _rows, _review = _case(tmp_path)
    original = pdic_path(page).read_bytes()
    target = original.replace(b"one", b"ONE")
    marker = module._stage_recovery(page, [
        ("pdic", original, target),
    ], rollback_required=False)
    module._publish(pdic_path(page), target)
    assert module.recover_pending_for_page(page)
    assert pdic_path(page).read_bytes() == target
    assert not marker.exists()


def test_plain_undo_redo_discards_stale_simplified_cache_and_origin_pin(tmp_path):
    """Restoring disk bytes must force the next Tk render to re-pin that version."""
    page, rows, review = _case(tmp_path)
    history = ReviewSessionHistory()
    before, after = _save_words(page, rows, review, "ONE", "two")
    assert history.record(before, after)
    review._simplified_page_cache = {page.stem: {"10,20": {
        "x": 10, "y": 20, "source_word": "ONE", "text": "stale manual",
        "manual": True,
    }}}
    review._r3_simplified_source_bytes = {page.stem: (
        page.with_suffix(".review.json"), b"stale source bytes",
    )}
    assert history.undo(review)
    assert page.stem not in review._simplified_page_cache
    assert page.stem not in review._r3_simplified_source_bytes
    review._simplified_page_cache[page.stem] = {"10,20": {"source_word": "one"}}
    review._r3_simplified_source_bytes[page.stem] = (page, b"old")
    assert history.redo(review)
    assert page.stem not in review._simplified_page_cache
    assert page.stem not in review._r3_simplified_source_bytes
