"""G1 regression: one candidate choice/position-switch must never publish only one side.

Synthetic page, no dictionary scan. Fail-first matrix for manual_selection,
PDIC, sibling ownership and deferred Tk state.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from picture_capture.io.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.ui import review_selection_workflow as selection


class V:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _scene(tmp_path):
    page = tmp_path / "page.png"
    page.write_bytes(b"synthetic image only")
    manual = tmp_path / "page_manual_selection.json"
    old = Entry("original", 10, 20, candidate_id="refined")
    write_pdic(pdic_path(page), [old], 100, ("page", "@", "@"))
    refined = {
        "candidate_id": "refined", "word": "original",
        "source_x": 10, "source_y": 20, "selected": True,
        "position_group_id": "g", "position_variant": "refined",
        "final_engine": "paddle",
    }
    original = {
        "candidate_id": "original", "word": "original",
        "source_x": 10, "source_y": 35, "selected": False,
        "position_group_id": "g", "position_variant": "original",
        "final_engine": "paddle",
    }
    messages = []
    app = SimpleNamespace(
        current_page=page, project=SimpleNamespace(root=tmp_path, images=[page]),
        image=SimpleNamespace(width=100), entries=[old],
        current_index=0, settings=SimpleNamespace(proofreading_event_capture=False),
        ocr_review_candidates=[refined, original],
        candidate_check_vars={"refined": V(True), "original": V(False)},
        entry_editor_bindings=[],
        _pending_manual_override_path=None, _pending_manual_override_payload=None,
        _deferred_save_snapshot=None, _deferred_save_page=None, _deferred_save_job=None,
        status_var=SimpleNamespace(set=messages.append),
    )
    deps = SimpleNamespace(WordEntry=Entry, json=json, pdic_path=pdic_path)
    app._manual_selection_path = lambda: manual
    app._read_manual_overrides = lambda: selection._read_manual_overrides(app, deps)
    app._flush_pending_manual_override = lambda: selection._flush_pending_manual_override(app, deps)
    app._write_manual_override = lambda *args, **kwargs: selection._write_manual_override(app, deps, *args, **kwargs)
    app._claim_page_for_manual_edit = lambda: True
    app._entry_for_candidate = lambda candidate: next(
        (entry for entry in app.entries
         if entry.candidate_id == candidate.get("candidate_id")), None
    )
    app._sync_entry_editor_texts = lambda: None
    app._queue_proofreading_candidate_evidence = lambda *args: None
    app._sort_entries_reading_order = lambda: app.entries.sort(key=lambda e: e.y)
    app._update_entry_overlays_local = lambda **kwargs: None
    app._schedule_deferred_page_save = lambda **kwargs: None
    app.redraw = lambda: None
    app.pages_tuple = lambda: ("page", "@", "@")
    return app, deps, page, manual, refined, original, messages


def _snapshot(app, manual):
    return (
        tuple((id(e), e.word, e.x, e.y, e.candidate_id) for e in app.entries),
        tuple((id(c), c["candidate_id"], c["selected"]) for c in app.ocr_review_candidates),
        tuple((k, v.get()) for k, v in sorted(app.candidate_check_vars.items())),
        manual.read_bytes() if manual.exists() else None,
    )


@pytest.mark.parametrize("bad_field, bad_value", [
    ("confidence", "not-a-number"),
    ("y", "bad-y"),
    ("score", "not-a-score"),
])
def test_choice_invalid_numeric_never_publishes_manual_or_changes_model(
    tmp_path, bad_field, bad_value,
):
    app, deps, page, manual, refined, _, messages = _scene(tmp_path)
    refined["paddle"] = {bad_field: bad_value}
    before = _snapshot(app, manual)
    before_pdic = pdic_path(page).read_bytes()
    # The input is untrusted OCR data. The UI must reject before publishing
    # an irreversible manual override.
    selection.apply_candidate_choice(app, deps, refined, "paddle", "chosen")
    assert _snapshot(app, manual) == before
    assert pdic_path(page).read_bytes() == before_pdic
    assert app._pending_manual_override_payload is None
    assert messages and any("未" in m for m in messages)


def test_choice_pdic_disk_full_does_not_leave_durable_manual_only(tmp_path):
    app, deps, page, manual, refined, _, messages = _scene(tmp_path)
    previous = _snapshot(app, manual)
    disk = pdic_path(page).read_bytes()
    def disk_full(**_kwargs):
        raise OSError("injected disk full before PDIC")
    app.save_pdic = disk_full
    selection.apply_candidate_choice(app, deps, refined, "paddle", "chosen")
    assert pdic_path(page).read_bytes() == disk
    assert _snapshot(app, manual) == previous
    assert app._pending_manual_override_payload is None
    assert messages and "保存" in messages[-1]


def test_choice_success_preserves_shared_candidate_identity_and_saves_both(tmp_path):
    app, deps, page, manual, refined, _, messages = _scene(tmp_path)
    def persist(**_kwargs):
        write_pdic(pdic_path(page), app.entries, 100, app.pages_tuple())
        app._flush_pending_manual_override()
    app.save_pdic = persist
    same_candidate = refined
    selection.apply_candidate_choice(app, deps, refined, "paddle", "chosen")
    assert refined is same_candidate and refined["word"] == "chosen"
    assert [e.word for e in read_pdic(pdic_path(page))] == ["chosen"]
    doc = json.loads(manual.read_text("utf-8"))
    assert doc["overrides"]["refined"]["word"] == "chosen"
    assert app._pending_manual_override_payload is None
    assert len(app.entries) == 1 and app.entries[0].candidate_id == "refined"


def test_position_switch_target_stage_failure_does_not_deselect_sibling(tmp_path):
    app, deps, page, manual, refined, original, messages = _scene(tmp_path)
    before = _snapshot(app, manual)
    previous_writer = app._write_manual_override
    def fail_target(candidate, **kwargs):
        if candidate is original:
            raise OSError("injected target staging failure")
        return previous_writer(candidate, **kwargs)
    app._write_manual_override = fail_target
    result = selection.set_candidate_selected(app, deps, original, True)
    assert result is False
    assert _snapshot(app, manual) == before
    assert app._pending_manual_override_payload is None
    assert app._pending_manual_override_path is None
    assert messages and "候选" in messages[-1]


def test_position_switch_foreign_manual_edit_between_stages_keeps_human_bytes(tmp_path):
    app, deps, page, manual, refined, original, messages = _scene(tmp_path)
    before = _snapshot(app, manual)
    writer = app._write_manual_override
    foreign = b'{"version":1,"page":"page","overrides":{"human":{"selected":true,"word":"human"}}}'
    def inject_foreign(candidate, **kwargs):
        result = writer(candidate, **kwargs)
        if candidate is refined:
            manual.write_bytes(foreign)
        return result
    app._write_manual_override = inject_foreign
    result = selection.set_candidate_selected(app, deps, original, True)
    assert result is False
    assert _snapshot(app, manual)[:3] == before[:3]
    assert manual.read_bytes() == foreign
    assert app._pending_manual_override_payload is None
    assert messages


def test_position_switch_success_stages_both_decisions_before_model_change(tmp_path):
    app, deps, page, manual, refined, original, messages = _scene(tmp_path)
    result = selection.set_candidate_selected(app, deps, original, True)
    assert result is True
    assert refined["selected"] is False and original["selected"] is True
    assert [(row.candidate_id, row.y) for row in app.entries] == [("original", 35)]
    staged = app._pending_manual_override_payload["overrides"]
    assert staged["refined"]["selected"] is False
    assert staged["original"]["selected"] is True
    assert not manual.exists()
    app._flush_pending_manual_override()
    assert json.loads(manual.read_text("utf-8"))["overrides"] == staged


def test_position_switch_failed_deferred_scheduling_restores_memory_and_pending(tmp_path):
    app, deps, page, manual, _, original, messages = _scene(tmp_path)
    before = _snapshot(app, manual)
    def reject(**_kwargs):
        raise RuntimeError("injected scheduler refusal")
    app._schedule_deferred_page_save = reject
    assert selection.set_candidate_selected(app, deps, original, True) is False
    assert _snapshot(app, manual) == before
    assert app._pending_manual_override_payload is None
    assert messages and "候选" in messages[-1]

def test_position_switch_never_adopts_nearby_sibling_entry_without_candidate_id(tmp_path):
    app, deps, page, manual, refined, original, messages = _scene(tmp_path)
    former = app.entries[0]
    # The old read-side OCR lookup can map a nearby Y to the wrong Entry.
    # Destructive selection must never call that approximate lookup.
    app._entry_for_candidate = lambda candidate: former
    assert selection.set_candidate_selected(app, deps, original, True) is True
    assert former not in app.entries
    assert len(app.entries) == 1 and app.entries[0].candidate_id == "original"
    assert app.entries[0].y == 35
    assert app.candidate_check_vars["refined"].get() is False


def test_new_choice_refuses_foreign_entry_at_identical_source_pixels(tmp_path):
    app, deps, page, manual, refined, original, messages = _scene(tmp_path)
    original["source_y"] = 20
    before = _snapshot(app, manual)
    selection.apply_candidate_choice(app, deps, original, "paddle", "foreign choice")
    assert _snapshot(app, manual) == before
    assert messages and "坐标" in messages[-1]
