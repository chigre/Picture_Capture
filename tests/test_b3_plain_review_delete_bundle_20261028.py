"""R3 noncandidate deletion: one PDIC/simplified recovery bundle, no user scans."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.io.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.persistence.project_storage import simplified_review_path_for_image
from picture_capture.proofreading import review_bundle as bundle
from picture_capture.proofreading import transactions as tx
from picture_capture.proofreading.simplified_review import read_records, write_records
from picture_capture.ui import review_entry_actions as entry_owner


class Var:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


def setup(tmp_path):
    page = tmp_path / "synthetic.png"
    page.write_bytes(b"synthetic image placeholder, no private image")
    first = Entry("first", 10, 20)
    second = Entry("second", 30, 40)
    original = [first, second]
    write_pdic(pdic_path(page), original, 100, ("synthetic", "@", "@"))
    sidecar = simplified_review_path_for_image(page)
    rows = {
        "10,20": {"x": 10, "y": 20, "source_word": "first",
                  "text": "hand-first", "manual": True},
        "30,40": {"x": 30, "y": 40, "source_word": "second",
                  "text": "hand-second", "manual": True},
        "90,90": {"x": 90, "y": 90, "source_word": "unrelated",
                  "text": "other human", "manual": True},
    }
    write_records(sidecar, page.stem, rows)
    messages = []
    app = SimpleNamespace(
        current_page=page, current_index=0, image=SimpleNamespace(width=100),
        project=SimpleNamespace(root=tmp_path, images=[page]),
        entries=list(original),
        settings=SimpleNamespace(proofreading_event_capture=False),
        _batch_active=False, _pending_manual_override_payload=None,
        ocr_review_candidates=[], entry_editor_bindings=[],
        _claim_page_for_manual_edit=lambda: True,
        _manual_selection_path=lambda: tmp_path / "manual_selection.json",
        _paddle_cache_path=lambda: tmp_path / "ocr.json",
        _sort_entries_reading_order=lambda: None,
        pages_tuple=lambda: ("synthetic", "@", "@"),
        _flush_pending_manual_override=lambda: None,
        _flush_proofreading_candidate_evidence=lambda: None,
        _flush_proofreading_add_evidence=lambda: None,
        _refresh_word_fill_check_from_line_count=lambda *a, **kw: None,
        _update_page_row=lambda *a: None,
        clear_review_entry_highlight=lambda: None,
        redraw=lambda: None,
        status_var=SimpleNamespace(set=messages.append),
    )
    view = SimpleNamespace(
        parent=app, _rendered_page_stem=page.stem,
        vars=[Var("first"), Var("second")],
        simplified_vars=[Var("hand-first"), Var("hand-second")],
        simplified_actual_values=["hand-first", "hand-second"],
        simplified_manual_flags=[True, True], _filter_rows_active=False,
        _simplified_page_cache={page.stem: rows},
        _simplified_dirty_pages=set(), _r3_simplified_source_bytes={
            page.stem: (sidecar.resolve(), sidecar.read_bytes())},
        _bound_row_entries=lambda: list(original),
        _simplified_page_records=lambda stem: view._simplified_page_cache[stem],
        _request_render_rows=lambda **kw: None,
        _show_ocr_options=lambda candidate: None, _update_title=lambda: None,
        active_index=0,
        _capture_simplified_edits=lambda stem: None,
    )
    def commit():
        for row, var in zip(original, view.vars):
            if row in app.entries:
                row.word = var.get().strip()
        # Actual ReviewWindow's capture pass refreshes source-word provenance;
        # these synthetic fixed display values remain intentionally manual.
        for row in original:
            key = f"{row.x},{row.y}"
            if key in rows:
                view._simplified_page_records(page.stem)[key]["source_word"] = row.word
    view._commit_edits = commit
    deps = SimpleNamespace(
        read_pdic=read_pdic, pdic_path=pdic_path,
        simplified_entry_key=lambda x, y: f"{x},{y}",
    )
    return page, original, app, view, deps, messages


def test_ordinary_delete_commits_both_files_preserves_unrelated_human_bytes(tmp_path):
    page, rows, app, view, deps, messages = setup(tmp_path)
    before_other = read_records(simplified_review_path_for_image(page))["90,90"]
    assert entry_owner.delete_review_entry(view, deps, 0) == "break"
    assert app.entries == [rows[1]]
    assert [(x.word, x.x, x.y) for x in read_pdic(pdic_path(page))] == [
        ("second", 30, 40)]
    actual = read_records(simplified_review_path_for_image(page))
    assert "10,20" not in actual and actual["30,40"]["text"] == "hand-second"
    assert actual["90,90"] == before_other
    assert view._r3_simplified_source_bytes[page.stem][1] == (
        simplified_review_path_for_image(page).read_bytes())
    assert not tx._marker_present(tx._recovery_path(page))
    assert messages[-1].startswith("已删除词条")


def test_same_bundle_commits_other_pending_editor_text_then_deletes_middle_row(tmp_path):
    page, rows, app, view, deps, messages = setup(tmp_path)
    view.vars[0].set("new human first")
    assert entry_owner.delete_review_entry(view, deps, 1) == "break"
    assert app.entries == [rows[0]] and rows[0].word == "new human first"
    assert [(x.word, x.x, x.y) for x in read_pdic(pdic_path(page))] == [
        ("new human first", 10, 20)]
    saved = read_records(simplified_review_path_for_image(page))
    assert "30,40" not in saved and saved["10,20"]["source_word"] == "new human first"
    assert saved["90,90"]["text"] == "other human"
    assert not tx._marker_present(tx._recovery_path(page))


@pytest.mark.parametrize("fault", ["before_pdic", "after_pdic", "before_simplified", "after_simplified"])
def test_publish_fault_rolls_back_both_sidecars_and_live_entry(tmp_path, monkeypatch, fault):
    page, rows, app, view, deps, messages = setup(tmp_path)
    original_pdic = pdic_path(page).read_bytes()
    path = simplified_review_path_for_image(page)
    original_sidecar = path.read_bytes()
    original_publish = bundle._publish
    phase = [0]
    def inject(p, data):
        phase[0] += 1
        if fault == "before_pdic" and phase[0] == 1:
            raise OSError("fault before PDIC")
        if fault == "before_simplified" and phase[0] == 2:
            raise OSError("fault before simplified")
        original_publish(p, data)
        if fault == "after_pdic" and phase[0] == 1:
            raise OSError("fault after PDIC")
        if fault == "after_simplified" and phase[0] == 2:
            raise OSError("fault after simplified")
    monkeypatch.setattr(bundle, "_publish", inject)
    assert entry_owner.delete_review_entry(view, deps, 0) == "break"
    assert pdic_path(page).read_bytes() == original_pdic
    assert path.read_bytes() == original_sidecar
    assert app.entries == rows
    assert rows[0].word == "first"
    assert "10,20" in view._simplified_page_cache[page.stem]
    assert not tx._marker_present(tx._recovery_path(page))
    assert "删除失败" in messages[-1]


@pytest.mark.parametrize("race", ["external_sidecar_after_pdic", "external_pdic_before_stage"])
def test_external_human_bytes_cannot_be_overwritten(tmp_path, monkeypatch, race):
    page, rows, app, view, deps, messages = setup(tmp_path)
    path = simplified_review_path_for_image(page)
    old_pdic = pdic_path(page).read_bytes()
    foreign = b"third-party manual correction bytes -- must remain exact"
    if race == "external_pdic_before_stage":
        def intervene():
            pdic_path(page).write_bytes(foreign)
            return True
        app._claim_page_for_manual_edit = intervene
        assert entry_owner.delete_review_entry(view, deps, 0) == "break"
        assert pdic_path(page).read_bytes() == foreign
        assert path.read_bytes() != foreign
        assert app.entries == rows
        assert not tx._marker_present(tx._recovery_path(page))
    else:
        original_publish = bundle._publish
        def inject(p, data):
            original_publish(p, data)
            if p == pdic_path(page):
                path.write_bytes(foreign)
        monkeypatch.setattr(bundle, "_publish", inject)
        assert entry_owner.delete_review_entry(view, deps, 0) == "break"
        assert path.read_bytes() == foreign
        assert tx._marker_present(tx._recovery_path(page))
        # Unknown foreign bytes block replay; do not pretend a full rollback.
        assert "删除失败" in messages[-1]
    assert "已删除词条" not in messages[-1]


def test_stale_page_source_refusal_preserves_cache_and_disk(tmp_path):
    page, rows, app, view, deps, messages = setup(tmp_path)
    initial = pdic_path(page).read_bytes()
    sidecar = simplified_review_path_for_image(page).read_bytes()
    app.current_page = tmp_path / "other.png"
    assert entry_owner.delete_review_entry(view, deps, 0) == "break"
    assert pdic_path(page).read_bytes() == initial
    assert simplified_review_path_for_image(page).read_bytes() == sidecar
    assert app.entries == rows
    assert "未执行" in messages[-1]
