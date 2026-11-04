"""R3 RED-first: live ReviewWindow text display and source-pinned auto preview.

Only synthetic page, fake Tk widgets, and exact in-memory row objects. Live
preview may update a main canvas widget but must NOT mutate Entry.word or
PDIC before the guarded ReviewWindow bundle commits.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.proofreading import main_editor_sync
from picture_capture.ui import review_simplified_workflow as simplified


class Var:
    def __init__(self, value=""):
        self.value = value
        self.callbacks = []
    def get(self):
        return self.value
    def set(self, value):
        self.value = value
        for callback in tuple(self.callbacks):
            callback("var", "", "write")
    def trace_add(self, action, callback):
        assert action == "write"
        self.callbacks.append(callback)
        return str(len(self.callbacks))


class Editor:
    def __init__(self, word):
        self.value = word
    def get(self):
        return self.value
    def delete(self, start, end):
        assert (start, end) == (0, "end")
        self.value = ""
    def insert(self, pos, text):
        assert pos == 0
        self.value = text


def case(*, canvas_text="原词"):
    page = Path("000001.png")
    row = SimpleNamespace(word="原词", x=10, y=20)
    canvas = Editor(canvas_text)
    status = Var("")
    app = SimpleNamespace(
        current_page=page, entries=[row],
        project=object(), entry_editor_bindings=[(canvas, row)],
        status_var=status,
    )
    review = SimpleNamespace(
        parent=app, vars=[Var("原词")], row_entries=[row],
        _rendered_page_stem=page.stem, _filter_rows_active=False,
    )
    review._bound_row_entries = lambda: list(review.row_entries)
    return app, review, row, canvas, status


def test_live_review_typing_updates_main_widget_without_changing_disk_model():
    app, review, row, canvas, status = case()
    main_editor_sync.bind_review_word_preview(review, 0)
    review.vars[0].set("修正词")  # Tk StringVar, not KeyRelease
    assert canvas.get() == "修正词"
    assert row.word == "原词"  # frozen source until guarded commit
    assert review.vars[0].get() == "修正词"
    assert "未保存" in status.get() or "尚未" in status.get()
    # Main/Review buffers now agree; paired save can consume both as ONE
    # revision rather than misclassifying a review edit as a second author.
    assert main_editor_sync.bridge_main_canvas_text_into_review(review) == 1
    assert row.word == "原词"


def test_live_review_paste_or_ime_trace_and_revert_works_without_keyrelease():
    app, review, row, canvas, _status = case()
    main_editor_sync.bind_review_word_preview(review, 0)
    review.vars[0].set("中文粘贴")
    assert canvas.get() == "中文粘贴"
    review.vars[0].set("原词")
    assert canvas.get() == "原词"
    assert row.word == "原词"


@pytest.mark.parametrize("change", ["different_page", "row_replaced", "model_changed"])
def test_obsolete_review_callback_never_touches_main(change):
    app, review, row, canvas, status = case()
    main_editor_sync.bind_review_word_preview(review, 0)
    if change == "different_page":
        app.current_page = Path("000002.png")
    elif change == "row_replaced":
        review.row_entries[0] = SimpleNamespace(word="原词", x=10, y=20)
    else:
        row.word = "external-owner"
    review.vars[0].set("旧回调不能覆盖")
    assert canvas.get() == "原词"
    assert row.word == ("external-owner" if change == "model_changed" else "原词")


@pytest.mark.parametrize("when", ["already_dirty", "after_live_preview"])
def test_independent_main_human_text_not_silently_clobbered(when):
    app, review, row, canvas, status = case(
        canvas_text="独立主界面输入" if when == "already_dirty" else "原词",
    )
    main_editor_sync.bind_review_word_preview(review, 0)
    if when == "after_live_preview":
        review.vars[0].set("第一步")
        assert canvas.get() == "第一步"
        canvas.value = "独立主界面输入"
    review.vars[0].set("另一份校对输入")
    assert canvas.get() == "独立主界面输入"
    assert review.vars[0].get() == "另一份校对输入"
    assert row.word == "原词"
    assert "冲突" in status.get() or "不同" in status.get()


def test_auto_simplified_preview_keeps_frozen_source_until_original_commit():
    row = SimpleNamespace(word="原词", x=10, y=20)
    page = Path("000001.png")
    records = {
        "10,20": {
            "x": 10, "y": 20, "source_word": "原词",
            "text": "原词", "manual": False,
        },
    }
    deps = SimpleNamespace(
        simplified_entry_key=lambda x, y: f"{x},{y}",
        simplify_text=lambda word: word,  # conversion may be identical
    )
    review = SimpleNamespace(
        parent=SimpleNamespace(current_page=page, entries=[row],
                               entry_editor_bindings=[]),
        row_entries=[row], vars=[Var("新词")],
        simplified_vars=[Var("原词")],
        simplified_manual_flags=[False],
        simplified_actual_values=["原词"],
        simplified_auto_refresh_flags=[True],
        _rendered_page_stem=page.stem, _filter_rows_active=False,
        _simplified_dirty_pages=set(), active_index=-1,
        _simplified_page_records=lambda stem: records,
        _simplified_display_from_value=lambda original, actual, manual:
            simplified._simplified_display_from_value(deps, original, actual, manual),
        _auto_simplified_value=lambda original, fallback=None: original,
        _refresh_cc_simplified_comparison=lambda index: None,
    )
    review._bound_row_entries = lambda: [row]
    review._capture_simplified_edits = lambda stem: simplified._capture_simplified_edits(
        review, deps, stem,
    )
    simplified._refresh_simplified_for_index(review, deps, 0)
    assert review.simplified_vars[0].get() == "√"
    assert records["10,20"]["source_word"] == "原词"  # pending rename
    simplified._capture_simplified_edits(review, deps, page.stem)
    assert review.simplified_manual_flags == [False]
    assert records["10,20"]["source_word"] == "原词"
    main_editor_sync.commit_proofread_entries(review)
    assert row.word == "新词"
    assert records["10,20"]["source_word"] == "新词"
    assert records["10,20"]["text"] == "新词"
    assert records["10,20"]["manual"] is False


@pytest.mark.parametrize("foreign_sidecar_race", [False, True])
def test_live_main_preview_real_pdic_sidecar_save_and_foreign_race(
    tmp_path, foreign_sidecar_race,
):
    """Real production serializers/paired writer, synthetic file bytes only.

    A Review edit must paint the main editor NOW but both PDIC and simplified
    records change only under a verified bundled save. A foreign sidecar write
    between snapshot and commit must preserve every original/human byte and
    both unsaved Tk buffers, with no fake save success.
    """
    from picture_capture.io.formats import pdic_path, write_pdic, read_pdic
    from picture_capture.models import Entry
    from picture_capture.persistence.project_storage import simplified_review_path_for_image
    from picture_capture.proofreading.simplified_review import write_records, read_records
    from picture_capture.proofreading import transactions, review_bundle, save_safety

    page = tmp_path / "000001.png"
    original_image = b"pure synthetic immutable page witness"
    page.write_bytes(original_image)
    row = Entry("原词", 10, 20)
    write_pdic(pdic_path(page), [row], 100, (page.stem, "@", "@"))
    sidecar = simplified_review_path_for_image(page)
    disk_records = {
        "10,20": {
            "x": 10, "y": 20, "source_word": "原词",
            "text": "原詞", "manual": False,
        },
    }
    write_records(sidecar, page.stem, disk_records)
    original_pdic = pdic_path(page).read_bytes()
    original_sidecar = sidecar.read_bytes()
    canvas, status = Editor("原词"), Var("")
    app = SimpleNamespace(
        current_page=page, current_index=0,
        entries=[row], image=SimpleNamespace(width=100),
        project=SimpleNamespace(root=tmp_path, images=[page]),
        settings=SimpleNamespace(proofreading_event_capture=False),
        entry_editor_bindings=[(canvas, row)],
        _batch_active=False, _pending_manual_override_payload=None,
        ocr_review_candidates=[], status_var=status,
        _manual_selection_path=lambda: tmp_path / "human-selection.json",
        _paddle_cache_path=lambda: tmp_path / "synthetic-ocr.json",
        _sort_entries_reading_order=lambda: None,
        pages_tuple=lambda: (page.stem, "@", "@"),
        _flush_pending_manual_override=lambda: None,
        _flush_proofreading_candidate_evidence=lambda: None,
        _flush_proofreading_add_evidence=lambda: None,
        _refresh_word_fill_check_from_line_count=lambda *a, **kw: None,
        _update_page_row=lambda *a, **kw: None,
    )
    deps = SimpleNamespace(
        simplified_entry_key=lambda x, y: f"{x},{y}",
        simplify_text=lambda original: original,
    )
    records = {key: dict(record) for key, record in disk_records.items()}
    review = SimpleNamespace(
        parent=app, row_entries=[row], vars=[Var("原词")],
        simplified_vars=[Var("原詞")],
        simplified_actual_values=["原詞"],
        simplified_manual_flags=[False],
        simplified_auto_refresh_flags=[True],
        _rendered_page_stem=page.stem, _filter_rows_active=False,
        _simplified_dirty_pages=set(), active_index=-1,
        _simplified_page_cache={page.stem: records},
        _r3_simplified_source_bytes={
            page.stem: (sidecar.resolve(), original_sidecar),
        },
        _simplified_page_records=lambda stem: records,
        _auto_simplified_value=lambda original, fallback=None: original,
        _simplified_display_from_value=lambda original, actual, manual:
            simplified._simplified_display_from_value(
                deps, original, actual, manual,
            ),
        _refresh_cc_simplified_comparison=lambda index: None,
    )
    review._bound_row_entries = lambda: [row]
    review._capture_simplified_edits = lambda stem: simplified._capture_simplified_edits(
        review, deps, stem,
    )
    main_editor_sync.bind_review_word_preview(review, 0)
    review.vars[0].set("校对词")
    simplified._refresh_simplified_for_index(review, deps, 0)
    assert canvas.get() == "校对词"
    assert row.word == "原词"
    assert pdic_path(page).read_bytes() == original_pdic
    assert sidecar.read_bytes() == original_sidecar
    assert records["10,20"]["source_word"] == "原词"
    source = transactions.snapshot_review(review, allow_evidence=True)
    assert source is not None

    if foreign_sidecar_race:
        # Another writer owns this new human correction. Never replace it,
        # retry stale snapshots, or acknowledge the local pending input.
        foreign = {
            "10,20": {
                "x": 10, "y": 20, "source_word": "原词",
                "text": "other independent human correction", "manual": True,
            }
        }
        write_records(sidecar, page.stem, foreign)
        foreign_bytes = sidecar.read_bytes()
        with pytest.raises(RuntimeError, match="指纹|来源|变化"):
            with save_safety.protect_review_pdic_commit(review):
                main_editor_sync.commit_proofread_entries(review)
                review_bundle.commit_review_bundle(review, source)
        assert pdic_path(page).read_bytes() == original_pdic
        assert sidecar.read_bytes() == foreign_bytes
        assert row.word == "原词"
        assert review.vars[0].get() == canvas.get() == "校对词"
    else:
        with save_safety.protect_review_pdic_commit(review):
            main_editor_sync.commit_proofread_entries(review)
            review_bundle.commit_review_bundle(review, source)
        assert read_pdic(pdic_path(page))[0].word == "校对词"
        assert read_records(sidecar)["10,20"] == {
            "x": 10, "y": 20, "source_word": "校对词",
            "text": "校对词", "manual": False,
        }
        assert row.word == review.vars[0].get() == canvas.get() == "校对词"

    assert page.read_bytes() == original_image
    assert not transactions._marker_present(transactions._recovery_path(page))
