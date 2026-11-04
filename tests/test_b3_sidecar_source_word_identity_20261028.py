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


@pytest.mark.parametrize("when", ["during_preview", "late_preview_readback"])
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
        # Freeze PDIC provenance, finish the preview, THEN emulate a foreign
        # replacement at the independent writer's final source readback.
        # This is a separate boundary from the injected serializer callback
        # above; it must refuse before creating a journal or changing sidecar.
        original_read = tx._bytes_or_absent
        checked = [0]
        def readback(target):
            nonlocal external_pdic
            if target == pdic_path(page):
                checked[0] += 1
                if checked[0] == 3:
                    entry.word = "new foreign headword"
                    write_pdic(pdic_path(page), [entry], 100, ("synthetic", "@", "@"))
                    external_pdic = pdic_path(page).read_bytes()
            return original_read(target)
        monkeypatch.setattr(tx, "_bytes_or_absent", readback)
        with pytest.raises(RuntimeError, match="PDIC"):
            guarded_write_records(page, path, page.stem, proposed, old_sidecar)
        assert checked[0] >= 3
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


def test_independent_sidecar_healthy_same_word_reaches_journal_and_commits(
    tmp_path, monkeypatch,
):
    """Positive control: the fail-closed source-word guard is not a blanket veto."""
    page, path, entry, app, review = case(tmp_path)
    original = path.read_bytes()
    proposed = read_records(path)
    proposed["10,20"]["text"] = "confirmed newer manual"
    observed = []
    actual_stage = tx._stage_recovery
    def staged(*args, **kwargs):
        observed.append(tuple(x[0] for x in args[1]))
        return actual_stage(*args, **kwargs)
    monkeypatch.setattr(tx, "_stage_recovery", staged)
    committed = guarded_write_records(page, path, page.stem, proposed, original)
    assert observed == [("simplified",)]
    assert committed == path.read_bytes() != original
    assert read_records(path)["10,20"]["text"] == "confirmed newer manual"
    assert read_records(path)["90,90"]["text"] == "old orphan human text"
    assert pdic_path(page).read_bytes() is not None
    assert not tx._marker_present(tx._recovery_path(page))


def test_reported_unsaved_original_regenerates_with_real_pdic_pair_then_sidecar(tmp_path):
    """Real serializers + real guarded bundle + separate regenerate, no scans."""
    from picture_capture.proofreading.main_editor_sync import commit_proofread_entries
    page, path, entry, app, review = case(tmp_path)
    app.project.images = [page]
    app._claim_page_for_manual_edit = lambda: True
    review.vars[0].set("corrected")
    review._capture_simplified_edits = lambda stem: None
    review._commit_edits = lambda: commit_proofread_entries(review)

    def save_original(*, redraw_main=True):
        assert redraw_main is False
        before = tx.snapshot_review(review)
        assert before is not None
        with protect_review_pdic_commit(review):
            review._commit_edits()
            bundle.commit_review_bundle(review, before)
        return True

    review.save = save_original
    persist_deps = SimpleNamespace(
        simplified_review_path_for_image=simplified_review_path_for_image,
        write_simplified_records=write_records,
    )
    review._persist_simplified_page = lambda stem: workflow._persist_simplified_page(
        review, persist_deps, stem,
    )
    deps = SimpleNamespace(
        simplified_entry_key=lambda x, y: f"{x},{y}",
        simplify_text=lambda word: "auto:" + word,
        messagebox=SimpleNamespace(showerror=lambda *a, **kw: None),
    )
    workflow.regenerate_simplified_current_page(review, deps)
    assert read_pdic(pdic_path(page))[0].word == "corrected"
    assert read_records(path)["10,20"] == {
        "x": 10, "y": 20, "source_word": "corrected",
        "text": "auto:corrected", "manual": False,
    }
    assert read_records(path)["90,90"]["text"] == "old orphan human text"
    assert not tx._marker_present(tx._recovery_path(page))
    assert "已重新简体化" in app.status_var.get()


def test_reported_stale_human_sidecar_preserved_while_new_original_is_saved(tmp_path):
    """An already-detached human correction is not a veto of PDIC-only text.

    Leave its bytes EXACTLY unchanged; never transfer it by shared XY to a
    different current word. The operator can reconcile old data separately.
    """
    from picture_capture.proofreading.main_editor_sync import commit_proofread_entries
    page, path, entry, app, review = case(tmp_path)
    entry.word = "current-from-prior-pdic-save"
    write_pdic(pdic_path(page), [entry], 100, ("synthetic", "@", "@"))
    review.vars[0].set("new-current-human-correction")
    review._capture_simplified_edits = lambda stem: None
    review._has_unreported_simplified_input = lambda: False
    old_sidecar = path.read_bytes()
    prior_pdic = pdic_path(page).read_bytes()
    source = tx.snapshot_review(review)
    assert source is not None
    assert source.simplified_bytes == old_sidecar
    assert source.entries[0][1] == "current-from-prior-pdic-save"
    # Reproduce the real ReviewWindow protected-save source lease.
    # A bare direct helper call must still reject stale ownership.
    review.__dict__["_r3_detached_original_save_source"] = source
    try:
        with protect_review_pdic_commit(review):
            commit_proofread_entries(review)
            bundle.commit_review_bundle(review, source)
    finally:
        review.__dict__.pop("_r3_detached_original_save_source", None)
    assert pdic_path(page).read_bytes() != prior_pdic
    assert read_pdic(pdic_path(page))[0].word == "new-current-human-correction"
    assert path.read_bytes() == old_sidecar
    assert read_records(path)["10,20"]["source_word"] == "old"
    assert read_records(path)["10,20"]["text"] == "a human correction"
    assert not tx._marker_present(tx._recovery_path(page))
    assert "简体" in app.status_var.get()


@pytest.mark.parametrize("unreported_simplified_edit", [False, True])
def test_detached_sidecar_confirmed_noop_save_does_not_trap_next_page(
    tmp_path, unreported_simplified_edit,
):
    """Actual R3 bundle: navigation after a saved rename must not require
    overwriting a preexisting detached human sidecar. A NEW unsaved simplified
    Tk edit must still block a false no-op.
    """
    page, path, entry, app, review = case(tmp_path)
    entry.word = "previously-saved-new-original"
    write_pdic(pdic_path(page), [entry], 100, ("synthetic", "@", "@"))
    review.vars[0].set(entry.word)
    review._commit_edits = lambda: None
    if unreported_simplified_edit:
        review.simplified_vars[0].set("new yet-unsaved human simplified edit")
    prior_pdic = pdic_path(page).read_bytes()
    prior_sidecar = path.read_bytes()
    source = tx.snapshot_review(review)
    assert source is not None
    review.__dict__["_r3_detached_original_save_source"] = source
    try:
        if unreported_simplified_edit:
            with pytest.raises(RuntimeError, match="简体|未确认|输入"):
                with protect_review_pdic_commit(review):
                    bundle.commit_review_bundle(review, source)
        else:
            with protect_review_pdic_commit(review):
                bundle.commit_review_bundle(review, source)
    finally:
        review.__dict__.pop("_r3_detached_original_save_source", None)
    assert pdic_path(page).read_bytes() == prior_pdic
    assert path.read_bytes() == prior_sidecar
    assert not tx._marker_present(tx._recovery_path(page))
    if not unreported_simplified_edit:
        assert "简体" in app.status_var.get()


@pytest.mark.parametrize("explicit", [False, True])
def test_exact_old_sidecar_source_corrected_with_explicit_manual_review_save(
    tmp_path, explicit,
):
    """Screenshot-shaped synthetic case: PDIC '司衡#', old human source '司衡'.

    An explicit ordinary ReviewWindow Save/Next must be able to commit a
    verified correction to '司衡' without modifying prior manual JSON bytes,
    warning that an old manual note may now match again. The background
    autosave is NOT a user decision to rejoin a detached manual sidecar.
    """
    from picture_capture.proofreading import main_editor_sync
    page, path, entry, app, review = case(tmp_path)
    entry.word = "司衡#"
    write_pdic(pdic_path(page), [entry], 100, ("synthetic", "@", "@"))
    records = read_records(path)
    records["10,20"].update(
        source_word="司衡", text="原先人工简体记录", manual=True,
    )
    write_records(path, page.stem, records)
    review._simplified_page_cache[page.stem] = records
    review._r3_simplified_source_bytes[page.stem] = (
        path.resolve(), path.read_bytes(),
    )
    source_before = pdic_path(page).read_bytes()
    sidecar_before = path.read_bytes()

    class MainCanvas:
        def __init__(self):
            self.text = "司衡#"
        def get(self):
            return self.text
        def delete(self, a, b):
            self.text = ""
        def insert(self, a, t):
            self.text = t

    class ReviewVar:
        def __init__(self, text):
            self.text = text
            self.callbacks = []
        def get(self):
            return self.text
        def set(self, text):
            self.text = text
            for callback in tuple(self.callbacks):
                callback("var", "", "write")
        def trace_add(self, mode, callback):
            assert mode == "write"
            self.callbacks.append(callback)

    canvas = MainCanvas()
    app.entry_editor_bindings = [(canvas, entry)]
    review.vars[0] = ReviewVar("司衡#")
    review.simplified_actual_values[0] = "⚠来源词条不一致，请核对原词"
    review.simplified_vars[0].set("⚠来源词条不一致，请核对原词")
    review.simplified_manual_flags[0] = True
    review.simplified_auto_refresh_flags[0] = False
    review._capture_simplified_edits = lambda stem: workflow._capture_simplified_edits(
        review,
        SimpleNamespace(simplified_entry_key=lambda x, y: f"{x},{y}"),
        stem,
    )
    main_editor_sync.bind_review_word_preview(review, 0)
    review.vars[0].set("司衡")
    assert canvas.get() == "司衡"
    assert entry.word == "司衡#"
    assert pdic_path(page).read_bytes() == source_before
    frozen = tx.snapshot_review(review, allow_evidence=True)
    assert frozen is not None
    review.__dict__["_r3_detached_original_save_source"] = frozen
    if explicit:
        review.__dict__["_r3_explicit_detached_source_rejoin"] = frozen
    try:
        if explicit:
            with protect_review_pdic_commit(review):
                main_editor_sync.commit_proofread_entries(review)
                bundle.commit_review_bundle(review, frozen)
            assert read_pdic(pdic_path(page))[0].word == "司衡"
            assert "核对" in app.status_var.get() or "人工" in app.status_var.get()
        else:
            with pytest.raises(RuntimeError, match="来源|原词|归属"):
                with protect_review_pdic_commit(review):
                    main_editor_sync.commit_proofread_entries(review)
                    bundle.commit_review_bundle(review, frozen)
            assert pdic_path(page).read_bytes() == source_before
            assert entry.word == "司衡#"
            assert review.vars[0].get() == canvas.get() == "司衡"
    finally:
        review.__dict__.pop("_r3_detached_original_save_source", None)
        review.__dict__.pop("_r3_explicit_detached_source_rejoin", None)
    assert path.read_bytes() == sidecar_before
    assert read_records(path)["10,20"]["text"] == "原先人工简体记录"
    assert not tx._marker_present(tx._recovery_path(page))
