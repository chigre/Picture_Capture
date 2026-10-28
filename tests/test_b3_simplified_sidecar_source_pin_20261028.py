"""G1: source-pinned simplified sidecar writes; synthetic data-integrity faults."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.io.formats import pdic_path
from picture_capture.persistence.project_storage import simplified_review_path_for_image
from picture_capture.proofreading import transactions as tx
from picture_capture.proofreading.simplified_review import (
    guarded_write_records, read_records, write_records,
)
from picture_capture.ui import review_simplified_workflow as ui


def scene(tmp_path):
    page = tmp_path / "page.png"
    page.write_bytes(b"fake source image")
    pdic_path(page).parent.mkdir(parents=True, exist_ok=True)
    path = simplified_review_path_for_image(page)
    path.parent.mkdir(parents=True, exist_ok=True)
    initial = {"10,20": {"x": 10, "y": 20, "source_word": "head",
                          "text": "manual original", "manual": True}}
    write_records(path, page.stem, initial)
    app = SimpleNamespace(project=SimpleNamespace(images=[page]), current_page=page)
    review = SimpleNamespace(parent=app, _rendered_page_stem=page.stem,
                             _simplified_page_cache={}, _simplified_dirty_pages={page.stem})
    deps = SimpleNamespace(read_simplified_records=read_records,
                           write_simplified_records=write_records,
                           simplified_review_path_for_image=simplified_review_path_for_image)
    review._simplified_page_records = lambda stem: ui._simplified_page_records(review, deps, stem)
    return page, path, review, deps


def test_normal_save_pins_source_and_advances_only_after_success(tmp_path):
    page, path, review, deps = scene(tmp_path)
    before = path.read_bytes()
    records = review._simplified_page_records(page.stem)
    assert review._r3_simplified_source_bytes[page.stem] == (path.resolve(), before)
    records["10,20"]["text"] = "new manual"
    ui._persist_simplified_page(review, deps, page.stem)
    assert read_records(path)["10,20"]["text"] == "new manual"
    assert review._r3_simplified_source_bytes[page.stem][1] == path.read_bytes()
    assert not tx._marker_present(tx._recovery_path(page))
    assert page.stem not in review._simplified_dirty_pages


@pytest.mark.parametrize("mutation", ["other_human", "same_human", "deleted", "invalid_json"])
def test_external_editor_after_cache_load_preserves_foreign_bytes(tmp_path, mutation):
    page, path, review, deps = scene(tmp_path)
    records = review._simplified_page_records(page.stem)
    records["10,20"]["text"] = "our proposed edit"
    if mutation == "deleted":
        path.unlink()
        foreign = None
    elif mutation == "invalid_json":
        foreign = b'{"entries":[,]}'
        path.write_bytes(foreign)
    else:
        rows = {"10,20": {"x": 10, "y": 20, "source_word": "head",
                          "text": "external" if mutation == "same_human" else "manual original",
                          "manual": True}}
        if mutation == "other_human":
            rows["40,50"] = {"x": 40, "y": 50, "source_word": "other",
                              "text": "another person's correction", "manual": True}
        write_records(path, page.stem, rows)
        foreign = path.read_bytes()
    with pytest.raises(RuntimeError, match="修改"):
        ui._persist_simplified_page(review, deps, page.stem)
    assert tx._bytes_or_absent(path) == foreign
    assert not tx._marker_present(tx._recovery_path(page))
    assert page.stem in review._simplified_dirty_pages


def test_missing_source_pin_cannot_rewrite_cached_manual_entries(tmp_path):
    page, path, review, deps = scene(tmp_path)
    review._simplified_page_cache[page.stem] = read_records(path)
    old = path.read_bytes()
    with pytest.raises(RuntimeError, match="来源"):
        ui._persist_simplified_page(review, deps, page.stem)
    assert path.read_bytes() == old


@pytest.mark.parametrize("fault", ["before_publish", "after_publish", "foreign_during_publish"])
def test_rollback_or_quarantine_after_sidecar_publication_fault(tmp_path, monkeypatch, fault):
    page, path, review, deps = scene(tmp_path)
    records = review._simplified_page_records(page.stem)
    records["10,20"]["text"] = "ours"
    old = path.read_bytes()
    original = tx._publish
    foreign = b"new third-party human bytes"

    def inject(target, data):
        if fault == "before_publish":
            raise OSError("before publication")
        original(target, data)
        if fault == "after_publish":
            raise OSError("after publication")
        if fault == "foreign_during_publish":
            path.write_bytes(foreign)
            raise OSError("external writer")

    monkeypatch.setattr(tx, "_publish", inject)
    with pytest.raises((RuntimeError, OSError)):
        ui._persist_simplified_page(review, deps, page.stem)
    if fault == "foreign_during_publish":
        assert path.read_bytes() == foreign
        assert tx._marker_present(tx._recovery_path(page))
    else:
        assert path.read_bytes() == old
        assert not tx._marker_present(tx._recovery_path(page))
    assert page.stem in review._simplified_dirty_pages


def test_foreign_write_during_proposal_does_not_publish(tmp_path):
    page, path, review, deps = scene(tmp_path)
    records = review._simplified_page_records(page.stem)
    records["10,20"]["text"] = "ours"
    foreign = b"foreign external edit"
    original = write_records

    def concurrent_writer(proposal_path, stem, proposed_records):
        original(proposal_path, stem, proposed_records)
        path.write_bytes(foreign)

    deps.write_simplified_records = concurrent_writer
    with pytest.raises(RuntimeError, match="外部修改"):
        ui._persist_simplified_page(review, deps, page.stem)
    assert path.read_bytes() == foreign
    assert not tx._marker_present(tx._recovery_path(page))


@pytest.mark.parametrize("invalid", [
    b"{not-json}",
    b'{"format":"picture_capture_simplified_review","format_version":1,"page":"page","entries":[],"entries":[]}',
    b'{"format":"picture_capture_simplified_review","format_version":1,"page":"page","entries":[],"quality":NaN}',
])
def test_unreadable_or_ambiguous_human_json_is_not_normalized(tmp_path, invalid):
    page, path, review, deps = scene(tmp_path)
    path.write_bytes(invalid)
    records = review._simplified_page_records(page.stem)
    records["10,20"] = {"x": 10, "y": 20, "source_word": "head",
                        "text": "ours", "manual": True}
    with pytest.raises(RuntimeError, match="无损解析"):
        ui._persist_simplified_page(review, deps, page.stem)
    assert path.read_bytes() == invalid
    assert not tx._marker_present(tx._recovery_path(page))


def test_cross_page_cached_write_cannot_modify_original_sidecar(tmp_path):
    page, path, review, deps = scene(tmp_path)
    review._simplified_page_records(page.stem)
    old = path.read_bytes()
    review.parent.current_page = tmp_path / "next.png"
    with pytest.raises(RuntimeError, match="页面"):
        ui._persist_simplified_page(review, deps, page.stem)
    assert path.read_bytes() == old


def test_old_focusout_callback_cannot_modify_other_page_cache(tmp_path):
    page, path, review, deps = scene(tmp_path)
    records = review._simplified_page_records(page.stem)
    original = dict(records)
    review.parent.current_page = tmp_path / "next.png"
    review.row_entries = [SimpleNamespace(x=10, y=20, word="head")]
    review.parent.entries = review.row_entries
    review.vars = [SimpleNamespace(get=lambda: "head")]
    review.simplified_vars = [SimpleNamespace(get=lambda: "changed")]
    review.simplified_actual_values = ["manual original"]
    review.simplified_manual_flags = [True]
    ui._capture_simplified_edits(review, deps, page.stem)
    assert records == original


def test_main_window_review_refusal_never_downgrades_to_raw_write(tmp_path):
    from picture_capture.ui import main_entry_actions as main
    page, path, review, deps = scene(tmp_path)
    row = SimpleNamespace(x=10, y=20, word="head")
    records = review._simplified_page_records(page.stem)
    review._simplified_dirty_pages = set()
    review._persist_simplified_page = lambda stem: (_ for _ in ()).throw(RuntimeError("outside writer"))
    app = SimpleNamespace(current_page=page, review_window=review)
    main_deps = SimpleNamespace(
        simplified_entry_key=lambda x, y: f"{x},{y}",
        simplified_review_path_for_image=simplified_review_path_for_image,
        read_simplified_records=read_records,
        write_simplified_records=write_records,
    )
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="outside writer"):
        main._delete_aligned_simplified_entry(app, main_deps, row)
    assert path.read_bytes() == before
    assert "10,20" in records
    assert not review._simplified_dirty_pages


def test_main_window_without_review_uses_same_guarded_writer(tmp_path):
    from picture_capture.ui import main_entry_actions as main
    page, path, review, deps = scene(tmp_path)
    row = SimpleNamespace(x=10, y=20, word="head")
    app = SimpleNamespace(current_page=page, review_window=None)
    main_deps = SimpleNamespace(
        simplified_entry_key=lambda x, y: f"{x},{y}",
        simplified_review_path_for_image=simplified_review_path_for_image,
        read_simplified_records=read_records,
        write_simplified_records=write_records,
    )
    main._delete_aligned_simplified_entry(app, main_deps, row)
    assert read_records(path) == {}
    assert not tx._marker_present(tx._recovery_path(page))


@pytest.mark.parametrize("external", ["same_row", "new_other_row", "delete_file"])
def test_regenerate_external_manual_edit_rejection_restores_gui_cache(
    tmp_path, external,
):
    from picture_capture.proofreading.simplified_review import entry_key
    page, path, review, deps = scene(tmp_path)
    source_records = review._simplified_page_records(page.stem)
    original_record = dict(source_records["10,20"])
    old_bytes = path.read_bytes()
    row = SimpleNamespace(x=10, y=20, word="head")
    class Buffer:
        def __init__(self, text):
            self.text = text
        def get(self):
            return self.text
        def set(self, value):
            self.text = value
    review.parent.entries = [row]
    review.parent._claim_page_for_manual_edit = lambda: True
    review.parent.status_var = Buffer("")
    review.row_entries = [row]
    review.vars = [Buffer("head")]
    review.simplified_vars = [Buffer("manual original")]
    review.simplified_actual_values = ["manual original"]
    review.simplified_manual_flags = [True]
    review.simplified_auto_refresh_flags = [False]
    review.active_index = -1
    review._simplified_display_from_value = lambda original, actual, manual: actual
    review._refresh_cc_simplified_comparison = lambda index: None
    review._persist_simplified_page = lambda stem: ui._persist_simplified_page(review, deps, stem)
    if external == "delete_file":
        path.unlink()
        third_party = None
    else:
        changed = read_records(path)
        if external == "same_row":
            changed["10,20"]["text"] = "externally corrected"
        else:
            changed["40,50"] = {"x": 40, "y": 50, "source_word": "other",
                                "text": "foreign manual", "manual": True}
        write_records(path, page.stem, changed)
        third_party = path.read_bytes()
        assert third_party != old_bytes
    regen_deps = SimpleNamespace(
        simplified_entry_key=entry_key,
        simplify_text=lambda text: "regen:" + text,
        messagebox=SimpleNamespace(showerror=lambda *args, **kw: None),
    )
    with pytest.raises(RuntimeError, match="修改"):
        ui.regenerate_simplified_current_page(review, regen_deps)
    assert tx._bytes_or_absent(path) == third_party
    assert source_records["10,20"] == original_record
    assert [x.get() for x in review.simplified_vars] == ["manual original"]
    assert review.simplified_manual_flags == [True]
    assert review.simplified_actual_values == ["manual original"]
    assert review.simplified_auto_refresh_flags == [False]
    assert review._simplified_dirty_pages == {page.stem}
    assert review._r3_simplified_source_bytes[page.stem][1] == old_bytes
    assert not tx._marker_present(tx._recovery_path(page))
    assert "已重新简体化" not in review.parent.status_var.get()


def test_regenerate_healthy_commit_updates_disk_and_ui_once(tmp_path):
    from picture_capture.proofreading.simplified_review import entry_key
    page, path, review, deps = scene(tmp_path)
    original = review._simplified_page_records(page.stem)
    before = path.read_bytes()
    row = SimpleNamespace(x=10, y=20, word="head")
    class Buffer:
        def __init__(self, value):
            self.value = value
        def get(self):
            return self.value
        def set(self, value):
            self.value = value
    review.parent.entries = [row]
    review.parent.status_var = Buffer("")
    review.parent._claim_page_for_manual_edit = lambda: True
    review.row_entries = [row]
    review.vars = [Buffer("head")]
    review.simplified_vars = [Buffer("manual original")]
    review.simplified_actual_values = ["manual original"]
    review.simplified_manual_flags = [True]
    review.simplified_auto_refresh_flags = [True]
    review.active_index = -1
    review._simplified_display_from_value = lambda original, actual, manual: actual
    review._refresh_cc_simplified_comparison = lambda index: None
    review._persist_simplified_page = lambda stem: ui._persist_simplified_page(review, deps, stem)
    regen_deps = SimpleNamespace(
        simplified_entry_key=entry_key,
        simplify_text=lambda text: "converted:" + text,
        messagebox=SimpleNamespace(showerror=lambda *args, **kw: None),
    )
    ui.regenerate_simplified_current_page(review, regen_deps)
    assert path.read_bytes() != before
    assert read_records(path)["10,20"] == {
        "x": 10, "y": 20, "source_word": "head",
        "text": "converted:head", "manual": False,
    }
    assert original["10,20"]["text"] == "converted:head"
    assert [v.get() for v in review.simplified_vars] == ["converted:head"]
    assert review.simplified_actual_values == ["converted:head"]
    assert review.simplified_manual_flags == [False]
    assert review.simplified_auto_refresh_flags == [False]
    assert not review._simplified_dirty_pages
    assert review._r3_simplified_source_bytes[page.stem][1] == path.read_bytes()
    assert not tx._marker_present(tx._recovery_path(page))
    assert review.parent.status_var.get().startswith("已重新简体化")
