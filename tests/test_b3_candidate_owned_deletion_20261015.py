"""R3 candidate-linked delete: no disk/UI split, exact Entry ownership, no scans."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.project_storage import simplified_review_path_for_image
from picture_capture.proofreading_candidate_delete import (
    commit_candidate_delete, prepare_candidate_delete,
)
from picture_capture.proofreading_transactions import snapshot_review
from picture_capture import proofreading_transactions as storage
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
