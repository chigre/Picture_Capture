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


class BrokenGetVar(Var):
    def get(self):
        raise RuntimeError("PRIVATE_PATIENT_PATH destroyed Tk getter")


@pytest.mark.parametrize("candidate", (False, True))
@pytest.mark.parametrize("direction", ("undo", "redo"))
@pytest.mark.parametrize("broken", ("var_get", "row_bind"))
def test_destroyed_tk_reader_refuses_replay_before_persisting(
    tmp_path, monkeypatch, capsys, candidate, direction, broken,
):
    case = fixture(tmp_path, candidate=candidate)
    if direction == "redo":
        assert case.history.undo(case.review)
        case.review.vars = [Var("head"), Var("tail")]
    expected = case.after if direction == "undo" else case.before
    # Isolate the after-snapshot presentation preflight: source was already
    # captured and has no change. Tk destruction must still veto the replay.
    monkeypatch.setattr(tx, "snapshot_review", lambda *_a, **_kw: expected)
    if broken == "var_get":
        case.review.vars[-1] = BrokenGetVar("tail")
    else:
        def broken_bound():
            raise RuntimeError("PRIVATE_PATIENT_PATH destroyed row bindings")
        case.review._bound_row_entries = broken_bound
    before_pdic = pdic_path(case.page).read_bytes()
    before_rows = tuple(case.app.entries)
    before_candidate = dict(case.candidate) if candidate else None

    assert (case.history.undo(case.review) if direction == "undo"
            else case.history.redo(case.review)) is False
    assert pdic_path(case.page).read_bytes() == before_pdic
    assert tuple(case.app.entries) == before_rows
    assert (dict(case.candidate) if candidate else None) == before_candidate
    assert len(case.history.undo_stack if direction == "undo"
               else case.history.redo_stack) == 1
    assert "PRIVATE_PATIENT_PATH" not in repr(capsys.readouterr())


@pytest.mark.parametrize("order", ("candidate_then_plain", "plain_then_candidate"))
def test_mixed_saved_text_and_candidate_delete_history_replays_in_exact_sequence(
    tmp_path, order,
):
    """Two genuinely committed different owners, four exact ordered replays."""
    case = fixture(tmp_path, candidate=True)
    hist = case.history
    original_pdic = case.before.pdic_bytes
    selected_manual = case.after.manual_bytes
    if order == "plain_then_candidate":
        # Re-establish original authoritative source and abandon old redo
        # through an actual new saved text commit.
        assert hist.undo(case.review)
        case.review.vars = [Var("head"), Var("tail")]
        plain_before = tx.snapshot_review(case.review)
        assert plain_before is not None
        case.tail.word = "TAIL"
        case.review.vars[1].set("TAIL")
        write_pdic(pdic_path(case.page), case.app.entries, 200, ("synthetic", "@", "@"))
        plain_after = tx.snapshot_review(case.review)
        assert plain_after is not None and hist.record(plain_before, plain_after)
        original_pdic = plain_before.pdic_bytes
        # The exact candidate still owns its own unchanged original head.
        plan = commit_candidate_delete(plain_after, case.head, case.candidate)
        assert plan is not None
        case.candidate["selected"] = False
        case.app.candidate_check_vars["owned-ocr"].set(False)
        case.app.entries[:] = [case.tail]
        case.review.vars = [Var("TAIL")]
        candidate_after = tx.snapshot_review(case.review)
        assert candidate_after is not None
        assert hist.record_candidate_delete(
            plain_after, candidate_after, case.candidate, True, plan,
        )
        final_pdic = candidate_after.pdic_bytes
        final_manual = candidate_after.manual_bytes
        assert hist.undo(case.review)  # candidate deletion
        case.review.vars = [Var("head"), Var("TAIL")]
        assert hist.undo(case.review)  # ordinary text save
        assert pdic_path(case.page).read_bytes() == original_pdic
        assert [e.word for e in case.app.entries] == ["head", "tail"]
        case.review.vars = [Var("head"), Var("tail")]
        assert hist.redo(case.review)  # ordinary text save
        case.review.vars = [Var("head"), Var("TAIL")]
        assert hist.redo(case.review)  # candidate deletion
    else:
        # The candidate has already been durably deleted; now edit only the
        # surviving unlinked ordinary row, then Undo/Redo both frames.
        ordinary_before = tx.snapshot_review(case.review)
        assert ordinary_before is not None
        case.tail.word = "TAIL"
        case.review.vars[0].set("TAIL")
        write_pdic(pdic_path(case.page), case.app.entries, 200, ("synthetic", "@", "@"))
        ordinary_after = tx.snapshot_review(case.review)
        assert ordinary_after is not None
        assert hist.record(ordinary_before, ordinary_after)
        final_pdic = ordinary_after.pdic_bytes
        final_manual = case.after.manual_bytes
        assert hist.undo(case.review)  # ordinary edit
        case.review.vars = [Var("tail")]
        assert hist.undo(case.review)  # candidate deletion
        assert pdic_path(case.page).read_bytes() == original_pdic
        assert [e.word for e in case.app.entries] == ["head", "tail"]
        case.review.vars = [Var("head"), Var("tail")]
        assert hist.redo(case.review)  # candidate deletion
        case.review.vars = [Var("tail")]
        assert hist.redo(case.review)  # ordinary edit

    assert pdic_path(case.page).read_bytes() == final_pdic
    assert [e.word for e in case.app.entries] == ["TAIL"]
    assert case.candidate["selected"] is False
    assert case.bindings["manual"].read_bytes() == final_manual
    assert len(hist.undo_stack) == 2 and not hist.redo_stack
    assert len(hist._candidate_frames) == 1


@pytest.mark.parametrize("candidate", (False, True))
@pytest.mark.parametrize("direction", ("undo", "redo"))
@pytest.mark.parametrize("exception", ("runtime", "tcl"))
def test_real_snapshot_destroyed_tk_row_reader_fails_closed_without_traceback(
    tmp_path, capsys, candidate, direction, exception,
):
    """Use the actual snapshot_review rather than mocking its return."""
    from tkinter import TclError

    case = fixture(tmp_path, candidate=candidate)
    if direction == "redo":
        assert case.history.undo(case.review)
        case.review.vars = [Var("head"), Var("tail")]
    before_pdic = pdic_path(case.page).read_bytes()
    original_rows = tuple(case.app.entries)
    before_candidate = dict(case.candidate) if candidate else None

    def dead_tk_row_reader():
        message = "PRIVATE_DESTROYED_REVIEW_C:/source/patient.dic"
        if exception == "runtime":
            raise RuntimeError(message)
        raise TclError(message)

    case.review._bound_row_entries = dead_tk_row_reader
    assert (case.history.undo(case.review) if direction == "undo"
            else case.history.redo(case.review)) is False
    assert pdic_path(case.page).read_bytes() == before_pdic
    assert tuple(case.app.entries) == original_rows
    assert (dict(case.candidate) if candidate else None) == before_candidate
    assert len(case.history.undo_stack if direction == "undo"
               else case.history.redo_stack) == 1
    assert "PRIVATE_DESTROYED_REVIEW" not in repr(capsys.readouterr())

@pytest.mark.parametrize("direction", ("undo", "redo"))
@pytest.mark.parametrize("callback", ("word_count", "page_row"))
@pytest.mark.parametrize("error_kind", ("runtime", "tcl"))
def test_candidate_replay_postcommit_derived_refresh_failure(
    tmp_path, capsys, direction, callback, error_kind,
):
    """A Tk teardown after the owned bundle publishes cannot strand its frame.

    This is synthetic saved-PDIC/manual-source E2, not real Windows E3.
    It must fail red before the post-commit Tk exception boundary is fixed.
    """
    from tkinter import TclError

    case = fixture(tmp_path, candidate=True)
    if direction == "redo":
        assert case.history.undo(case.review)
        # An explicit ReviewWindow repaint rebinds the restored original rows.
        case.review.vars = [Var("head"), Var("tail")]
    target = case.before if direction == "undo" else case.after
    exception = RuntimeError if error_kind == "runtime" else TclError

    def destroyed_tk(*_args, **_kwargs):
        raise exception("PRIVATE_SOURCE_PATH destroyed Tk after commit")

    if callback == "word_count":
        case.app._refresh_word_fill_check_from_line_count = destroyed_tk
    else:
        case.app._update_page_row = destroyed_tk

    replay = (case.history.undo(case.review) if direction == "undo"
              else case.history.redo(case.review))
    assert replay is True
    assert pdic_path(case.page).read_bytes() == target.pdic_bytes
    assert tx._bytes_or_absent(case.bindings["manual"]) == target.manual_bytes
    assert [entry.word for entry in case.app.entries] == [
        word for _, word, _, _ in target.entries
    ]
    assert case.candidate["selected"] is (direction == "undo")
    destination = (case.history.redo_stack if direction == "undo"
                   else case.history.undo_stack)
    source = (case.history.undo_stack if direction == "undo"
              else case.history.redo_stack)
    assert len(destination) == 1 and not source
    stdout = capsys.readouterr()
    assert "PRIVATE_SOURCE_PATH" not in stdout.out + stdout.err
