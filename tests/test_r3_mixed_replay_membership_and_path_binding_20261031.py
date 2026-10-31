"""B3/R3 red-first: provenance rebinding + mixed replay's old Tk row identity.

All tests use temporary synthetic PNG placeholder bytes and disposable PDIC.
No native-human E3, private scans, or inferred candidate identity.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.io.formats import pdic_path, write_pdic
from picture_capture.models import Entry
from picture_capture.persistence.project_storage import (
    page_sections_read_path_for_image, profile_path,
)
from picture_capture.proofreading import transactions as tx
from picture_capture.proofreading.candidate_delete import commit_candidate_delete
from picture_capture.proofreading.candidate_history import CandidateReviewHistory


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class BrokenTkVar(Var):
    def set(self, value):
        raise RuntimeError("PRIVATE_PATIENT_PATH destroyed Tk variable")


def fixture(tmp_path: Path, *, candidate: bool = False):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic pixel placeholder only")
    head = Entry("head", 10, 20, candidate_id="owned-ocr" if candidate else None)
    tail = Entry("tail", 30, 40)
    rows = [head, tail]
    write_pdic(pdic_path(page), rows, 200, ("synthetic", "@", "@"))
    ocr_dir = tmp_path / "QT" / "PaddleOCR"
    ocr_dir.mkdir(parents=True)
    bindings = {
        "manual": ocr_dir / "synthetic_manual_selection.json",
        "ocr": ocr_dir / "synthetic_ocr.json",
    }
    bindings["ocr"].write_bytes(b'{"synthetic_ocr": true}')
    section = page_sections_read_path_for_image(page)
    section.parent.mkdir(parents=True, exist_ok=True)
    section.write_bytes(b'{"synthetic_section": true}')
    prof = profile_path(tmp_path)
    prof.parent.mkdir(parents=True, exist_ok=True)
    prof.write_bytes(b'{"synthetic_profile": 3}')
    record = {"candidate_id": "owned-ocr", "word": "head", "selected": True} if candidate else None
    app = SimpleNamespace(
        current_page=page,
        project=SimpleNamespace(root=tmp_path),
        entries=rows, current_index=0,
        settings=SimpleNamespace(proofreading_event_capture=False),
        _batch_active=False, _pending_manual_override_payload=None,
        ocr_review_candidates=[record] if record is not None else [],
        candidate_check_vars={"owned-ocr": Var(True)} if candidate else {},
        _manual_selection_path=lambda: bindings["manual"],
        _paddle_cache_path=lambda: bindings["ocr"],
        _last_pdic_write_changed=False,
        _refresh_word_fill_check_from_line_count=lambda *a, **k: None,
        _update_page_row=lambda *a, **k: None,
    )
    review = SimpleNamespace(
        parent=app, _filter_rows_active=False,
        _rendered_page_stem=page.stem,
        _simplified_dirty_pages=set(),
        _simplified_page_cache={},
        vars=[Var("head"), Var("tail")],
    )
    review._bound_row_entries = lambda: app.entries
    before = tx.snapshot_review(review)
    assert before is not None
    if candidate:
        plan = commit_candidate_delete(before, head, record)
        assert plan is not None
        record["selected"] = False
        app.candidate_check_vars["owned-ocr"].set(False)
    else:
        plan = None
    app.entries[:] = [tail]
    write_pdic(pdic_path(page), app.entries, 200, ("synthetic", "@", "@")) if not candidate else None
    review.vars = [Var("tail")]
    after = tx.snapshot_review(review)
    assert after is not None
    hist = CandidateReviewHistory()
    if candidate:
        assert hist.record_candidate_delete(before, after, record, True, plan)
    else:
        assert hist.record(before, after)
    return SimpleNamespace(
        page=page, app=app, review=review, head=head, tail=tail,
        candidate=record, history=hist, before=before, after=after,
        bindings=bindings, section=section, profile=prof,
    )


@pytest.mark.parametrize("candidate", (False, True))
@pytest.mark.parametrize("direction", ("undo", "redo"))
def test_membership_replay_updates_only_originally_bound_tk_vars(
    tmp_path, candidate, direction,
):
    case = fixture(tmp_path, candidate=candidate)
    if direction == "redo":
        assert case.history.undo(case.review)
        case.review.vars = [Var("head"), Var("tail")]
    old_entries = list(case.app.entries)
    old_vars = list(case.review.vars)
    frozen_var_values = {id(entry): var.get()
                         for entry, var in zip(old_entries, old_vars)}
    assert (case.history.undo(case.review) if direction == "undo"
            else case.history.redo(case.review))
    # A newly restored Entry never hijacks the old surviving row's StringVar,
    # and a deleted Entry's widget never gets the surviving Entry's text.
    for row, variable in zip(old_entries, old_vars):
        if row is case.tail:
            assert variable.get() == "tail"
        else:
            assert variable.get() == frozen_var_values[id(row)]
    assert [entry.word for entry in case.app.entries] == (
        ["head", "tail"] if direction == "undo" else ["tail"]
    )
    assert pdic_path(case.page).read_bytes() == (
        case.before.pdic_bytes if direction == "undo"
        else case.after.pdic_bytes
    )


@pytest.mark.parametrize("candidate", (False, True))
@pytest.mark.parametrize("direction", ("undo", "redo"))
def test_presentation_var_failure_after_durable_replay_does_not_escape_or_lose_frame(
    tmp_path, capsys, candidate, direction,
):
    case = fixture(tmp_path, candidate=candidate)
    if direction == "redo":
        assert case.history.undo(case.review)
        case.review.vars = [Var("head"), BrokenTkVar("tail")]
    else:
        case.review.vars = [BrokenTkVar("tail")]
    expected = case.before if direction == "undo" else case.after
    assert (case.history.undo(case.review) if direction == "undo"
            else case.history.redo(case.review)) is True
    assert pdic_path(case.page).read_bytes() == expected.pdic_bytes
    assert [e.word for e in case.app.entries] == (
        ["head", "tail"] if direction == "undo" else ["tail"]
    )
    assert len(case.history.redo_stack if direction == "undo"
               else case.history.undo_stack) == 1
    assert len(case.history.undo_stack if direction == "undo"
               else case.history.redo_stack) == 0
    assert case.review.__dict__.get("_r3_simplified_capture_blocked") is True
    assert "PRIVATE_PATIENT_PATH" not in repr(capsys.readouterr())


@pytest.mark.parametrize("candidate", (False, True))
@pytest.mark.parametrize("direction", ("undo", "redo"))
@pytest.mark.parametrize("binding", ("manual", "ocr", "section", "profile"))
def test_snapshot_unavailable_and_source_path_rebound_quarantines_history(
    tmp_path, monkeypatch, candidate, direction, binding,
):
    case = fixture(tmp_path, candidate=candidate)
    if direction == "redo":
        assert case.history.undo(case.review)
        case.review.vars = [Var("head"), Var("tail")]
    original_pdic = pdic_path(case.page).read_bytes()
    original_rows = tuple(case.app.entries)
    original_candidate = dict(case.candidate) if candidate else None

    if binding in ("manual", "ocr"):
        source = case.bindings[binding]
        rebinding = source.with_name("foreign-" + source.name)
        if source.exists():
            rebinding.write_bytes(source.read_bytes())
        case.bindings[binding] = rebinding
    elif binding == "section":
        source = case.section
        rebinding = source.with_name("foreign-" + source.name)
        rebinding.write_bytes(source.read_bytes())
        monkeypatch.setattr(tx, "page_sections_read_path_for_image",
                            lambda _p: rebinding)
    else:
        new_root = tmp_path / "foreign_project"
        new_profile = profile_path(new_root)
        new_profile.parent.mkdir(parents=True, exist_ok=True)
        new_profile.write_bytes(case.profile.read_bytes())
        case.app.project.root = new_root

    # The live Tk rows are temporarily unavailable and a same-byte path
    # rebind must NOT be interpreted as verified unchanged provenance.
    monkeypatch.setattr(tx, "snapshot_review", lambda *_a, **_k: None)
    assert (case.history.undo(case.review) if direction == "undo"
            else case.history.redo(case.review)) is False
    assert not case.history.undo_stack and not case.history.redo_stack
    assert case.history._candidate_frames == {}
    assert tuple(case.app.entries) == original_rows
    assert (dict(case.candidate) if candidate else None) == original_candidate
    assert pdic_path(case.page).read_bytes() == original_pdic


@pytest.mark.parametrize("candidate", (False, True))
@pytest.mark.parametrize("direction", ("undo", "redo"))
def test_snapshot_unavailable_with_all_original_bindings_retains_retry(
    tmp_path, monkeypatch, candidate, direction,
):
    case = fixture(tmp_path, candidate=candidate)
    if direction == "redo":
        assert case.history.undo(case.review)
        case.review.vars = [Var("head"), Var("tail")]
    original_pdic = pdic_path(case.page).read_bytes()
    monkeypatch.setattr(tx, "snapshot_review", lambda *_a, **_k: None)
    assert (case.history.undo(case.review) if direction == "undo"
            else case.history.redo(case.review)) is False
    assert len(case.history.redo_stack if direction == "redo"
               else case.history.undo_stack) == 1
    assert pdic_path(case.page).read_bytes() == original_pdic
