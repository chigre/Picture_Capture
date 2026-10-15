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
    assert 'self._review_flat_button(row1, "撤销保存"' in source
    assert 'self._review_flat_button(row1, "重做保存"' in source
    assert "record_review_after(self, transaction_before)" in source
    assert "record_review_after(self, transaction_before, allow_unbound=True)" in source



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
    from picture_capture.project_storage import (
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
    from picture_capture.project_storage import (
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
    from picture_capture.project_storage import simplified_review_path_for_image
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
    from picture_capture.project_storage import simplified_review_path_for_image
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
    from picture_capture.project_storage import simplified_review_path_for_image
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
    from picture_capture.project_storage import simplified_review_path_for_image
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
    code = Path(gui.__file__).read_text(encoding="utf-8")
    assert "recover_pending_for_page(target_page, manual_path=trusted_manual_path)" in code
