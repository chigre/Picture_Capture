"""B2 #483: an explicit, operation-owned marker move, not XY guesswork."""
from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

import pytest

from picture_capture.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import AppSettings, Entry
from picture_capture.proofreading_capture import capture_saved_explicit_marker_move
from picture_capture.proofreading_events import load_events, sha256_file
from picture_capture.project_storage import data_root
from picture_capture.ui.entry_move_controller import move_entry_via_dialog


def _fixture(tmp_path):
    page = tmp_path / "page.png"
    page.write_bytes(b"synthetic-source")
    initial = [Entry("alpha", 10, 20), Entry("beta", 50, 80)]
    write_pdic(pdic_path(page), initial, 120, ("page", "@", "@"))
    return page, initial


def _evidence(root):
    folder = data_root(root) / "ProofreadingEvidence"
    journals = [p for p in folder.glob("*.json")
                if p.name != "project_identity.json"] if folder.exists() else []
    return load_events(journals[0]) if journals else []


def test_explicit_move_proves_exact_row_and_survives_reopen(tmp_path):
    page, before = _fixture(tmp_path)
    old = sha256_file(pdic_path(page))
    image = sha256_file(page)
    after = [Entry("alpha-edited", 83, 121), Entry("beta", 50, 80)]
    write_pdic(pdic_path(page), after, 120, ("page", "@", "@"))
    assert capture_saved_explicit_marker_move(
        project_root=tmp_path, page=page,
        prior_pdic_entries=before, prior_pdic_sha256=old,
        before=("alpha", 10, 20), after=("alpha-edited", 83, 121),
        prior_image_sha256=image,
    )
    recorded = _evidence(tmp_path)
    assert len(recorded) == 1
    e = recorded[0]
    assert e["action"] == "move"
    assert e["entry_id"] and e["pdic_sha256"] == sha256_file(pdic_path(page))
    assert e["prior_pdic_sha256"] == old
    assert e["verification_status"] == "explicit_action_unverified_page"

    from picture_capture.proofreading_capture import capture_saved_review_rename
    previous = read_pdic(pdic_path(page))
    digest = sha256_file(pdic_path(page))
    write_pdic(pdic_path(page),
               [Entry("alpha-final", 83, 121), Entry("beta", 50, 80)],
               120, ("page", "@", "@"))
    assert capture_saved_review_rename(
        project_root=tmp_path, page=page,
        prior_pdic_entries=previous, prior_pdic_sha256=digest,
    )
    assert _evidence(tmp_path)[-1]["entry_id"] == e["entry_id"]


@pytest.mark.parametrize("extra", ["other-rename", "other-deleted", "target-duplicate", "other-coordinate"])
def test_explicit_move_rejects_unowned_compound_edits(tmp_path, extra):
    page, before = _fixture(tmp_path)
    digest, image = sha256_file(pdic_path(page)), sha256_file(page)
    changed = [Entry("alpha", 73, 101), Entry("beta", 50, 80)]
    if extra == "other-rename":
        changed[1].word = "BETTER"
    elif extra == "other-deleted":
        changed.pop()
    elif extra == "target-duplicate":
        changed.append(Entry("third", 73, 101))
    else:
        changed[1].y = 79
    write_pdic(pdic_path(page), changed, 120, ("page", "@", "@"))
    assert not capture_saved_explicit_marker_move(
        project_root=tmp_path, page=page, prior_pdic_entries=before,
        prior_pdic_sha256=digest, before=("alpha", 10, 20),
        after=("alpha", 73, 101), prior_image_sha256=image,
    )
    assert _evidence(tmp_path) == []


def test_explicit_move_refuses_source_image_change(tmp_path):
    page, before = _fixture(tmp_path)
    digest, image = sha256_file(pdic_path(page)), sha256_file(page)
    write_pdic(pdic_path(page),
               [Entry("alpha", 73, 101), Entry("beta", 50, 80)],
               120, ("page", "@", "@"))
    page.write_bytes(b"another-source")
    assert not capture_saved_explicit_marker_move(
        project_root=tmp_path, page=page, prior_pdic_entries=before,
        prior_pdic_sha256=digest, before=("alpha", 10, 20),
        after=("alpha", 73, 101), prior_image_sha256=image,
    )
    assert not _evidence(tmp_path)


def _app(tmp_path, *, enabled=True):
    page, before = _fixture(tmp_path)
    messages = []
    app = SimpleNamespace(
        image=SimpleNamespace(size=(120, 180), width=120),
        current_page=page,
        current_index=0,
        project=SimpleNamespace(root=tmp_path),
        entries=before,
        settings=AppSettings(proofreading_event_capture=enabled),
        status_var=SimpleNamespace(set=messages.append),
        _batch_active=False,
    )
    app._claim_page_for_manual_edit = lambda: True
    app._guard_transformed_geometry = lambda _: True
    app._sync_entry_editor_texts = lambda: None
    app._sort_entries_reading_order = lambda: None
    app._get_cached_display_geometry = lambda: SimpleNamespace(
        source_to_canonical=lambda x, y: (x, y), top=0, bottom=180,
    )
    app._current_effective_profile_settings = lambda: app.settings
    app.page_sections = []
    app.redraw = lambda: None
    app.pages_tuple = lambda: ("page", "@", "@")
    def save_pdic(*, silent=False, sync_editors=False):
        write_pdic(pdic_path(page), app.entries, 120, ("page", "@", "@"))
    app.save_pdic = save_pdic
    return app, page, messages


def test_move_dialog_commits_own_entry_and_preserves_default_off(tmp_path, monkeypatch):
    app, page, messages = _app(tmp_path, enabled=False)
    import picture_capture.ui.entry_move_controller as module
    monkeypatch.setattr(module.simpledialog, "askstring", lambda *a, **k: "70, 100")
    assert move_entry_via_dialog(app, app.entries[0]) == "break"
    assert [(e.word, e.x, e.y) for e in read_pdic(pdic_path(page))] == [
        ("alpha", 70, 100), ("beta", 50, 80),
    ]
    assert _evidence(tmp_path) == []
    assert any("已移动" in str(x) for x in messages)


def test_move_dialog_rejects_uncommitted_other_edit_before_save(tmp_path, monkeypatch):
    app, page, _ = _app(tmp_path)
    app.entries[1].word = "modified-in-widget"
    import picture_capture.ui.entry_move_controller as module
    monkeypatch.setattr(module.simpledialog, "askstring", lambda *a, **k: "70,100")
    assert move_entry_via_dialog(app, app.entries[0]) == "break"
    assert [(e.word,e.x,e.y) for e in read_pdic(pdic_path(page))] == [
        ("alpha",10,20), ("beta",50,80),
    ]
    assert _evidence(tmp_path) == []


def test_move_dialog_save_failure_rolls_back_uncommitted_coordinates(tmp_path, monkeypatch):
    app, page, _ = _app(tmp_path)
    image = pdic_path(page).read_bytes()
    def crash_save(*, silent=False, sync_editors=False):
        raise OSError("disk full")
    app.save_pdic = crash_save
    import picture_capture.ui.entry_move_controller as module
    monkeypatch.setattr(module.simpledialog, "askstring", lambda *a, **k: "70,100")
    assert move_entry_via_dialog(app, app.entries[0]) == "break"
    assert (app.entries[0].x, app.entries[0].y) == (10,20)
    assert pdic_path(page).read_bytes() == image
    assert not _evidence(tmp_path)


def test_move_dialog_batch_pending_or_ocr_owned_row_not_mutated(tmp_path, monkeypatch):
    app, page, messages = _app(tmp_path)
    import picture_capture.ui.entry_move_controller as module
    monkeypatch.setattr(module.simpledialog, "askstring", lambda *a, **k: "70,100")
    app._batch_active = True
    assert move_entry_via_dialog(app, app.entries[0]) == "break"
    app._batch_active = False
    app.entries[0].candidate_id = "ocr-owned-candidate"
    assert move_entry_via_dialog(app, app.entries[0]) == "break"
    assert (app.entries[0].x, app.entries[0].y) == (10,20)
    assert not _evidence(tmp_path)


def test_move_ui_index_is_operation_owner_not_sorted_row_number():
    from pathlib import Path
    from picture_capture import app as mod
    overlay = Path(mod.__file__).with_name("ui").joinpath("entry_overlay_builder.py").read_text("utf-8")
    assert "<Button-3>" in overlay
    assert "self._move_entry_via_dialog(e)" in overlay
    assert "index" not in "self._move_entry_via_dialog(e)"


def test_move_dialog_preserves_source_when_destination_collides_or_is_invalid(tmp_path, monkeypatch):
    import picture_capture.ui.entry_move_controller as module
    app, page, messages = _app(tmp_path)
    source = pdic_path(page).read_bytes()
    for value in ("50,80", "-1,100", "300,100", "bad input"):
        monkeypatch.setattr(module.simpledialog, "askstring", lambda *a, **k: value)
        assert move_entry_via_dialog(app, app.entries[0]) == "break"
        assert (app.entries[0].x, app.entries[0].y) == (10, 20)
        assert pdic_path(page).read_bytes() == source
    assert not _evidence(tmp_path)


def test_move_dialog_refuses_section_gap(tmp_path, monkeypatch):
    from picture_capture.page_sections import PageSection
    import picture_capture.ui.entry_move_controller as module
    app, page, _ = _app(tmp_path)
    app.page_sections = [PageSection(0, 90)]
    before = pdic_path(page).read_bytes()
    monkeypatch.setattr(module.simpledialog, "askstring", lambda *a, **k: "70,100")
    assert move_entry_via_dialog(app, app.entries[0]) == "break"
    assert pdic_path(page).read_bytes() == before


def test_move_dialog_corrupt_simplified_source_fails_closed(tmp_path, monkeypatch):
    from picture_capture.project_storage import simplified_review_path_for_image
    import picture_capture.ui.entry_move_controller as module
    app, page, _ = _app(tmp_path)
    paired = simplified_review_path_for_image(page)
    paired.parent.mkdir(parents=True, exist_ok=True)
    paired.write_text("{broken json", encoding="utf-8")
    existing = pdic_path(page).read_bytes()
    monkeypatch.setattr(module.simpledialog, "askstring", lambda *a, **k: "70,100")
    assert move_entry_via_dialog(app, app.entries[0]) == "break"
    assert pdic_path(page).read_bytes() == existing
    assert paired.read_text(encoding="utf-8") == "{broken json"


def test_move_dialog_switch_page_mid_dialog_fails_closed(tmp_path, monkeypatch):
    import picture_capture.ui.entry_move_controller as module
    app, page, _ = _app(tmp_path)
    existing = pdic_path(page).read_bytes()
    def navigate(*_args, **_kwargs):
        app.current_page = tmp_path / "other.png"
        return "70,100"
    monkeypatch.setattr(module.simpledialog, "askstring", navigate)
    assert move_entry_via_dialog(app, app.entries[0]) == "break"
    assert pdic_path(page).read_bytes() == existing


def test_move_dialog_logs_opted_in_unverified_move(tmp_path, monkeypatch):
    import picture_capture.ui.entry_move_controller as module
    app, page, messages = _app(tmp_path)
    monkeypatch.setattr(module.simpledialog, "askstring", lambda *a, **k: "70,100")
    assert move_entry_via_dialog(app, app.entries[0]) == "break"
    saved = _evidence(tmp_path)
    assert len(saved) == 1
    assert saved[0]["action"] == "move"
    assert saved[0]["verification_status"] == "explicit_action_unverified_page"


def test_move_dialog_report_journal_error_without_falsely_reporting_success(tmp_path, monkeypatch):
    from picture_capture import proofreading_capture
    import picture_capture.ui.entry_move_controller as module
    app, page, messages = _app(tmp_path)
    monkeypatch.setattr(module.simpledialog, "askstring", lambda *a, **k: "70,100")
    def error_after_pdic(*_args, **_kwargs):
        raise OSError("simulated write interruption")
    monkeypatch.setattr(proofreading_capture, "capture_saved_explicit_marker_move", error_after_pdic)
    assert move_entry_via_dialog(app, app.entries[0]) == "break"
    assert (read_pdic(pdic_path(page))[0].x, read_pdic(pdic_path(page))[0].y) == (70,100)
    assert "证据写入失败" in messages[-1]
    assert not _evidence(tmp_path)
