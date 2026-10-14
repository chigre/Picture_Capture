"""B2 post-save opt-in deletion evidence and legacy settings integration."""
from __future__ import annotations

import json
from pathlib import Path

from picture_capture.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import AppSettings, Entry
from picture_capture.proofreading_capture import (
    capture_saved_review_deletion, _project_identity,
)
from picture_capture.proofreading_events import load_events
from picture_capture.ui.settings import schema


def _page(tmp_path, *, names=("first", "second")):
    page = tmp_path / "page.png"
    page.write_bytes(b"not a scan")
    old = [
        Entry(word=name, x=10, y=i * 40 + 20)
        for i, name in enumerate(names)
    ]
    original = pdic_path(page)
    write_pdic(original, old, 100, ("page", "@", "@"))
    return page, old


def test_proofreading_capture_off_by_default_and_visible_opt_in(tmp_path):
    assert AppSettings().proofreading_event_capture is False
    assert ("记录本地校对操作证据（默认关）", "proofreading_event_capture") in (
        next(items for group, items in schema.CHECK_GROUPS if group == "校对时主界面")
    )
    assert "默认关闭" in schema.CHECK_HELP["proofreading_event_capture"]
    settings_file = tmp_path / "settings.json"
    AppSettings(proofreading_event_capture=True).to_json(settings_file)
    assert AppSettings.from_json(settings_file).proofreading_event_capture is True
    raw = json.loads(settings_file.read_text(encoding="utf-8"))
    raw.pop("proofreading_event_capture", None)
    settings_file.write_text(json.dumps(raw), encoding="utf-8")
    assert AppSettings.from_json(settings_file).proofreading_event_capture is False


def test_post_save_deletion_is_captured_without_rewriting_user_pdic(tmp_path):
    page, old = _page(tmp_path)
    write_pdic(pdic_path(page), old[:1], 100, ("page", "@", "@"))
    saved = pdic_path(page).read_bytes()
    assert capture_saved_review_deletion(
        project_root=tmp_path, page=page, prior_pdic_entries=old,
        expected_deleted=("second", 10, 60),
        deleted_candidate_id="candidate-second", candidate_id_unique=True,
    )
    assert pdic_path(page).read_bytes() == saved
    directory = tmp_path / "ProofreadingEvidence"
    journals = [p for p in directory.glob("*.json") if p.name != "project_identity.json"]
    assert len(journals) == 1
    events = load_events(journals[0])
    assert len(events) == 1
    assert events[0]["action"] == "delete"
    assert events[0]["verification_status"] == "explicit_action_unverified_page"
    assert events[0]["before"] == {"word": "second", "x": 10, "y": 60}
    assert events[0]["candidate_id"] == "candidate-second"
    assert events[0]["entry_id"] is not None
    assert events[0]["page_id"].startswith(_project_identity(tmp_path) + "/")
    assert events[0]["after"] is None


def test_reordered_or_renamed_concurrent_edits_are_not_fabricated_as_deletion(tmp_path):
    page, before = _page(tmp_path)
    write_pdic(pdic_path(page), [Entry(word="renamed", x=10, y=20)], 100, ("page", "@", "@"))
    assert capture_saved_review_deletion(
        project_root=tmp_path, page=page, prior_pdic_entries=before,
        expected_deleted=("second", 10, 60),
        deleted_candidate_id="candidate-second", candidate_id_unique=True,
    ) is False
    assert not (tmp_path / "ProofreadingEvidence").exists()


def test_same_coordinate_duplicate_does_not_claim_identity(tmp_path):
    page, before = _page(tmp_path, names=("duplicate", "duplicate"))
    before[1].y = 20
    write_pdic(pdic_path(page), before, 100, ("page", "@", "@"))
    write_pdic(pdic_path(page), before[:1], 100, ("page", "@", "@"))
    assert capture_saved_review_deletion(
        project_root=tmp_path, page=page, prior_pdic_entries=before,
        expected_deleted=("duplicate", 10, 20),
        deleted_candidate_id="ambiguous", candidate_id_unique=False,
    ) is False
    assert not (tmp_path / "ProofreadingEvidence").exists()


def test_unlinked_deletion_keeps_unknown_stable_identity(tmp_path):
    page, before = _page(tmp_path)
    write_pdic(pdic_path(page), before[:1], 100, ("page", "@", "@"))
    assert capture_saved_review_deletion(
        project_root=tmp_path, page=page, prior_pdic_entries=before,
        expected_deleted=("second", 10, 60),
        deleted_candidate_id="duplicated-candidate", candidate_id_unique=False,
    )
    journal = next(p for p in (tmp_path / "ProofreadingEvidence").glob("*.json") if p.name != "project_identity.json")
    event = load_events(journal)[0]
    assert event["entry_id"] is None and event["candidate_id"] is None


def test_review_delete_only_attempts_capture_after_successful_save():
    code = (Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = code.index("    def delete_review_entry(self, index:")
    end = code.index("    def _save_digit_map(", start)
    block = code[start:end]
    assert block.index("self.parent.save_pdic(silent=True, sync_editors=False)") < block.index(
        "capture_saved_review_deletion("
    )
    assert "proofreading_event_capture" in block
    assert "capture_failed = True" in block


def test_single_saved_rename_is_recorded_after_pdic_commit_without_touching_bytes(tmp_path):
    from picture_capture.proofreading_capture import capture_saved_review_rename

    page, old = _page(tmp_path)
    updated = [Entry(word="FIRST EDITED", x=10, y=20), old[1]]
    write_pdic(pdic_path(page), updated, 100, ("page", "@", "@"))
    after_bytes = pdic_path(page).read_bytes()
    assert capture_saved_review_rename(
        project_root=tmp_path, page=page, prior_pdic_entries=old,
    )
    assert pdic_path(page).read_bytes() == after_bytes
    journal = next(
        p for p in (tmp_path / "ProofreadingEvidence").glob("*.json")
        if p.name != "project_identity.json"
    )
    saved = load_events(journal)
    assert len(saved) == 1
    assert saved[0]["action"] == "rename"
    assert saved[0]["before"]["word"] == "first"
    assert saved[0]["after"]["word"] == "FIRST EDITED"
    assert saved[0]["verification_status"] == "explicit_action_unverified_page"
    assert saved[0]["candidate_id"] is None
    assert saved[0]["entry_id"] is not None
    # The next unchanged save does not manufacture a duplicate action.
    assert capture_saved_review_rename(
        project_root=tmp_path, page=page,
        prior_pdic_entries=read_pdic(pdic_path(page)),
    ) is False
    assert len(load_events(journal)) == 1


def test_rename_identity_is_stable_across_session_reopen_and_row_reorder(tmp_path):
    from picture_capture.proofreading_capture import capture_saved_review_rename

    page, previous = _page(tmp_path)
    first = Entry(word="first edit", x=10, y=20)
    write_pdic(pdic_path(page), [previous[1], first], 100, ("page", "@", "@"))
    assert capture_saved_review_rename(
        project_root=tmp_path, page=page, prior_pdic_entries=previous,
    )
    journal = next(
        p for p in (tmp_path / "ProofreadingEvidence").glob("*.json")
        if p.name != "project_identity.json"
    )
    stable_id = load_events(journal)[0]["entry_id"]
    reopened = read_pdic(pdic_path(page))
    write_pdic(
        pdic_path(page),
        [Entry(word="second edit", x=10, y=20), previous[1]],
        100, ("page", "@", "@"),
    )
    assert capture_saved_review_rename(
        project_root=tmp_path, page=page, prior_pdic_entries=reopened,
    )
    events = load_events(journal)
    assert [e["entry_id"] for e in events] == [stable_id, stable_id]


def test_coedited_words_or_changed_xy_never_guessed_as_rename(tmp_path):
    from picture_capture.proofreading_capture import capture_saved_review_rename

    page, previous = _page(tmp_path)
    write_pdic(
        pdic_path(page),
        [Entry(word="one", x=10, y=20), Entry(word="two", x=10, y=60)],
        100, ("page", "@", "@"),
    )
    assert not capture_saved_review_rename(
        project_root=tmp_path, page=page, prior_pdic_entries=previous,
    )
    assert not (tmp_path / "ProofreadingEvidence").exists()
    write_pdic(
        pdic_path(page),
        [Entry(word="first", x=12, y=20), previous[1]],
        100, ("page", "@", "@"),
    )
    assert not capture_saved_review_rename(
        project_root=tmp_path, page=page, prior_pdic_entries=previous,
    )


def test_review_rename_capture_hooks_follow_both_save_paths():
    app = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    review = app.split("class ReviewWindow(", 1)[1].split("class PictureCaptureApp(", 1)[0]
    for name in ("save(self, *, redraw_main: bool = True)", "autosave_commit(self)"):
        begin = review.index("    def " + name)
        end = review.find("\n    def ", begin + 8)
        snippet = review[begin:end if end != -1 else None]
        assert snippet.index("_review_evidence_before_save()") < snippet.index(
            "self._commit_edits()"
        )
        assert snippet.index("self.parent.save_pdic(") < snippet.index(
            "_review_evidence_after_save(evidence_before)"
        )
    assert "proofreading_event_capture" in review
