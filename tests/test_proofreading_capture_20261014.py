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


def test_two_proven_word_edits_are_recorded_but_mixed_coordinate_changes_refused(tmp_path):
    from picture_capture.proofreading_capture import capture_saved_review_rename

    page, previous = _page(tmp_path)
    write_pdic(
        pdic_path(page),
        [Entry(word="one", x=10, y=20), Entry(word="two", x=10, y=60)],
        100, ("page", "@", "@"),
    )
    assert capture_saved_review_rename(
        project_root=tmp_path, page=page, prior_pdic_entries=previous,
    )
    journal = next(
        item for item in (tmp_path / "ProofreadingEvidence").glob("*.json")
        if item.name != "project_identity.json"
    )
    events = load_events(journal)
    assert len(events) == 2
    assert {event["before"]["word"] for event in events} == {"first", "second"}
    assert all(event["verification_status"] == "explicit_action_unverified_page"
               for event in events)
    original_journal = journal.read_bytes()
    write_pdic(
        pdic_path(page),
        [Entry(word="first", x=12, y=20), previous[1]],
        100, ("page", "@", "@"),
    )
    assert not capture_saved_review_rename(
        project_root=tmp_path, page=page, prior_pdic_entries=previous,
    )
    assert journal.read_bytes() == original_journal


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
        # ReviewWindow now publishes PDIC and simplified in one recoverable
        # bundle; the old sequential parent.save_pdic call was unsafe.
        assert snippet.index("commit_review_bundle(self, transaction_before)") < snippet.index(
            "_review_evidence_after_save(evidence_before)"
        )
    bundle = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture"
        / "proofreading_review_bundle.py"
    ).read_text(encoding="utf-8")
    assert "_stage_recovery(page, changes, rollback_required=True)" in bundle
    assert "_rollback_failed_publish(page)" in bundle
    assert "_bytes_or_absent(owned[role]) != new" in bundle
    assert "proofreading_event_capture" in review


def test_candidate_toggle_only_records_one_confirmed_pdic_and_manual_override_save(tmp_path):
    import json
    from picture_capture.proofreading_capture import capture_saved_candidate_selection

    page, original = _page(tmp_path)
    candidate = ("added", 10, 100)
    # Selecting one new candidate changes exactly one PDIC row.
    write_pdic(
        pdic_path(page),
        original + [Entry(word=candidate[0], x=candidate[1], y=candidate[2])],
        100, ("page", "@", "@"),
    )
    saved = pdic_path(page).read_bytes()
    overrides = tmp_path / "page_manual_selection.json"
    overrides.write_text(json.dumps({
        "version": 1, "page": "page",
        "overrides": {"unique-cid": {"selected": True, "word": "added", "engine": "manual_checkbox"}},
    }), encoding="utf-8")
    assert capture_saved_candidate_selection(
        project_root=tmp_path, page=page, prior_pdic_entries=original,
        expected_entry=candidate, candidate_id="unique-cid",
        selected=True, candidate_id_unique=True, manual_selection_path=overrides,
    )
    assert pdic_path(page).read_bytes() == saved
    journal = next(p for p in (tmp_path / "ProofreadingEvidence").glob("*.json") if p.name != "project_identity.json")
    rows = load_events(journal)
    assert len(rows) == 1 and rows[0]["action"] == "select"
    assert rows[0]["candidate_id"] == "unique-cid"
    assert rows[0]["verification_status"] == "explicit_action_unverified_page"
    assert rows[0]["entry_id"] is not None
    # Deselect the same candidate after saving both files.
    new_previous = read_pdic(pdic_path(page))
    write_pdic(pdic_path(page), original, 100, ("page", "@", "@"))
    overrides.write_text(json.dumps({
        "version": 1, "page": "page",
        "overrides": {"unique-cid": {"selected": False, "word": "added", "engine": "manual_checkbox"}},
    }), encoding="utf-8")
    assert capture_saved_candidate_selection(
        project_root=tmp_path, page=page, prior_pdic_entries=new_previous,
        expected_entry=candidate, candidate_id="unique-cid",
        selected=False, candidate_id_unique=True, manual_selection_path=overrides,
    )
    final = load_events(journal)
    assert [row["action"] for row in final] == ["select", "deselect"]
    assert final[0]["entry_id"] == final[1]["entry_id"]


def test_candidate_toggle_rejects_partial_or_ambiguous_commits(tmp_path):
    import json
    from picture_capture.proofreading_capture import capture_saved_candidate_selection

    page, original = _page(tmp_path)
    expected = ("added", 10, 100)
    extra = Entry(word="other-new", x=10, y=120)
    write_pdic(
        pdic_path(page),
        original + [Entry(word="added", x=10, y=100), extra],
        100, ("page", "@", "@"),
    )
    overrides = tmp_path / "page_manual_selection.json"
    overrides.write_text(json.dumps({
        "version": 1, "page": "page",
        "overrides": {"unique-cid": {"selected": True, "word": "added", "engine": "manual_checkbox"}},
    }), encoding="utf-8")
    kwargs = dict(
        project_root=tmp_path, page=page, prior_pdic_entries=original,
        expected_entry=expected, candidate_id="unique-cid",
        selected=True, candidate_id_unique=True, manual_selection_path=overrides,
    )
    assert capture_saved_candidate_selection(**kwargs) is False
    write_pdic(
        pdic_path(page),
        original + [Entry(word="added", x=10, y=100)],
        100, ("page", "@", "@"),
    )
    assert capture_saved_candidate_selection(**{**kwargs, "candidate_id_unique": False}) is False
    overrides.write_text(json.dumps({
        "version": 1, "page": "page", "overrides": {
            "unique-cid": {"selected": False, "word": "added", "engine": "manual_checkbox"},
        },
    }), encoding="utf-8")
    assert capture_saved_candidate_selection(**kwargs) is False
    assert not (tmp_path / "ProofreadingEvidence").exists()


def _pdic_save_regions():
    """Audit effective save bodies, including the extracted deferred helper."""
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (root / "app.py").read_text(encoding="utf-8")
    helper = (root / "proofreading_deferred_save.py").read_text(encoding="utf-8")
    wrapper = app[app.index("    def _flush_deferred_page_save("):]
    wrapper = wrapper[:wrapper.index("\n    def ")]
    # The GUI remains a thin call-time adapter to the same persistence API.
    assert "flush_deferred_page_save(self, write_pdic=write_pdic, pdic_path=pdic_path)" in wrapper
    regions = []
    for source, method, indentation, prefix in (
        (app, "save_pdic(", "    ", "self."),
        (helper, "flush_deferred_page_save(", "", "app."),
    ):
        start = source.index(indentation + "def " + method)
        end = source.find("\n" + indentation + "def ", start + 8)
        regions.append((source[start:end if end != -1 else None], prefix))
    return app, regions


def test_ocr_checkbox_flushes_after_both_pdic_and_override_writes():
    app, regions = _pdic_save_regions()
    for snippet, prefix in regions:
        assert snippet.index(prefix + "_flush_pending_manual_override()") < snippet.index(
            prefix + "_flush_proofreading_candidate_evidence()"
        )
    assert "self._queue_proofreading_candidate_evidence(cand, selected)" in app
    assert 'state["_pending_evidence_toggle"] = False' in app


def test_proven_single_canvas_addition_creates_unverified_local_event(tmp_path):
    from picture_capture.proofreading_capture import capture_saved_manual_addition

    page, old = _page(tmp_path)
    fresh = Entry(word="new hand entry", x=30, y=110)
    write_pdic(pdic_path(page), old + [fresh], 100, ("page", "@", "@"))
    saved_bytes = pdic_path(page).read_bytes()
    assert capture_saved_manual_addition(
        project_root=tmp_path, page=page, prior_pdic_entries=old,
        expected_xy=(30, 110),
    )
    assert pdic_path(page).read_bytes() == saved_bytes
    journal = next(
        p for p in (tmp_path / "ProofreadingEvidence").glob("*.json")
        if p.name != "project_identity.json"
    )
    e = load_events(journal)[0]
    assert e["action"] == "add" and e["candidate_id"] is None
    assert e["verification_status"] == "explicit_action_unverified_page"
    assert e["after"] == {"word": "new hand entry", "x": 30, "y": 110}
    assert e["entry_id"] is not None
    assert e["coordinate_space"] == "original_image_xy"


def test_add_evidence_rejects_multiedit_duplicate_and_wrong_clicked_location(tmp_path):
    from picture_capture.proofreading_capture import capture_saved_manual_addition

    page, old = _page(tmp_path)
    a = Entry(word="manual", x=30, y=110)
    write_pdic(pdic_path(page), old + [a], 100, ("page", "@", "@"))
    opts = dict(project_root=tmp_path, page=page, prior_pdic_entries=old)
    assert not capture_saved_manual_addition(**opts, expected_xy=(31, 110))
    write_pdic(
        pdic_path(page), old + [a, Entry(word="extra", x=20, y=120)],
        100, ("page", "@", "@"),
    )
    assert not capture_saved_manual_addition(**opts, expected_xy=(30, 110))
    write_pdic(
        pdic_path(page), old + [Entry(word="colliding", x=10, y=20)],
        100, ("page", "@", "@"),
    )
    assert not capture_saved_manual_addition(**opts, expected_xy=(10, 20))
    write_pdic(
        pdic_path(page), [old[1], a], 100, ("page", "@", "@"),
    )
    assert not capture_saved_manual_addition(**opts, expected_xy=(30, 110))
    assert not (tmp_path / "ProofreadingEvidence").exists()


def test_actual_canvas_click_is_stage_only_and_flushes_after_saved_pdic():
    app = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    click = app[app.index("    def canvas_left_click("):app.index("    def canvas_left_drag(")]
    assert click.index('queue_add(source_x, source_y)') < click.index(
        'self.entries.append(WordEntry("", source_x, source_y))'
    )
    _, regions = _pdic_save_regions()
    for part, prefix in regions:
        assert part.index("write_pdic(") < part.index(
            prefix + "_flush_proofreading_add_evidence()"
        )
    assert 'state["_pending_evidence_add"] = False' in app


def test_named_ocr_same_word_y_position_switch_is_audited_after_both_saves(tmp_path):
    import json
    from picture_capture.proofreading_capture import capture_saved_position_switch

    page, old = _page(tmp_path)
    moved_before = ("first", 10, 20)
    moved_after = ("first", 10, 24)
    write_pdic(
        pdic_path(page),
        [Entry(word="first", x=10, y=24), old[1]],
        100, ("page", "@", "@"),
    )
    overrides = tmp_path / "page_manual_selection.json"
    overrides.write_text(json.dumps({
        "page": "page", "version": 1, "overrides": {
            "old-y": {"selected": False, "word": "first", "engine": "position_switch"},
            "new-y": {"selected": True, "word": "first", "engine": "manual_checkbox"},
        },
    }), encoding="utf-8")
    kwargs = dict(
        project_root=tmp_path, page=page, prior_pdic_entries=old,
        removed_entry=moved_before, added_entry=moved_after,
        removed_candidate_id="old-y", added_candidate_id="new-y",
        position_group_id="stable-headword", manual_selection_path=overrides,
    )
    assert capture_saved_position_switch(**kwargs)
    journal = next(
        p for p in (tmp_path / "ProofreadingEvidence").glob("*.json")
        if p.name != "project_identity.json"
    )
    ev = load_events(journal)
    assert len(ev) == 1
    assert ev[0]["action"] == "move"
    assert ev[0]["before"]["y"] == 20
    assert ev[0]["after"]["y"] == 24
    assert ev[0]["entry_id"] and ev[0]["candidate_id"] == "new-y"
    assert ev[0]["verification_status"] == "explicit_action_unverified_page"


def test_position_switch_rejects_partial_manual_override_or_multiple_edits(tmp_path):
    import json
    from picture_capture.proofreading_capture import capture_saved_position_switch

    page, old = _page(tmp_path)
    before = ("first", 10, 20)
    after = ("first", 10, 24)
    write_pdic(pdic_path(page), [Entry("first", 10, 24), old[1]], 100, ("page", "@", "@"))
    overrides = tmp_path / "manual.json"
    overrides.write_text(json.dumps({"page": "page", "overrides": {
        "new-y": {"selected": True, "word": "first", "engine": "manual_checkbox"},
    }}), encoding="utf-8")
    kwargs = dict(
        project_root=tmp_path, page=page, prior_pdic_entries=old,
        removed_entry=before, added_entry=after,
        removed_candidate_id="old-y", added_candidate_id="new-y",
        position_group_id="stable", manual_selection_path=overrides,
    )
    assert not capture_saved_position_switch(**kwargs)
    overrides.write_text(json.dumps({"page": "page", "overrides": {
        "old-y": {"selected": False, "word": "first", "engine": "position_switch"},
        "new-y": {"selected": True, "word": "first", "engine": "manual_checkbox"},
    }}), encoding="utf-8")
    assert not capture_saved_position_switch(**{**kwargs, "added_entry": ("changed", 10, 24)})
    write_pdic(
        pdic_path(page),
        [Entry("first", 10, 24), Entry("also changed", 10, 60)],
        100, ("page", "@", "@"),
    )
    assert not capture_saved_position_switch(**kwargs)
    assert not (tmp_path / "ProofreadingEvidence").exists()


def test_only_verified_pre_edit_final_ocr_audit_can_annotate_candidate_lineage(tmp_path):
    import json
    from picture_capture.proofreading_capture import (
        verified_ocr_preedit_fingerprints, capture_saved_candidate_selection,
    )
    from picture_capture.ocr_final_decisions import (
        final_decisions_path, pdic_snapshot, _snapshot_digest,
    )
    from picture_capture.proofreading_evidence import link_event_to_final

    page, old = _page(tmp_path)
    cache = tmp_path / "ocr_cache.json"
    cache.write_text(json.dumps({"signature": "ocr-v1"}), encoding="utf-8")
    original_rows = pdic_snapshot(read_pdic(pdic_path(page)))
    fingerprint = _snapshot_digest(original_rows)
    final = {
        "format": "picture-capture-final-ocr-decisions-v1",
        "ocr_cache_signature": "ocr-v1",
        "pdic_snapshot_sha256": fingerprint, "pdic_rows": original_rows,
        "candidate_decisions": [
            {"candidate_id": "cid-1", "final_status": "removed_after_ocr",
             "final_selected": False},
        ],
    }
    final_decisions_path(cache).write_text(json.dumps(final), encoding="utf-8")
    source = verified_ocr_preedit_fingerprints(cache, pdic_path(page))
    assert source == ("ocr-v1", fingerprint)
    cache.write_text(json.dumps({"signature": "new-ocr"}), encoding="utf-8")
    assert verified_ocr_preedit_fingerprints(cache, pdic_path(page)) is None
    cache.write_text(json.dumps({"signature": "ocr-v1"}), encoding="utf-8")
    selected = Entry("new lemma", 30, 120)
    write_pdic(pdic_path(page), old + [selected], 100, ("page", "@", "@"))
    assert verified_ocr_preedit_fingerprints(cache, pdic_path(page)) is None
    override = tmp_path / "page_manual_selection.json"
    override.write_text(json.dumps({
        "page": "page", "overrides": {
            "cid-1": {"selected": True, "word": "new lemma",
                      "engine": "manual_checkbox"},
        }
    }), encoding="utf-8")
    assert capture_saved_candidate_selection(
        project_root=tmp_path, page=page,
        prior_pdic_entries=old, expected_entry=("new lemma", 30, 120),
        candidate_id="cid-1", selected=True, candidate_id_unique=True,
        manual_selection_path=override, source_fingerprints=source,
    )
    journal = next(
        p for p in (tmp_path / "ProofreadingEvidence").glob("*.json")
        if p.name != "project_identity.json"
    )
    event = load_events(journal)[0]
    assert event["ocr_signature"] == "ocr-v1"
    assert event["final_snapshot_sha256"] == fingerprint
    assert link_event_to_final(
        event, final, current_ocr_signature="ocr-v1",
    )["status"] == "matched"
    assert link_event_to_final(
        event, final, current_ocr_signature="ocr-v1",
    )["training_label"] is None
