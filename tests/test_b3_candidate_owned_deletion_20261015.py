"""R3 candidate-linked delete: no disk/UI split, exact Entry ownership, no scans."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.io.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.persistence.project_storage import simplified_review_path_for_image
from picture_capture.proofreading.candidate_delete import (
    commit_candidate_delete, prepare_candidate_delete,
)
from picture_capture.proofreading.transactions import snapshot_review
from picture_capture.proofreading import transactions as storage
from picture_capture.ui.review_candidate_delete_actions import (
    delete_owned_review_candidate,
)


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _case(tmp_path, *, n=2, with_simplified=True):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic page fingerprint, no private scan")
    entry = Entry("head", 10, 20, candidate_id="ocr-id")
    rows = [entry] + ([Entry("other", 30, 40)] if n == 2 else [])
    write_pdic(pdic_path(page), rows, 200, ("synthetic", "@", "@"))
    directory = tmp_path / "QT" / "PaddleOCR"
    directory.mkdir(parents=True)
    manual_path = directory / "synthetic_manual_selection.json"
    ocr_path = directory / "synthetic.json"
    candidate = {
        "candidate_id": "ocr-id", "selected": True, "word": "head",
        "source_x": 10, "source_y": 20, "final_engine": "paddle",
    }
    actions = []
    app = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path), current_page=page,
        current_index=0, entries=rows,
        settings=SimpleNamespace(proofreading_event_capture=False),
        _batch_active=False, _pending_manual_override_payload=None,
        _manual_selection_path=lambda: manual_path,
        _paddle_cache_path=lambda: ocr_path,
        ocr_review_candidates=[candidate],
        candidate_check_vars={"ocr-id": Var(True)},
        status_var=Var(""),
        _sort_entries_reading_order=lambda: actions.append("sort"),
        _refresh_word_fill_check_from_line_count=lambda *a, **kw: actions.append("count"),
        _update_page_row=lambda *a: actions.append("page"),
        clear_review_entry_highlight=lambda: actions.append("clear"),
        redraw=lambda: actions.append("redraw"),
    )
    review = SimpleNamespace(
        parent=app, _filter_rows_active=False,
        _rendered_page_stem=page.stem,
        _simplified_dirty_pages=set(), _simplified_page_cache={},
        vars=[Var(row.word) for row in rows],
        active_index=0,
        _request_render_rows=lambda **kw: actions.append("render"),
        _show_ocr_options=lambda *a: actions.append("empty"),
        _update_title=lambda: actions.append("title"),
    )
    review._bound_row_entries = lambda: app.entries
    simplified = simplified_review_path_for_image(page)
    if with_simplified:
        simplified.parent.mkdir(parents=True, exist_ok=True)
        simplified.write_text(json.dumps({
            "format": "picture_capture_simplified_review",
            "format_version": 1,
            "page": page.stem,
            "entries": [
                {"x": row.x, "y": row.y, "source_word": row.word,
                 "text": row.word, "manual": True}
                for row in rows
            ],
        }, ensure_ascii=False), encoding="utf-8")
    return page, rows, review, candidate, manual_path, simplified, actions


def test_owned_candidate_delete_commits_all_files_before_mutating_ui(tmp_path):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    original_other = rows[1]
    pdic_before = pdic_path(page).read_bytes()
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert [e.word for e in read_pdic(pdic_path(page))] == ["other"]
    assert b"other" in pdic_path(page).read_bytes()
    assert b"head" in pdic_before
    assert review.parent.entries == [original_other]
    assert candidate["selected"] is False
    assert review.parent.candidate_check_vars["ocr-id"].get() is False
    doc = json.loads(manual.read_text("utf-8"))
    assert doc["overrides"]["ocr-id"] == {
        "selected": False, "word": "head", "engine": "review_delete",
    }
    assert [r["source_word"] for r in json.loads(simplified.read_text("utf-8"))["entries"]] == ["other"]
    assert "redraw" in actions and "render" in actions
    assert not storage._recovery_path(page).exists()


@pytest.mark.parametrize("failed_role", ["manual", "simplified"])
def test_candidate_delete_does_not_touch_memory_on_multifile_failure(
    tmp_path, monkeypatch, failed_role,
):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    before_pdic = pdic_path(page).read_bytes()
    before_simplified = simplified.read_bytes()
    original = storage._publish
    chosen = manual if failed_role == "manual" else simplified
    failed = False

    def fail_once(path, contents):
        nonlocal failed
        if path == chosen and not failed:
            failed = True
            raise OSError("injected I/O failure")
        return original(path, contents)

    monkeypatch.setattr(storage, "_publish", fail_once)
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert pdic_path(page).read_bytes() == before_pdic
    assert simplified.read_bytes() == before_simplified
    assert not manual.exists()
    assert review.parent.entries == rows
    assert candidate["selected"] is True
    assert review.parent.candidate_check_vars["ocr-id"].get() is True
    assert not actions
    assert not storage._recovery_path(page).exists()


def test_dirty_tk_or_simplified_editor_refuses_before_any_write(tmp_path):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    original = pdic_path(page).read_bytes()
    review.vars[0].set("unsaved typing")
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert pdic_path(page).read_bytes() == original
    assert not manual.exists()
    review.vars[0].set("head")
    review._simplified_dirty_pages.add(page.stem)
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert pdic_path(page).read_bytes() == original
    assert candidate["selected"] is True


def test_duplicate_ocr_candidate_id_or_stale_owner_blocks_delete(tmp_path):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    original = pdic_path(page).read_bytes()
    review.parent.ocr_review_candidates.append(dict(candidate))
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert pdic_path(page).read_bytes() == original
    review.parent.ocr_review_candidates.pop()
    rows[0].candidate_id = "changed-owner"
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert pdic_path(page).read_bytes() == original


def test_malformed_existing_manual_or_simplified_data_is_not_overwritten(tmp_path):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    original = pdic_path(page).read_bytes()
    manual.write_bytes(b"{invalid existing human override")
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert manual.read_bytes() == b"{invalid existing human override"
    manual.unlink()
    simplified.write_bytes(b"broken JSON")
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert simplified.read_bytes() == b"broken JSON"
    assert pdic_path(page).read_bytes() == original


def test_candidate_delete_last_row_persists_empty_pdic_without_stale_ui(tmp_path):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path, n=1)
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert pdic_path(page).read_bytes() == b""
    assert not review.parent.entries
    assert "empty" in actions and "title" in actions
    assert candidate["selected"] is False


def test_non_utf8_pdic_or_discordant_manual_page_fails_closed(tmp_path):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    before = snapshot_review(review)
    assert before is not None
    manual.write_text('{"version":1,"page":"other_page","overrides":{}}', encoding="utf-8")
    # Snapshot captures the changed file but the candidate builder rejects
    # persisted manual overrides for another page.
    after = snapshot_review(review)
    assert after is not None
    assert prepare_candidate_delete(after, rows[0], candidate) is None
    assert candidate["selected"] is True


def test_r2_evidence_mode_refuses_candidate_atomic_without_silent_loss(tmp_path):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    review.parent.settings.proofreading_event_capture = True
    before = pdic_path(page).read_bytes()
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert pdic_path(page).read_bytes() == before
    assert not manual.exists()


def test_prepare_does_not_write_until_explicit_transaction_commit(tmp_path):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    before = snapshot_review(review)
    assert before is not None
    unchanged = pdic_path(page).read_bytes()
    plan = prepare_candidate_delete(before, rows[0], candidate)
    assert plan and plan.candidate_id == "ocr-id"
    assert pdic_path(page).read_bytes() == unchanged
    assert not manual.exists()
    completed = commit_candidate_delete(before, rows[0], candidate)
    assert completed == plan
    # Pure commit never mutates Entry/candidate state. UI coordinator does
    # so only after the durability boundary.
    assert candidate["selected"] is True
    assert rows[0] in review.parent.entries


def test_legacy_ocr_candidate_without_selected_flag_is_owned_by_live_entry(tmp_path):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    candidate.pop("selected")
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert [row.word for row in read_pdic(pdic_path(page))] == ["other"]
    assert candidate["selected"] is False
    assert review.parent.candidate_check_vars["ocr-id"].get() is False


def test_explicit_false_ocr_selection_is_not_reactivated_by_delete(tmp_path):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    candidate["selected"] = False
    original = pdic_path(page).read_bytes()
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert pdic_path(page).read_bytes() == original
    assert not manual.exists()
    assert rows[0] in review.parent.entries



def test_missing_tk_row_binding_refuses_candidate_delete_before_write(tmp_path):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    before_pdic = pdic_path(page).read_bytes()
    before_simplified = simplified.read_bytes()
    review.vars = review.vars[:1]
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert pdic_path(page).read_bytes() == before_pdic
    assert simplified.read_bytes() == before_simplified
    assert not manual.exists()
    assert candidate["selected"] is True
    assert review.parent.entries == rows
    assert not actions


def test_real_delete_ui_records_candidate_history_and_replays_bytes(tmp_path):
    from picture_capture.ui.review_transaction_actions import _history

    page, rows, review, candidate, manual, simplified, _ = _case(tmp_path)
    original = pdic_path(page).read_bytes()
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    after = pdic_path(page).read_bytes()
    history = _history(review)
    assert len(history.undo_stack) == 1
    review.vars = [Var(row.word) for row in review.parent.entries]
    assert history.undo(review)
    assert pdic_path(page).read_bytes() == original
    assert not manual.exists()
    assert rows[0] in review.parent.entries
    assert candidate["selected"] is True
    review.vars = [Var(row.word) for row in review.parent.entries]
    assert history.redo(review)
    assert pdic_path(page).read_bytes() == after
    assert candidate["selected"] is False


def test_invalid_candidate_row_index_fails_closed(tmp_path):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    before_pdic = pdic_path(page).read_bytes()
    before_simplified = simplified.read_bytes()
    for stale_rows, index in ((rows, -1), (rows, len(rows)), ([], 0)):
        assert delete_owned_review_candidate(review, index, stale_rows) == "break"
        assert pdic_path(page).read_bytes() == before_pdic
        assert simplified.read_bytes() == before_simplified
        assert not manual.exists()
        assert candidate["selected"] is True
        assert review.parent.entries == rows
        assert review.parent.candidate_check_vars["ocr-id"].get() is True
        assert not actions


def test_silent_partial_publisher_refuses_candidate_commit(tmp_path, monkeypatch):
    """No false success if a storage adapter returns without writing bytes."""
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    old_pdic = pdic_path(page).read_bytes()
    old_simplified = simplified.read_bytes()
    original_publish = storage._publish
    skipped = False

    def silent_manual_noop(path, data):
        nonlocal skipped
        if path == manual and not skipped:
            skipped = True
            return None
        return original_publish(path, data)

    monkeypatch.setattr(storage, "_publish", silent_manual_noop)
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert skipped
    assert pdic_path(page).read_bytes() == old_pdic
    assert simplified.read_bytes() == old_simplified
    assert not manual.exists()
    assert not storage._recovery_path(page).exists()
    assert review.parent.entries == rows
    assert candidate["selected"] is True
    assert review.parent.candidate_check_vars["ocr-id"].get() is True
    assert not actions



def test_last_file_write_then_raise_candidate_delete_forces_before_state(
    tmp_path, monkeypatch,
):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    old_pdic = pdic_path(page).read_bytes()
    old_simplified = simplified.read_bytes()
    original_publish = storage._publish
    raised = False

    def write_then_raise(path, contents):
        nonlocal raised
        result = original_publish(path, contents)
        if path == simplified and not raised:
            raised = True
            raise OSError("last write committed, then raised")
        return result

    monkeypatch.setattr(storage, "_publish", write_then_raise)
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert raised
    assert pdic_path(page).read_bytes() == old_pdic
    assert simplified.read_bytes() == old_simplified
    assert not manual.exists()
    assert review.parent.entries == rows
    assert candidate["selected"] is True
    assert review.parent.candidate_check_vars["ocr-id"].get() is True
    assert not actions
    assert not storage._recovery_path(page).exists()


def test_failed_final_write_plus_failed_rollback_quarantines_page(
    tmp_path, monkeypatch,
):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    old_pdic = pdic_path(page).read_bytes()
    original_publish = storage._publish
    raised = False

    def double_fault(path, contents):
        nonlocal raised
        if path == pdic_path(page) and contents == old_pdic:
            return None
        result = original_publish(path, contents)
        if path == simplified and not raised:
            raised = True
            raise OSError("last write landed before failure")
        return result

    monkeypatch.setattr(storage, "_publish", double_fault)
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert raised
    assert storage._recovery_path(page).exists()
    assert not storage.recover_pending_for_page(page, manual_path=manual)
    assert review.parent.entries == rows
    assert candidate["selected"] is True
    assert not actions
    monkeypatch.setattr(storage, "_publish", original_publish)
    assert storage.recover_pending_for_page(page, manual_path=manual)
    assert pdic_path(page).read_bytes() == old_pdic
    assert not storage._recovery_path(page).exists()


def test_missing_recovery_marker_silent_noop_refuses_bundle(tmp_path, monkeypatch):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    old_pdic = pdic_path(page).read_bytes()
    old_simplified = simplified.read_bytes()
    marker = storage._recovery_path(page)

    # The recovery journal now has an independent O_EXCL creation owner.
    # Inject a silent no-op at that actual boundary, not the ordinary
    # PDIC/simplified atomic-byte writer which no longer stages journals.
    monkeypatch.setattr(
        storage, "_create_exclusive_recovery_marker",
        lambda path, data: None,
    )
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert pdic_path(page).read_bytes() == old_pdic
    assert simplified.read_bytes() == old_simplified
    assert not manual.exists()
    assert not marker.exists()
    assert review.parent.entries == rows
    assert candidate["selected"] is True
    assert not actions


def test_silent_marker_unlink_cannot_report_success_and_rollback_on_restart(
    tmp_path, monkeypatch,
):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    old_pdic = pdic_path(page).read_bytes()
    old_simplified = simplified.read_bytes()
    marker = storage._recovery_path(page)
    real_unlink = Path.unlink

    def silent_marker_unlink(self, *args, **kwargs):
        if self == marker:
            return None
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", silent_marker_unlink)
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert marker.exists()
    assert pdic_path(page).read_bytes() == old_pdic
    assert simplified.read_bytes() == old_simplified
    assert not manual.exists()
    assert review.parent.entries == rows
    assert candidate["selected"] is True
    assert not actions
    monkeypatch.setattr(Path, "unlink", real_unlink)
    assert storage.recover_pending_for_page(page, manual_path=manual)
    assert not marker.exists()


# #503 G1 provenance hardening: distinguish record ownership from mere
# coordinate equality, and avoid reusing shared OCR candidate IDs.
@pytest.mark.parametrize("owner", ["second_row", "duplicate_fingerprint"])
def test_candidate_delete_rejects_non_unique_entry_candidate_ownership(
    tmp_path, owner,
):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    pdic = pdic_path(page)
    before_pdic, before_simplified = pdic.read_bytes(), simplified.read_bytes()
    if owner == "second_row":
        rows[1].candidate_id = "ocr-id"
        assert snapshot_review(review) is not None
    else:
        snapshot = snapshot_review(review)
        assert snapshot is not None
        from dataclasses import replace
        # A forged/duplicated identity fingerprint must not become an
        # authoritative 1:1 ownership mapping during preparation.
        duplicate = replace(
            snapshot, owner_ids=snapshot.owner_ids + ((id(rows[0]), "ocr-id"),)
        )
        assert prepare_candidate_delete(duplicate, rows[0], candidate) is None
        return
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert pdic.read_bytes() == before_pdic
    assert simplified.read_bytes() == before_simplified
    assert not manual.exists()
    assert candidate["selected"] is True
    assert review.parent.candidate_check_vars["ocr-id"].get() is True
    assert not actions


@pytest.mark.parametrize(
    "mutation",
    ["foreign_source_word", "wrong_page", "wrong_format", "wrong_version",
     "missing_version", "duplicate_xy", "bad_other_record"],
)
def test_candidate_delete_refuses_unowned_or_malformed_simplified_record(
    tmp_path, mutation,
):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    pdic = pdic_path(page)
    before_pdic = pdic.read_bytes()
    doc = json.loads(simplified.read_text("utf-8"))
    if mutation == "foreign_source_word":
        # Same (x, y) but a different manual headword: never delete this.
        doc["entries"][0]["source_word"] = "unrelated human revision"
    elif mutation == "wrong_page":
        doc["page"] = "another_page"
    elif mutation == "wrong_format":
        doc["format"] = "unrelated_data"
    elif mutation == "wrong_version":
        doc["format_version"] = 999
    elif mutation == "missing_version":
        del doc["format_version"]
    elif mutation == "duplicate_xy":
        doc["entries"].append(dict(doc["entries"][0]))
    elif mutation == "bad_other_record":
        doc["entries"][1]["y"] = "not a coordinate"
    simplified.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    old_simplified = simplified.read_bytes()

    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert pdic.read_bytes() == before_pdic
    assert simplified.read_bytes() == old_simplified
    assert not manual.exists()
    assert review.parent.entries == rows
    assert candidate["selected"] is True
    assert review.parent.candidate_check_vars["ocr-id"].get() is True
    assert not actions


@pytest.mark.parametrize(
    "prior",
    [
        {"selected": True, "word": "somebody else's word"},
        {"selected": False, "word": "head"},
        {"selected": "true", "word": "head"},
        {"word": "head"},
        "not an override record",
    ],
)
def test_candidate_delete_rejects_stale_or_unowned_manual_override(
    tmp_path, prior,
):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    pdic = pdic_path(page)
    initial = pdic.read_bytes()
    manual.write_text(
        json.dumps({
            "version": 1, "page": page.stem,
            "overrides": {"ocr-id": prior},
        }), encoding="utf-8",
    )
    existing = manual.read_bytes()
    simplified_before = simplified.read_bytes()
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert manual.read_bytes() == existing
    assert pdic.read_bytes() == initial
    assert simplified.read_bytes() == simplified_before
    assert candidate["selected"] is True
    assert review.parent.candidate_check_vars["ocr-id"].get() is True
    assert not actions


def test_candidate_delete_accepts_matching_manual_override_and_retains_other_decisions(
    tmp_path,
):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    manual.write_text(
        json.dumps({
            "version": 1, "page": page.stem,
            "overrides": {
                "ocr-id": {"selected": True, "word": "head", "engine": "review"},
                "other-id": {"selected": False, "word": "untouched", "engine": "manual"},
            },
        }), encoding="utf-8",
    )
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    result = json.loads(manual.read_text("utf-8"))["overrides"]
    assert result["other-id"] == {
        "selected": False, "word": "untouched", "engine": "manual",
    }
    assert result["ocr-id"]["selected"] is False
    assert [entry.word for entry in read_pdic(pdic_path(page))] == ["other"]
    assert not storage._marker_present(storage._recovery_path(page))


def test_candidate_delete_preserves_unmatched_simplified_text_and_metadata(
    tmp_path,
):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    doc = json.loads(simplified.read_text("utf-8"))
    # Simplified translation text is independently editable, and must not
    # equal the original source headword merely to allow a safe delete.
    doc["entries"][0]["text"] = "人工作业"
    doc["entries"][1]["text"] = "人工保留"
    doc["entries"][1]["manual"] = True
    simplified.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    result = json.loads(simplified.read_text("utf-8"))["entries"]
    assert len(result) == 1
    assert result[0]["source_word"] == "other"
    assert result[0]["text"] == "人工保留"
    assert result[0]["manual"] is True


def test_candidate_delete_allows_valid_simplified_document_without_target_row(
    tmp_path,
):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    doc = json.loads(simplified.read_text("utf-8"))
    doc["entries"] = [doc["entries"][1]]
    simplified.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    old_simplified = simplified.read_bytes()
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert simplified.read_bytes() == old_simplified
    assert [entry.word for entry in read_pdic(pdic_path(page))] == ["other"]
    assert candidate["selected"] is False
    assert not storage._marker_present(storage._recovery_path(page))


def test_owned_candidate_delete_undo_redo_preserves_preexisting_human_overrides(
    tmp_path,
):
    from picture_capture.ui.review_transaction_actions import _history

    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    other = {"selected": False, "word": "user kept", "engine": "hand-reviewed"}
    manual.write_text(
        json.dumps({
            "version": 1, "page": page.stem,
            "overrides": {
                "ocr-id": {"selected": True, "word": "head", "engine": "review"},
                "unrelated-id": other,
            },
        }, ensure_ascii=False), encoding="utf-8",
    )
    before = {
        "pdic": pdic_path(page).read_bytes(),
        "manual": manual.read_bytes(),
        "simplified": simplified.read_bytes(),
    }
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    after = {
        "pdic": pdic_path(page).read_bytes(),
        "manual": manual.read_bytes(),
        "simplified": simplified.read_bytes(),
    }
    assert before["pdic"] != after["pdic"]
    assert before["manual"] != after["manual"]
    history = _history(review)
    assert len(history.undo_stack) == 1

    review.vars = [Var(entry.word) for entry in review.parent.entries]
    assert history.undo(review) is True
    assert pdic_path(page).read_bytes() == before["pdic"]
    assert manual.read_bytes() == before["manual"]
    assert simplified.read_bytes() == before["simplified"]
    assert candidate["selected"] is True
    assert review.parent.candidate_check_vars["ocr-id"].get() is True

    review.vars = [Var(entry.word) for entry in review.parent.entries]
    assert history.redo(review) is True
    assert pdic_path(page).read_bytes() == after["pdic"]
    assert manual.read_bytes() == after["manual"]
    assert simplified.read_bytes() == after["simplified"]
    assert candidate["selected"] is False
    assert review.parent.candidate_check_vars["ocr-id"].get() is False
    assert json.loads(manual.read_text("utf-8"))["overrides"]["unrelated-id"] == other
    assert not storage._marker_present(storage._recovery_path(page))


def test_stale_simplified_provenance_must_not_change_candidate_history_or_undo(
    tmp_path,
):
    from picture_capture.ui.review_transaction_actions import _history

    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    doc = json.loads(simplified.read_text("utf-8"))
    doc["entries"][0]["source_word"] = "foreign editorial headword"
    simplified.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    before_pdic = pdic_path(page).read_bytes()
    before_simplified = simplified.read_bytes()

    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert _history(review).undo_stack == []
    assert pdic_path(page).read_bytes() == before_pdic
    assert simplified.read_bytes() == before_simplified
    assert not manual.exists()
    assert candidate["selected"] is True
    assert not actions

# #503 G1: Python's permissive JSON parser silently collapses duplicate
# keys (including unrelated human decisions) when the sidecar is rewritten.
# Such ambiguous sidecars must remain byte-identical; no UI state may change.
@pytest.mark.parametrize("mutation", [
    "manual_duplicate_root",
    "manual_duplicate_target",
    "manual_duplicate_other_human",
    "manual_nonfinite_other_human",
    "simplified_duplicate_root",
    "simplified_duplicate_target",
    "simplified_duplicate_other_human",
    "simplified_nonfinite_other_human",
])
def test_candidate_delete_quarantines_ambiguous_human_json_without_rewrite(
    tmp_path, mutation,
):
    page, rows, review, candidate, manual, simplified, actions = _case(tmp_path)
    pdic = pdic_path(page)
    original_pdic = pdic.read_bytes()
    original_simplified = simplified.read_bytes()
    if mutation.startswith("manual"):
        values = {
            "manual_duplicate_root":
                '{"version":1,"page":"synthetic","overrides":{},'
                '"overrides":{"ocr-id":{"selected":true,"word":"head"}}}',
            "manual_duplicate_target":
                '{"version":1,"page":"synthetic","overrides":{'
                '"ocr-id":{"selected":true,"selected":true,"word":"head"}}}',
            "manual_duplicate_other_human":
                '{"version":1,"page":"synthetic","overrides":{'
                '"other-id":{"selected":true,"word":"人工原值","word":"人工后值"}}}',
            "manual_nonfinite_other_human":
                '{"version":1,"page":"synthetic","overrides":{'
                '"other-id":{"selected":true,"word":"人工原值","score":NaN}}}',
        }
        manual.write_text(values[mutation], encoding="utf-8")
    else:
        raw = simplified.read_text("utf-8")
        if mutation == "simplified_duplicate_root":
            raw = raw.replace('"entries": [', '"entries": [], "entries": [', 1)
        elif mutation == "simplified_duplicate_target":
            raw = raw.replace(
                '"source_word": "head"',
                '"source_word": "head", "source_word": "head"', 1,
            )
        elif mutation == "simplified_duplicate_other_human":
            raw = raw.replace(
                '"text": "other"',
                '"text": "人工原值", "text": "人工后值"', 1,
            )
        else:
            raw = raw.replace(
                '"text": "other"', '"text": "other", "quality": NaN', 1,
            )
        simplified.write_text(raw, encoding="utf-8")
    original_manual = manual.read_bytes() if manual.exists() else None
    original_simplified = simplified.read_bytes()
    assert delete_owned_review_candidate(review, 0, rows) == "break"
    assert pdic.read_bytes() == original_pdic
    assert (manual.read_bytes() if manual.exists() else None) == original_manual
    assert simplified.read_bytes() == original_simplified
    assert review.parent.entries == rows
    assert candidate["selected"] is True
    assert review.parent.candidate_check_vars["ocr-id"].get() is True
    assert not storage._marker_present(storage._recovery_path(page))
    assert not actions
