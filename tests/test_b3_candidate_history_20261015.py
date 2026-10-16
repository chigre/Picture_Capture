"""B3/R3 exact candidate replay contract, generated data only (no private scans)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.project_storage import simplified_review_path_for_image
from picture_capture.proofreading_candidate_delete import commit_candidate_delete
from picture_capture.proofreading_candidate_history import CandidateReviewHistory
from picture_capture.proofreading_transactions import snapshot_review
from picture_capture import proofreading_transactions as tx


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def setup_case(tmp_path: Path, *, count: int = 2, legacy: bool = False):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic fingerprint only")
    owned = Entry("head", 10, 20, candidate_id="ocr-owned")
    others = [Entry(f"other{i}", 30 + 10 * i, 40 + 10 * i)
              for i in range(count - 1)]
    rows = [owned, *others]
    write_pdic(pdic_path(page), rows, 200, ("synthetic", "@", "@"))
    cache = tmp_path / "QT" / "PaddleOCR"
    cache.mkdir(parents=True)
    manual = cache / "synthetic_manual_selection.json"
    candidate = {"candidate_id": "ocr-owned", "word": "head",
                 "source_x": 10, "source_y": 20}
    if not legacy:
        candidate["selected"] = True
    app = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path), current_page=page,
        current_index=0, entries=rows,
        settings=SimpleNamespace(proofreading_event_capture=False),
        _batch_active=False, _pending_manual_override_payload=None,
        _manual_selection_path=lambda: manual,
        _paddle_cache_path=lambda: cache / "synthetic.json",
        ocr_review_candidates=[candidate],
        candidate_check_vars={"ocr-owned": Var(True)},
        _last_pdic_write_changed=False,
        _refresh_word_fill_check_from_line_count=lambda *a, **kw: None,
        _update_page_row=lambda *a: None,
    )
    review = SimpleNamespace(
        parent=app, _filter_rows_active=False,
        _rendered_page_stem=page.stem, _simplified_dirty_pages=set(),
        _simplified_page_cache={}, vars=[Var(e.word) for e in rows],
    )
    review._bound_row_entries = lambda: app.entries
    return page, owned, review, candidate, manual


def committed_delete(page, owned, review, candidate):
    before = snapshot_review(review)
    assert before is not None
    selected_before = candidate.get("selected")
    plan = commit_candidate_delete(before, owned, candidate)
    assert plan is not None
    candidate["selected"] = False
    review.parent.candidate_check_vars["ocr-owned"].set(False)
    review.parent.entries[:] = [e for e in review.parent.entries if e is not owned]
    review.vars = [Var(e.word) for e in review.parent.entries]
    after = snapshot_review(review)
    assert after is not None
    history = CandidateReviewHistory()
    assert history.record_candidate_delete(before, after, candidate, selected_before, plan)
    return history, before, after


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("count", [1, 3])
def test_exact_owned_candidate_undo_redo_roundtrip(tmp_path, legacy, count):
    page, owned, review, candidate, manual = setup_case(
        tmp_path, count=count, legacy=legacy,
    )
    original = pdic_path(page).read_bytes()
    history, before, after = committed_delete(page, owned, review, candidate)
    assert manual.exists()
    after_manual = manual.read_bytes()
    assert history.undo(review)
    assert pdic_path(page).read_bytes() == original
    assert not manual.exists()
    assert review.parent.entries[0] is owned
    assert review.parent.candidate_check_vars["ocr-owned"].get() is True
    assert ("selected" not in candidate) if legacy else (candidate["selected"] is True)
    assert not tx._recovery_path(page).exists()
    review.vars = [Var(e.word) for e in review.parent.entries]
    assert history.redo(review)
    assert pdic_path(page).read_bytes() == after.pdic_bytes
    assert manual.read_bytes() == after_manual
    assert owned not in review.parent.entries
    assert candidate["selected"] is False
    assert review.parent.candidate_check_vars["ocr-owned"].get() is False
    assert not tx._recovery_path(page).exists()


def test_external_manual_drift_refuses_without_touching_disk_or_ui(tmp_path):
    page, owned, review, candidate, manual = setup_case(tmp_path)
    history, _, after = committed_delete(page, owned, review, candidate)
    manual.write_bytes(b'{"page":"synthetic","overrides":{"new":"external"}}')
    changed = manual.read_bytes()
    assert history.undo(review) is False
    assert pdic_path(page).read_bytes() == after.pdic_bytes
    assert manual.read_bytes() == changed
    assert candidate["selected"] is False
    assert owned not in review.parent.entries


def test_rollback_failure_keeps_model_and_all_original_files(tmp_path, monkeypatch):
    page, owned, review, candidate, manual = setup_case(tmp_path)
    history, _, after = committed_delete(page, owned, review, candidate)
    old_manual = manual.read_bytes()
    original_publish = tx._publish
    failed = False

    def fail_manual_once(path, data):
        nonlocal failed
        if path == manual and not failed:
            failed = True
            raise OSError("injected disk failure")
        return original_publish(path, data)

    monkeypatch.setattr(tx, "_publish", fail_manual_once)
    assert history.undo(review) is False
    assert pdic_path(page).read_bytes() == after.pdic_bytes
    assert manual.read_bytes() == old_manual
    assert candidate["selected"] is False
    assert owned not in review.parent.entries
    assert not tx._recovery_path(page).exists()
    monkeypatch.setattr(tx, "_publish", original_publish)
    assert history.undo(review) is True


def test_unsaved_text_and_dirty_simplified_refuse_candidate_replay(tmp_path):
    page, owned, review, candidate, manual = setup_case(tmp_path)
    history, _, after = committed_delete(page, owned, review, candidate)
    review.vars[0].set("pending")
    assert not history.undo(review)
    assert pdic_path(page).read_bytes() == after.pdic_bytes
    review.vars[0].set("other0")
    review._simplified_dirty_pages.add(page.stem)
    assert not history.undo(review)
    review._simplified_dirty_pages.clear()
    assert history.undo(review)


def test_stale_candidate_payload_and_page_change_refuse(tmp_path):
    page, owned, review, candidate, manual = setup_case(tmp_path)
    history, _, after = committed_delete(page, owned, review, candidate)
    candidate["word"] = "changed by OCR"
    assert not history.undo(review)
    assert pdic_path(page).read_bytes() == after.pdic_bytes
    candidate["word"] = "head"
    review.parent.current_page = tmp_path / "other.png"
    assert not history.undo(review)


def test_compound_source_is_not_misclassified_as_candidate_delete(tmp_path):
    page, owned, review, candidate, manual = setup_case(tmp_path)
    before = snapshot_review(review)
    assert before is not None
    plan = commit_candidate_delete(before, owned, candidate)
    assert plan is not None
    candidate["selected"] = False
    review.parent.entries[:] = []
    review.vars = []
    after = snapshot_review(review, allow_unbound=True)
    assert after is None  # Surviving row remains on disk; no guessed ownership.



def test_partial_tk_variable_bindings_refuse_candidate_undo(tmp_path):
    page, owned, review, candidate, manual = setup_case(tmp_path, count=3)
    history, _, after = committed_delete(page, owned, review, candidate)
    review.vars = review.vars[:1]
    assert history.undo(review) is False
    assert pdic_path(page).read_bytes() == after.pdic_bytes
    assert candidate["selected"] is False
    assert owned not in review.parent.entries


def test_new_ordinary_save_after_candidate_undo_clears_redo_and_replay_refs(tmp_path):
    page, owned, review, candidate, manual = setup_case(tmp_path)
    history, _, _ = committed_delete(page, owned, review, candidate)
    assert history.undo(review)
    assert len(history.redo_stack) == 1
    review.vars = [Var(row.word) for row in review.parent.entries]
    before = snapshot_review(review)
    assert before is not None
    ordinary = review.parent.entries[-1]
    ordinary.word = "renamed"
    write_pdic(pdic_path(page), review.parent.entries, 200, ("synthetic", "@", "@"))
    review.vars[-1].set("renamed")
    after = snapshot_review(review)
    assert after is not None
    assert history.record(before, after)
    assert history.redo_stack == []
    assert history._candidate_frames == {}
    assert history.redo(review) is False
    assert pdic_path(page).read_bytes() == after.pdic_bytes


def test_candidate_undo_blocks_stale_simplified_focusout_capture(tmp_path):
    from picture_capture.app import ReviewWindow

    page, owned, review, candidate, manual = setup_case(tmp_path)
    history, _, _ = committed_delete(page, owned, review, candidate)
    review.vars = [Var(row.word) for row in review.parent.entries]
    assert history.undo(review)
    assert review.__dict__.get("_r3_simplified_capture_blocked") is True
    review.simplified_vars = [Var("stale value")]
    ReviewWindow._capture_simplified_edits(review, page.stem)
    assert review._simplified_page_cache == {}


def test_failed_candidate_undo_does_not_enter_repaint_guard(tmp_path):
    page, owned, review, candidate, manual = setup_case(tmp_path)
    history, _, _ = committed_delete(page, owned, review, candidate)
    review.vars[0].set("unsaved")
    assert history.undo(review) is False
    assert review.__dict__.get("_r3_simplified_capture_blocked") is None

def test_recovery_rollback_io_failure_quarantines_until_verified_reload(tmp_path, monkeypatch):
    """A second I/O failure may leave a journal; never claim atomic rollback."""
    page, owned, review, candidate, manual = setup_case(tmp_path)
    history, _, after = committed_delete(page, owned, review, candidate)
    original_publish = tx._publish
    faults = {"manual": False, "rollback": False}

    def fail_commit_then_rollback(path, data):
        if path == manual and not faults["manual"]:
            faults["manual"] = True
            raise OSError("injected manual publication failure")
        if path == pdic_path(page) and faults["manual"] and not faults["rollback"]:
            faults["rollback"] = True
            raise OSError("injected rollback failure")
        return original_publish(path, data)

    with monkeypatch.context() as patcher:
        patcher.setattr(tx, "_publish", fail_commit_then_rollback)
        assert history.undo(review) is False
    assert faults == {"manual": True, "rollback": True}
    assert tx._recovery_path(page).exists()
    assert tx.snapshot_review(review) is None
    assert candidate["selected"] is False
    assert owned not in review.parent.entries

    assert tx.recover_pending_for_page(page, manual_path=manual)
    assert not tx._recovery_path(page).exists()
    assert pdic_path(page).read_bytes() == after.pdic_bytes
    assert candidate["selected"] is False
    review.vars = [Var(row.word) for row in review.parent.entries]
    assert history.undo(review)
    assert owned in review.parent.entries


def test_candidate_delete_twenty_repeated_undo_redo_roundtrips(tmp_path):
    page, owned, review, candidate, manual = setup_case(tmp_path)
    history, before, after = committed_delete(page, owned, review, candidate)
    for _ in range(20):
        review.vars = [Var(row.word) for row in review.parent.entries]
        assert history.undo(review)
        assert pdic_path(page).read_bytes() == before.pdic_bytes
        assert candidate.get("selected", True) is True
        review.vars = [Var(row.word) for row in review.parent.entries]
        assert history.redo(review)
        assert pdic_path(page).read_bytes() == after.pdic_bytes
        assert candidate["selected"] is False
    assert len(history.undo_stack) == 1
    assert len(history.redo_stack) == 0
