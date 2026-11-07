"""B3/R3 exact candidate replay contract, generated data only (no private scans)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.io.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.persistence.project_storage import simplified_review_path_for_image
from picture_capture.proofreading.candidate_delete import commit_candidate_delete
from picture_capture.proofreading.candidate_history import CandidateReviewHistory
from picture_capture.proofreading.transactions import snapshot_review
from picture_capture.proofreading import transactions as tx


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


def test_candidate_undo_redo_clears_stale_manual_sidecar_origin_pin(tmp_path):
    """A verified multi-file replay must invalidate both cached data and pin."""
    page, owned, review, candidate, manual = setup_case(tmp_path, count=2)
    history, before, after = committed_delete(page, owned, review, candidate)
    review._simplified_page_cache[page.stem] = {"10,20": {
        "source_word": "head", "text": "stale manual correction",
    }}
    review._r3_simplified_source_bytes = {page.stem: (page, b"wrong version")}
    assert history.undo(review)
    assert page.stem not in review._simplified_page_cache
    assert page.stem not in review._r3_simplified_source_bytes
    review.vars = [Var(e.word) for e in review.parent.entries]
    review._simplified_page_cache[page.stem] = {"10,20": {"source_word": "head"}}
    review._r3_simplified_source_bytes[page.stem] = (page, b"wrong again")
    assert history.redo(review)
    assert page.stem not in review._simplified_page_cache
    assert page.stem not in review._r3_simplified_source_bytes


@pytest.mark.parametrize("direction", ["undo", "redo"])
@pytest.mark.parametrize("source", [
    "image", "pdic", "simplified", "manual", "ocr", "section", "profile",
])
def test_candidate_replay_snapshot_failure_unreadable_source_fail_closed(
    tmp_path, monkeypatch, capsys, direction, source,
):
    """Unreadable owned source on Tk snapshot failure cannot crash replay.

    Disk changes are never inferred from the saved history on a denied read.
    This is a synthetic diagnostic, not actual Windows operator E3.
    """
    from picture_capture.proofreading import transactions as files
    page, owned, review, candidate, manual = setup_case(tmp_path)
    history, before, after = committed_delete(page, owned, review, candidate)
    if direction == "redo":
        assert history.undo(review)
        review.vars = [Var(e.word) for e in review.parent.entries]
    expected = after if direction == "undo" else before
    original_pdic = pdic_path(page).read_bytes()
    original_manual = manual.read_bytes() if manual.exists() else None
    original_membership = tuple(review.parent.entries)
    original_candidate = dict(candidate)
    sentinel = "PRIVATE_CANDIDATE_SOURCE_DO_NOT_LOG"

    # This simulates an otherwise transient row rebind. The explicit second
    # source check must distinguish unreadable backing data from a safe retry.
    monkeypatch.setattr(files, "snapshot_review", lambda *_a, **_kw: None)
    paths = {
        "pdic": pdic_path(page),
        "simplified": simplified_review_path_for_image(page),
        "manual": expected.manual_path,
        "ocr": expected.ocr_path,
        "section": expected.section_path,
        "profile": expected.profile_path,
    }
    if source == "image":
        original_hash = files.sha256_file
        def unreadable_hash(path):
            if path == page:
                raise PermissionError(sentinel)
            return original_hash(path)
        monkeypatch.setattr(files, "sha256_file", unreadable_hash)
    else:
        original_reader = files._bytes_or_absent
        assert paths[source] is not None
        def unreadable_reader(path):
            if path == paths[source]:
                raise PermissionError(sentinel)
            return original_reader(path)
        monkeypatch.setattr(files, "_bytes_or_absent", unreadable_reader)

    assert (history.undo(review) if direction == "undo" else history.redo(review)) is False
    assert not history.undo_stack and not history.redo_stack
    assert history._candidate_frames == {}
    assert tuple(review.parent.entries) == original_membership
    assert dict(candidate) == original_candidate
    assert pdic_path(page).read_bytes() == original_pdic
    assert (manual.read_bytes() if manual.exists() else None) == original_manual
    assert sentinel not in repr(capsys.readouterr())


@pytest.mark.parametrize("direction", ["undo", "redo"])
@pytest.mark.parametrize("source", ["section", "profile"])
def test_candidate_replay_transient_tk_rebind_with_sidecar_drift_invalidates(
    tmp_path, monkeypatch, direction, source,
):
    """A real SECTION/Profile drift cannot retain an obsolete candidate redo."""
    from picture_capture.proofreading import transactions as files
    page, owned, review, candidate, manual = setup_case(tmp_path)
    history, before, after = committed_delete(page, owned, review, candidate)
    if direction == "redo":
        assert history.undo(review)
        review.vars = [Var(e.word) for e in review.parent.entries]
    expected = after if direction == "undo" else before
    target = expected.section_path if source == "section" else expected.profile_path
    assert target is not None
    target.parent.mkdir(parents=True, exist_ok=True)
    original = target.read_bytes() if target.exists() else None
    changed = (original or b"") + b"foreign-owner-write"
    target.write_bytes(changed)
    pdic_before = pdic_path(page).read_bytes()
    selection_before = dict(candidate)
    monkeypatch.setattr(files, "snapshot_review", lambda *_a, **_kw: None)

    assert (history.undo(review) if direction == "undo" else history.redo(review)) is False
    assert history.undo_stack == [] and history.redo_stack == []
    assert history._candidate_frames == {}
    assert target.read_bytes() == changed
    assert pdic_path(page).read_bytes() == pdic_before
    assert candidate == selection_before


@pytest.mark.parametrize("direction", ["undo", "redo"])
def test_candidate_replay_transient_tk_rebind_with_unchanged_sources_retryable(
    tmp_path, monkeypatch, direction,
):
    from picture_capture.proofreading import transactions as files
    page, owned, review, candidate, manual = setup_case(tmp_path)
    history, before, after = committed_delete(page, owned, review, candidate)
    if direction == "redo":
        assert history.undo(review)
        review.vars = [Var(e.word) for e in review.parent.entries]
    original_stack = len(history.redo_stack if direction == "redo" else history.undo_stack)
    monkeypatch.setattr(files, "snapshot_review", lambda *_a, **_kw: None)
    assert (history.undo(review) if direction == "undo" else history.redo(review)) is False
    assert len(history.redo_stack if direction == "redo" else history.undo_stack) == original_stack
    assert len(history._candidate_frames) == 1
