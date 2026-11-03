"""R3 paired-save failure injection with synthetic data, never private scans."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.io.formats import pdic_path, write_pdic
from picture_capture.models import Entry
from picture_capture.persistence.project_storage import simplified_review_path_for_image
from picture_capture.proofreading.transactions import snapshot_review, _recovery_path
from picture_capture.proofreading.save_safety import protect_review_pdic_commit
from picture_capture.proofreading.review_bundle import commit_review_bundle
from picture_capture.proofreading import review_bundle as bundle


def case(tmp_path):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic-only-not-private-pixels")
    entry = Entry("old", 10, 20)
    write_pdic(pdic_path(page), [entry], 100, ("synthetic", "@", "@"))
    app = SimpleNamespace(
        current_page=page, project=SimpleNamespace(root=tmp_path, images=[page]),
        entries=[entry], image=SimpleNamespace(width=100), current_index=0,
        settings=SimpleNamespace(proofreading_event_capture=False),
        _batch_active=False, _pending_manual_override_payload=None,
        ocr_review_candidates=[], entry_editor_bindings=[],
        _manual_selection_path=lambda: tmp_path / "manual_selection.json",
        _paddle_cache_path=lambda: tmp_path / "ocr.json",
        _sort_entries_reading_order=lambda: None,
        pages_tuple=lambda: ("synthetic", "@", "@"),
        _flush_pending_manual_override=lambda: None,
        _flush_proofreading_candidate_evidence=lambda: None,
        _flush_proofreading_add_evidence=lambda: None,
        _refresh_word_fill_check_from_line_count=lambda *args, **kwargs: None,
        _update_page_row=lambda *args: None,
        status_var=SimpleNamespace(set=lambda *args: None),
    )
    vars = [SimpleNamespace(get=lambda: "new")]
    records = {"10,20": {"x": 10, "y": 20, "source_word": "old", "text": "manual", "manual": True}}
    review = SimpleNamespace(
        parent=app, _rendered_page_stem=page.stem, vars=vars,
        _filter_rows_active=False, _bound_row_entries=lambda: app.entries,
        _simplified_page_cache={page.stem: records},
        _simplified_dirty_pages={page.stem},
        _r3_simplified_source_bytes={page.stem: (
            simplified_review_path_for_image(page).resolve(), None,
        )},
        simplified_manual_flags=[True], simplified_actual_values=["manual"],
        _simplified_page_records=lambda stem: review._simplified_page_cache[stem],
    )
    def change():
        entry.word = "new"
        records["10,20"]["source_word"] = "new"
    review._commit_edits = change
    return page, entry, review


@pytest.mark.parametrize("role", ["pdic", "simplified"])
def test_failed_post_replace_rolls_back_exact_pair_and_ui(tmp_path, monkeypatch, role):
    page, entry, review = case(tmp_path)
    before = snapshot_review(review)
    assert before is not None
    original = pdic_path(page).read_bytes()
    original_publish = bundle._publish
    failed = [False]
    target = pdic_path(page) if role == "pdic" else simplified_review_path_for_image(page)
    def injected(path, data):
        original_publish(path, data)
        if path == target and not failed[0]:
            failed[0] = True
            raise OSError("injected failure after file replace")
    monkeypatch.setattr(bundle, "_publish", injected)
    with pytest.raises(OSError, match="injected failure"):
        with protect_review_pdic_commit(review):
            review._commit_edits()
            commit_review_bundle(review, before)
    assert pdic_path(page).read_bytes() == original
    assert not simplified_review_path_for_image(page).exists()
    assert entry.word == "old"
    assert review.vars[0].get() == "new"
    assert not _recovery_path(page).exists()


def test_review_bundle_success_commits_both_files(tmp_path):
    page, entry, review = case(tmp_path)
    source = snapshot_review(review)
    with protect_review_pdic_commit(review):
        review._commit_edits()
        commit_review_bundle(review, source)
    assert entry.word == "new"
    assert b"new#" in pdic_path(page).read_bytes()
    assert simplified_review_path_for_image(page).exists()
    assert not _recovery_path(page).exists()


def test_external_pdic_modification_blocks_and_preserves_human_bytes(tmp_path):
    page, entry, review = case(tmp_path)
    source = snapshot_review(review)
    pdic_path(page).write_bytes(b"external human data")
    with pytest.raises(RuntimeError, match="指纹"):
        with protect_review_pdic_commit(review):
            review._commit_edits()
            commit_review_bundle(review, source)
    assert pdic_path(page).read_bytes() == b"external human data"


def test_success_discards_stale_deferred_checkbox_snapshot(tmp_path):
    page, entry, review = case(tmp_path)
    review.parent._deferred_save_job = "job-1"
    review.parent._deferred_save_snapshot = ("stale",)
    review.parent._deferred_save_page = page
    cancelled = []
    review.parent.after_cancel = cancelled.append
    before = snapshot_review(review)
    with protect_review_pdic_commit(review):
        review._commit_edits()
        commit_review_bundle(review, before)
    assert cancelled == ["job-1"]
    assert review.parent._deferred_save_snapshot is None
    assert review.parent._deferred_save_page is None


def test_r2_opt_in_source_can_commit_but_undo_remains_denied(tmp_path):
    from picture_capture.ui.review_transaction_actions import capture_review_before
    page, entry, review = case(tmp_path)
    review.parent.settings.proofreading_event_capture = True
    assert snapshot_review(review) is None
    before = capture_review_before(review)
    assert before is not None
    with protect_review_pdic_commit(review):
        review._commit_edits()
        commit_review_bundle(review, before)
    assert entry.word == "new"
    assert snapshot_review(review) is None


def _seed_existing_sidecar(page, review):
    from picture_capture.proofreading.simplified_review import write_records
    path = simplified_review_path_for_image(page)
    # Reuse the exact dict owned by case()._commit_edits so pending editor
    # source-word changes are represented in the real proposal cache.
    records = review._simplified_page_cache[page.stem]
    records["10,20"]["text"] = "human edited text"
    records["10,20"]["manual"] = True
    write_records(path, page.stem, records)
    review._r3_simplified_source_bytes[page.stem] = (
        path.resolve(), path.read_bytes(),
    )
    return path


@pytest.mark.parametrize("scenario", ["same_row", "extra_row", "external_deletion"])
def test_external_human_edit_before_snapshot_never_uses_stale_review_cache(
    tmp_path, scenario,
):
    """Late disk snapshot must NOT legitimize stale ReviewWindow cached rows."""
    from picture_capture.proofreading.simplified_review import read_records, write_records
    page, entry, review = case(tmp_path)
    path = _seed_existing_sidecar(page, review)
    old_pdic = pdic_path(page).read_bytes()
    if scenario == "external_deletion":
        path.unlink()
        foreign = None
    else:
        changed = read_records(path)
        if scenario == "same_row":
            changed["10,20"]["text"] = "new external manual text"
        else:
            changed["50,60"] = {
                "x": 50, "y": 60, "source_word": "foreign",
                "text": "another person's note", "manual": True,
            }
        write_records(path, page.stem, changed)
        foreign = path.read_bytes()
    source = snapshot_review(review)  # snapshot is LATER than external edit
    assert source is not None
    assert source.simplified_bytes == foreign
    with pytest.raises(RuntimeError, match="缓存来源"):
        with protect_review_pdic_commit(review):
            review._commit_edits()
            commit_review_bundle(review, source)
    assert pdic_path(page).read_bytes() == old_pdic
    assert (path.read_bytes() if path.exists() else None) == foreign
    assert entry.word == "old"
    assert not _recovery_path(page).exists()


@pytest.mark.parametrize("bad", [
    "duplicate_coordinate", "unknown_entry_field", "unknown_top_field",
    "missing_entry_field", "bool_coordinate", "string_coordinate",
    "duplicate_json_member", "nan_literal", "wrong_page",
])
def test_unowned_human_sidecar_semantics_refuse_both_bundle_and_direct_save(
    tmp_path, bad,
):
    """Display-normalized records cannot erase unparseable/ambiguous human data."""
    import json
    from picture_capture.proofreading.simplified_review import (
        guarded_write_records, read_records,
    )
    page, entry, review = case(tmp_path)
    path = _seed_existing_sidecar(page, review)
    doc = json.loads(path.read_text("utf-8"))
    row = doc["entries"][0]
    if bad == "duplicate_coordinate":
        doc["entries"].append(dict(row, text="other human edit"))
    elif bad == "unknown_entry_field":
        row["human_comment"] = "DO NOT LOSE"
    elif bad == "unknown_top_field":
        doc["manual_note"] = "DO NOT LOSE"
    elif bad == "missing_entry_field":
        del row["manual"]
    elif bad == "bool_coordinate":
        row["x"] = True
    elif bad == "string_coordinate":
        row["x"] = "10"
    elif bad == "wrong_page":
        doc["page"] = "another-page"
    if bad == "duplicate_json_member":
        raw = path.read_bytes().replace(b'"page":', b'"page":"shadow", "page":', 1)
    elif bad == "nan_literal":
        raw = path.read_bytes().replace(b'"format_version": 1', b'"format_version": NaN')
    else:
        raw = json.dumps(doc, ensure_ascii=False).encode("utf-8")
    path.write_bytes(raw)
    # UI display reader is intentionally permissive; it may already have
    # discarded unknown fields. Pin still matches bytes, so semantic guard is
    # necessary in addition to version pinning.
    review._simplified_page_cache[page.stem] = read_records(path)
    review._r3_simplified_source_bytes[page.stem] = (path.resolve(), raw)
    original_pdic = pdic_path(page).read_bytes()
    snapshot = snapshot_review(review)
    assert snapshot is not None
    with pytest.raises(RuntimeError, match="简体人工"):
        with protect_review_pdic_commit(review):
            review._commit_edits()
            commit_review_bundle(review, snapshot)
    assert pdic_path(page).read_bytes() == original_pdic
    assert path.read_bytes() == raw
    assert entry.word == "old"
    assert not _recovery_path(page).exists()
    with pytest.raises(RuntimeError, match="简体人工"):
        guarded_write_records(page, path, page.stem, read_records(path), raw)
    assert pdic_path(page).read_bytes() == original_pdic
    assert path.read_bytes() == raw
    assert not _recovery_path(page).exists()


def test_healthy_existing_human_sidecar_and_matching_pin_commits_without_loss(tmp_path):
    from picture_capture.proofreading.simplified_review import read_records
    page, entry, review = case(tmp_path)
    path = _seed_existing_sidecar(page, review)
    before = read_records(path)
    old_bytes = path.read_bytes()
    source = snapshot_review(review)
    assert source is not None and source.simplified_bytes == old_bytes
    with protect_review_pdic_commit(review):
        review._commit_edits()
        commit_review_bundle(review, source)
    updated = read_records(path)
    assert updated["10,20"]["text"] == before["10,20"]["text"]
    assert updated["10,20"]["manual"] is True
    assert updated["10,20"]["source_word"] == "new"
    assert b"new#" in pdic_path(page).read_bytes()
    assert review._r3_simplified_source_bytes[page.stem] == (
        path.resolve(), path.read_bytes(),
    )
    assert not _recovery_path(page).exists()


def test_missing_pin_does_not_allow_a_prepopulated_legacy_cache_to_be_saved(tmp_path):
    page, entry, review = case(tmp_path)
    path = _seed_existing_sidecar(page, review)
    before = path.read_bytes()
    review._r3_simplified_source_bytes.clear()
    snapshot = snapshot_review(review)
    with pytest.raises(RuntimeError, match="缓存来源"):
        with protect_review_pdic_commit(review):
            review._commit_edits()
            commit_review_bundle(review, snapshot)
    assert entry.word == "old"
    assert path.read_bytes() == before
    assert not _recovery_path(page).exists()


@pytest.mark.parametrize("existing_sidecar", [False, True])
@pytest.mark.parametrize("manual", [False, True])
def test_live_review_word_rename_rebases_simplified_source_and_commits_pdic(
    tmp_path, existing_sidecar, manual,
):
    """Use the REAL production editor commit; not the fixture's pre-rebased stub.

    A normal headword rename must be allowed to move the matching companion
    record's source_word with the paired R3 bundle. The old on-disk sidecar
    is independently verified against the OLD PDIC before any publication.
    """
    from picture_capture.proofreading.main_editor_sync import commit_proofread_entries
    from picture_capture.proofreading.simplified_review import entry_key, read_records
    from picture_capture.ui import review_simplified_workflow as simpl_workflow

    page, entry, review = case(tmp_path)
    sidecar = simplified_review_path_for_image(page)
    record = review._simplified_page_cache[page.stem]["10,20"]
    record["manual"] = manual
    record["text"] = "human-locked" if manual else "auto-old"
    if existing_sidecar:
        _seed_existing_sidecar(page, review)
        # The existing sidecar has authentic pre-edit ownership.
        assert read_records(sidecar)["10,20"]["source_word"] == "old"
    review.row_entries = [entry]
    review.simplified_vars = [SimpleNamespace(get=lambda: record["text"])]
    review._simplified_display_from_value = (
        lambda word, text, is_manual: text
    )
    review._capture_simplified_edits = lambda stem: simpl_workflow._capture_simplified_edits(
        review, SimpleNamespace(simplified_entry_key=entry_key), stem,
    )
    review._commit_edits = lambda: commit_proofread_entries(review)
    before = snapshot_review(review)
    assert before is not None
    with protect_review_pdic_commit(review):
        review._commit_edits()
        commit_review_bundle(review, before)
    assert entry.word == "new"
    assert read_records(sidecar)["10,20"]["source_word"] == "new"
    assert read_records(sidecar)["10,20"]["text"] == (
        "human edited text" if existing_sidecar else ("human-locked" if manual else "auto-old")
    )
    assert pdic_path(page).read_bytes().startswith(b"new#")
    assert not _recovery_path(page).exists()


def test_live_review_rename_refuses_stale_companion_owner_before_pdic_mutation(tmp_path):
    """Do not relabel a different human correction at a coincident XY."""
    from picture_capture.proofreading.main_editor_sync import commit_proofread_entries
    from picture_capture.proofreading.simplified_review import entry_key
    from picture_capture.ui import review_simplified_workflow as simpl_workflow

    page, entry, review = case(tmp_path)
    record = review._simplified_page_cache[page.stem]["10,20"]
    record["source_word"] = "foreign-owner"
    review.row_entries = [entry]
    review.simplified_vars = [SimpleNamespace(get=lambda: "human")]
    review._simplified_display_from_value = lambda w, v, m: v
    review._capture_simplified_edits = lambda stem: simpl_workflow._capture_simplified_edits(
        review, SimpleNamespace(simplified_entry_key=entry_key), stem,
    )
    original_pdic = pdic_path(page).read_bytes()
    with pytest.raises(RuntimeError, match="(来源|原词|归属|简体)"):
        commit_proofread_entries(review)
    assert pdic_path(page).read_bytes() == original_pdic
    assert entry.word == "old"
    assert record["source_word"] == "foreign-owner"


def test_review_bridge_repairs_preexisting_main_focusout_model_ahead(tmp_path):
    """A main FocusOut may have changed Entry.word BEFORE PDIC publication.

    Exact disk old-word ownership allows staging that newer value in the
    Review editor and temporarily restoring the model to its saved baseline
    so R3 snapshot_review can authorize the paired commit. No disk write here.
    """
    from picture_capture.proofreading.main_editor_sync import bridge_main_canvas_text_into_review
    page, entry, review = case(tmp_path)
    class V:
        def __init__(self, value):
            self.value = value
        def get(self):
            return self.value
        def set(self, value):
            self.value = value
    review.vars = [V("old")]
    widget = V("main-focusout-new")
    entry.word = "main-focusout-new"
    review.parent.entry_editor_bindings = [(widget, entry)]
    assert bridge_main_canvas_text_into_review(review) == 1
    assert review.vars[0].get() == "main-focusout-new"
    assert widget.get() == "main-focusout-new"
    assert entry.word == "old"
    assert [e.word for e in __import__(
        "picture_capture.io.formats", fromlist=["read_pdic"]
    ).read_pdic(pdic_path(page))] == ["old"]


def test_review_bridge_refuses_two_divergent_texts_after_main_model_ahead(tmp_path):
    """An old disk baseline is not permission to discard a review correction."""
    from picture_capture.proofreading.main_editor_sync import bridge_main_canvas_text_into_review
    page, entry, review = case(tmp_path)
    class V:
        def __init__(self, value):
            self.value = value
        def get(self):
            return self.value
        def set(self, value):
            self.value = value
    review.vars = [V("review-new")]
    entry.word = "main-new"
    widget = V("main-new")
    review.parent.entry_editor_bindings = [(widget, entry)]
    with pytest.raises(RuntimeError, match="(冲突|同时|不同|来源)"):
        bridge_main_canvas_text_into_review(review)
    assert entry.word == "main-new"
    assert widget.get() == "main-new"
    assert review.vars[0].get() == "review-new"
    assert b"old#" in pdic_path(page).read_bytes()


class _EditableText:
    def __init__(self, text):
        self.text = text
    def get(self):
        return self.text
    def set(self, value):
        self.text = value
    def delete(self, *_args):
        self.text = ""
    def insert(self, _pos, value):
        self.text = value


def _real_r3_two_view_fixture(tmp_path):
    """Exercise production page lifecycle + editor + R3 paired file writer."""
    from picture_capture.proofreading.main_editor_sync import commit_proofread_entries
    from picture_capture.proofreading.simplified_review import entry_key
    from picture_capture.ui import review_page_lifecycle, review_simplified_workflow

    page, entry, review = case(tmp_path)
    app = review.parent
    app.settings.review_zoom_percent = 100
    app.settings.to_json = lambda *_a: None
    app._foreground_batch_state = lambda *_a: "idle"
    app._claim_page_for_manual_edit = lambda: True
    app.entry_editor_bindings = []
    app.review_window = review
    app.redraw = lambda: None
    review.winfo_exists = lambda: True
    review.vars = [_EditableText("old")]
    review.row_entries = [entry]
    review.simplified_vars = [_EditableText("manual")]
    review._simplified_display_from_value = lambda word, value, manual: value
    review._capture_simplified_edits = lambda stem: review_simplified_workflow._capture_simplified_edits(
        review, SimpleNamespace(simplified_entry_key=entry_key), stem,
    )
    review._commit_edits = lambda: commit_proofread_entries(review)
    review._review_evidence_before_save = lambda: None
    review._review_evidence_after_save = lambda _before: None
    review._stored_review_zoom_percent = lambda: 100
    deps = SimpleNamespace(settings_path=lambda root: root / "project-settings.json")
    review.save = lambda **kwargs: review_page_lifecycle.save(review, deps, **kwargs)
    return page, entry, review, app


def test_real_r3_save_click_commits_both_original_and_simplified(tmp_path):
    from picture_capture.proofreading.simplified_review import read_records
    page, entry, review, app = _real_r3_two_view_fixture(tmp_path)
    review.vars[0].set("校对界面人工新词")
    assert review.save(redraw_main=False) is True
    assert entry.word == "校对界面人工新词"
    assert "校对界面人工新词" in pdic_path(page).read_text(encoding="utf-8")
    row = read_records(simplified_review_path_for_image(page))["10,20"]
    assert row["source_word"] == "校对界面人工新词"
    assert row["text"] == "manual"
    assert not _recovery_path(page).exists()


def test_real_main_save_click_with_open_review_uses_paired_r3_transaction(tmp_path):
    from picture_capture.ui import main_pdic_persistence
    from picture_capture.proofreading.simplified_review import read_records
    page, entry, review, app = _real_r3_two_view_fixture(tmp_path)
    widget = _EditableText("主界面输入但尚未提交")
    app.entry_editor_bindings = [(widget, entry)]
    main_pdic_persistence.save_pdic(app, deps={
        "tk": SimpleNamespace(TclError=RuntimeError),
        "pdic_path": pdic_path,
        "write_pdic": lambda *_a: pytest.fail("unpaired main file writer must not run"),
    })
    assert entry.word == widget.get()
    assert review.vars[0].get() == widget.get()
    assert widget.get() in pdic_path(page).read_text(encoding="utf-8")
    assert read_records(simplified_review_path_for_image(page))["10,20"]["source_word"] == widget.get()
    assert not _recovery_path(page).exists()


def test_real_save_reopens_old_focusout_model_without_losing_main_input(tmp_path):
    page, entry, review, app = _real_r3_two_view_fixture(tmp_path)
    entry.word = "旧版已FocusOut尚未落盘"
    widget = _EditableText(entry.word)
    app.entry_editor_bindings = [(widget, entry)]
    assert review.save(redraw_main=False) is True
    assert entry.word == widget.get()
    assert widget.get() in pdic_path(page).read_text(encoding="utf-8")
    assert not _recovery_path(page).exists()


def test_real_r3_conflicting_windows_refuse_and_preserve_both_inputs(tmp_path):
    page, entry, review, app = _real_r3_two_view_fixture(tmp_path)
    review.vars[0].set("校对界面不同版本")
    widget = _EditableText("主界面不同版本")
    app.entry_editor_bindings = [(widget, entry)]
    before = pdic_path(page).read_bytes()
    assert review.save(redraw_main=False) is False
    assert entry.word == "old"
    assert review.vars[0].get() == "校对界面不同版本"
    assert widget.get() == "主界面不同版本"
    assert pdic_path(page).read_bytes() == before
    assert not _recovery_path(page).exists()
