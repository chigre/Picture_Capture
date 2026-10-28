"""G1 source-word + original source-pixel identity, synthetic data only."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.io.formats import pdic_path, write_pdic, read_pdic
from picture_capture.models import Entry
from picture_capture.persistence.project_storage import simplified_review_path_for_image
from picture_capture.proofreading import transactions as tx
from picture_capture.proofreading import review_bundle as bundle
from picture_capture.proofreading.simplified_review import (
    read_records, write_records, guarded_write_records,
    source_word_conflicts, validate_source_word_binding,
)
from picture_capture.proofreading.save_safety import protect_review_pdic_commit
from picture_capture.ui import review_simplified_workflow as workflow


class Var:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


def case(tmp_path: Path):
    page = tmp_path / "test.png"
    page.write_bytes(b"synthetic image fingerprint, no scanned content")
    entry = Entry("old", 10, 20)
    write_pdic(pdic_path(page), [entry], 100, ("synthetic", "@", "@"))
    path = simplified_review_path_for_image(page)
    rows = {
        "10,20": {"x": 10, "y": 20, "source_word": "old",
                  "text": "a human correction", "manual": True},
        # A legacy orphan must be retained byte-for-byte, never attributed
        # to the live PDIC row at a *different* source pixel.
        "90,90": {"x": 90, "y": 90, "source_word": "former",
                  "text": "old orphan human text", "manual": True},
    }
    write_records(path, page.stem, rows)
    app = SimpleNamespace(
        current_page=page, current_index=0,
        project=SimpleNamespace(root=tmp_path), entries=[entry],
        image=SimpleNamespace(width=100),
        settings=SimpleNamespace(proofreading_event_capture=False),
        _batch_active=False, _pending_manual_override_payload=None,
        ocr_review_candidates=[], entry_editor_bindings=[],
        _manual_selection_path=lambda: tmp_path / "manual.json",
        _paddle_cache_path=lambda: tmp_path / "ocr.json",
        _sort_entries_reading_order=lambda: None,
        pages_tuple=lambda: ("synthetic", "@", "@"),
        _flush_pending_manual_override=lambda: None,
        _flush_proofreading_candidate_evidence=lambda: None,
        _flush_proofreading_add_evidence=lambda: None,
        _refresh_word_fill_check_from_line_count=lambda *a, **k: None,
        _update_page_row=lambda *a: None,
        status_var=Var(""),
    )
    review = SimpleNamespace(
        parent=app, vars=[Var("old")],
        row_entries=[entry], _rendered_page_stem=page.stem,
        _filter_rows_active=False,
        simplified_vars=[Var("a human correction")],
        simplified_manual_flags=[True],
        simplified_actual_values=["a human correction"],
        simplified_auto_refresh_flags=[False],
        simplified_editors=[object()], active_index=-1,
        _simplified_page_cache={page.stem: rows},
        _r3_simplified_source_bytes={page.stem: (path.resolve(), path.read_bytes())},
        _simplified_dirty_pages=set(),
        _simplified_display_from_value=lambda original, actual, manual: actual,
        _refresh_cc_simplified_comparison=lambda index: None,
    )
    review._bound_row_entries = lambda: app.entries
    review._simplified_page_records = lambda stem: review._simplified_page_cache[stem]
    review._commit_edits = lambda: None
    return page, path, entry, app, review


@pytest.mark.parametrize("saved_word,live_word,conflict", [
    ("old", "old", False), ("old", "NEW", True),
    ("old", "old ", True), ("", "old", True),
])
def test_same_pixel_not_same_word_is_not_human_ownership(saved_word, live_word, conflict):
    saved = {"source_word": saved_word, "manual": True, "text": "someone's correction"}
    assert source_word_conflicts(saved, live_word) is conflict
    assert source_word_conflicts(None, live_word) is False


@pytest.mark.parametrize("mutation", ["external_pdic_word", "foreign_source_word"])
def test_preexisting_wrong_source_word_refuses_paired_commit_before_any_write(
    tmp_path, mutation,
):
    page, path, entry, app, review = case(tmp_path)
    if mutation == "external_pdic_word":
        entry.word = "replacement"
        review.vars[0].set("replacement")
        write_pdic(pdic_path(page), [entry], 100, ("synthetic", "@", "@"))
    else:
        rows = read_records(path)
        rows["10,20"]["source_word"] = "another headword"
        write_records(path, page.stem, rows)
        review._simplified_page_cache[page.stem] = rows
    original_pdic = pdic_path(page).read_bytes()
    original_sidecar = path.read_bytes()
    review._r3_simplified_source_bytes[page.stem] = (path.resolve(), original_sidecar)
    before = tx.snapshot_review(review)
    assert before is not None
    with pytest.raises(RuntimeError, match="来源词条"):
        with protect_review_pdic_commit(review):
            bundle.commit_review_bundle(review, before)
    assert pdic_path(page).read_bytes() == original_pdic
    assert path.read_bytes() == original_sidecar
    assert not tx._marker_present(tx._recovery_path(page))


def test_valid_saved_manual_word_and_legacy_orphan_remain_unchanged(tmp_path):
    page, path, entry, app, review = case(tmp_path)
    before = path.read_bytes()
    snapshot = tx.snapshot_review(review)
    with protect_review_pdic_commit(review):
        bundle.commit_review_bundle(review, snapshot)
    assert path.read_bytes() == before
    assert read_records(path)["90,90"]["text"] == "old orphan human text"
    assert not tx._marker_present(tx._recovery_path(page))


@pytest.mark.parametrize("rename_cache", [False, True])
def test_pending_headword_change_requires_matching_proposed_sidecar_word(
    tmp_path, rename_cache,
):
    page, path, entry, app, review = case(tmp_path)
    before_pdic, before_sidecar = pdic_path(page).read_bytes(), path.read_bytes()
    source = tx.snapshot_review(review)
    assert source is not None
    with protect_review_pdic_commit(review):
        entry.word = "new"
        review.vars[0].set("new")
        if rename_cache:
            review._simplified_page_cache[page.stem]["10,20"]["source_word"] = "new"
        if rename_cache:
            bundle.commit_review_bundle(review, source)
        else:
            with pytest.raises(RuntimeError, match="来源词条"):
                bundle.commit_review_bundle(review, source)
    if rename_cache:
        assert b"new#" in pdic_path(page).read_bytes()
        assert read_records(path)["10,20"]["source_word"] == "new"
        assert read_records(path)["10,20"]["text"] == "a human correction"
        assert not tx._marker_present(tx._recovery_path(page))
    else:
        # The paired writer refused before any canonical file mutation. The
        # synthetic surrounding context intentionally catches the error,
        # so the in-memory entry can still be pending until user saves again.
        assert pdic_path(page).read_bytes() == before_pdic
        assert path.read_bytes() == before_sidecar
        assert not tx._marker_present(tx._recovery_path(page))


def test_simplified_only_write_refuses_mismatched_existing_pdic_word(tmp_path):
    page, path, entry, app, review = case(tmp_path)
    entry.word = "new OCR word"
    write_pdic(pdic_path(page), [entry], 100, ("synthetic", "@", "@"))
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="来源词条"):
        guarded_write_records(page, path, page.stem, read_records(path), before)
    assert path.read_bytes() == before
    assert not tx._marker_present(tx._recovery_path(page))


def test_simplified_only_rejects_wrong_target_source_word(tmp_path):
    page, path, entry, app, review = case(tmp_path)
    proposed = read_records(path)
    proposed["10,20"]["source_word"] = "some other word"
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="来源词条"):
        guarded_write_records(page, path, page.stem, proposed, before)
    assert path.read_bytes() == before
    assert not tx._marker_present(tx._recovery_path(page))


@pytest.mark.parametrize("when", ["during_preview", "after_journal_stage"])
def test_independent_sidecar_write_never_binds_stale_pdic_after_race(
    tmp_path, monkeypatch, when,
):
    page, path, entry, app, review = case(tmp_path)
    old_sidecar = path.read_bytes()
    proposed = read_records(path)
    proposed["10,20"]["text"] = "our revised manual correction"
    external_pdic = None
    if when == "during_preview":
        original = write_records
        def writer(proposal, stem, rows):
            nonlocal external_pdic
            original(proposal, stem, rows)
            entry.word = "new foreign headword"
            write_pdic(pdic_path(page), [entry], 100, ("synthetic", "@", "@"))
            external_pdic = pdic_path(page).read_bytes()
        with pytest.raises(RuntimeError, match="PDIC"):
            guarded_write_records(page, path, page.stem, proposed, old_sidecar, writer=writer)
    else:
        # Explicitly inject after R3 journal creation but before any sidecar
        # publication. This exercises source-drift post-stage without
        # monkeypatching the rollback publisher itself.
        original_stage = tx._stage_recovery
        def staged(page_arg, changes, *, rollback_required=False):
            nonlocal external_pdic
            marker = original_stage(
                page_arg, changes, rollback_required=rollback_required,
            )
            entry.word = "new foreign headword"
            write_pdic(pdic_path(page), [entry], 100, ("synthetic", "@", "@"))
            external_pdic = pdic_path(page).read_bytes()
            return marker
        monkeypatch.setattr(tx, "_stage_recovery", staged)
        with pytest.raises(RuntimeError, match="PDIC"):
            guarded_write_records(page, path, page.stem, proposed, old_sidecar)
    assert path.read_bytes() == old_sidecar
    assert pdic_path(page).read_bytes() == external_pdic
    assert not tx._marker_present(tx._recovery_path(page))


def test_focusout_and_simplified_key_cannot_reassign_old_human_record(tmp_path):
    page, path, entry, app, review = case(tmp_path)
    # Simulate PDIC replacement at the same physical pixel while an old
    # saved human sidecar remains in the UI cache.
    entry.word = "new OCR word"
    review.vars[0].set("new OCR word")
    review.simplified_vars[0].set("typed newer manual")
    review._capture_simplified_edits = lambda stem: None
    deps = SimpleNamespace(
        simplified_entry_key=lambda x, y: f"{x},{y}",
        simplify_text=lambda word: "auto:"+word,
        messagebox=SimpleNamespace(showerror=lambda *a, **k: None),
    )
    saved = dict(review._simplified_page_cache[page.stem]["10,20"])
    workflow._capture_simplified_edits(review, deps, page.stem)
    assert review._simplified_page_cache[page.stem]["10,20"] == saved
    workflow.on_simplified_key(
        review, deps, SimpleNamespace(widget=review.simplified_editors[0]), 0,
    )
    assert review._simplified_page_cache[page.stem]["10,20"] == saved
    assert not review._simplified_dirty_pages


def test_regeneration_refuses_old_manual_source_word_without_saving(tmp_path):
    page, path, entry, app, review = case(tmp_path)
    entry.word = "new OCR word"
    review.vars[0].set("new OCR word")
    errors = []
    writes = []
    app._claim_page_for_manual_edit = lambda: True
    review._simplified_page_records = lambda stem: review._simplified_page_cache[stem]
    review._persist_simplified_page = lambda stem: writes.append(stem)
    review._refresh_cc_simplified_comparison = lambda index: None
    deps = SimpleNamespace(
        simplified_entry_key=lambda x, y: f"{x},{y}",
        simplify_text=lambda word: "auto:" + word,
        messagebox=SimpleNamespace(showerror=lambda *a, **kw: errors.append(a)),
    )
    before = dict(review._simplified_page_cache[page.stem]["10,20"])
    workflow.regenerate_simplified_current_page(review, deps)
    assert errors and not writes
    assert review._simplified_page_cache[page.stem]["10,20"] == before
    assert review.simplified_manual_flags == [True]
    assert not review._simplified_dirty_pages
