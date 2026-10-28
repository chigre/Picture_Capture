"""G1/G2 rendered Tk Entry ownership: generated inputs, no private scans."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui import review_simplified_workflow as owner


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def case(*, n=2):
    rows = [SimpleNamespace(x=10 + i * 10, y=20 + i * 10,
                            word=f"word{i}") for i in range(n)]
    page = SimpleNamespace(stem="page", name="page.png")
    records, calls, idle = {}, [], []
    app = SimpleNamespace(
        current_page=page, entries=list(rows),
        _ordered_entries_reading_order=lambda: list(reversed(rows)),
        _claim_page_for_manual_edit=lambda: calls.append("claim") or True,
        status_var=Var(""),
    )
    view = SimpleNamespace(
        parent=app, row_entries=list(rows), _rendered_page_stem="page",
        vars=[Var(r.word) for r in rows],
        simplified_vars=[Var(f"manual{i}") for i in range(n)],
        simplified_manual_flags=[False] * n,
        simplified_actual_values=[None] * n,
        simplified_auto_refresh_flags=[False] * n,
        simplified_editors=[object() for _ in rows],
        _simplified_dirty_pages=set(),
        _simplified_page_records=lambda stem: records,
        _simplified_display_from_value=lambda original, actual, manual: "√",
        _auto_simplified_value=lambda original, fallback=None: "auto:" + original,
        _refresh_cc_simplified_comparison=lambda index: calls.append(("refresh", index)),
        _persist_simplified_page=lambda stem: calls.append(("persist", stem)),
        after_idle=idle.append, active_index=-1,
    )
    view.on_simplified_key = lambda event, index: owner.on_simplified_key(view, deps, event, index)
    deps = SimpleNamespace(
        simplified_entry_key=lambda x, y: f"{x}:{y}",
        simplify_text=lambda word: "converted:" + word,
        messagebox=SimpleNamespace(showerror=lambda *a, **kw: calls.append("error")),
    )
    return view, deps, rows, records, calls, idle


def test_manual_key_uses_rendered_entry_not_resorted_section_row():
    view, deps, rows, records, calls, _ = case()
    owner.on_simplified_key(view, deps, SimpleNamespace(widget=view.simplified_editors[0]), 0)
    assert records == {"10:20": {"x": 10, "y": 20, "source_word": "word0",
                                 "text": "manual0", "manual": True}}
    assert view.simplified_manual_flags == [True, False]
    assert view._simplified_dirty_pages == {"page"}
    assert "claim" in calls
    assert "20:30" not in records


@pytest.mark.parametrize("fault", [
    "page_changed", "render_stem_changed", "deleted_entry", "duplicated_entry",
    "duplicate_pixel_coordinate", "missing_bound", "partial_render",
    "partial_simplified_values", "filter_mode",
])
def test_manual_key_stale_or_unowned_row_has_no_mutation(fault):
    view, deps, rows, records, calls, _ = case()
    if fault == "page_changed":
        view.parent.current_page = SimpleNamespace(stem="next", name="next.png")
    elif fault == "render_stem_changed":
        view._rendered_page_stem = "other"
    elif fault == "deleted_entry":
        view.parent.entries.pop(0)
    elif fault == "duplicated_entry":
        view.row_entries[1] = view.row_entries[0]
    elif fault == "duplicate_pixel_coordinate":
        rows[1].x, rows[1].y = rows[0].x, rows[0].y
    elif fault == "missing_bound":
        del view.row_entries
    elif fault == "partial_render":
        view.row_entries.pop()
    elif fault == "partial_simplified_values":
        view.simplified_actual_values.pop()
    else:
        view._filter_rows_active = True
    owner.on_simplified_key(view, deps, SimpleNamespace(), 0)
    assert records == {}
    assert view.simplified_manual_flags == [False, False]
    assert view.simplified_actual_values == ([None] if fault == "partial_simplified_values"
                                            else [None, None])
    assert view._simplified_dirty_pages == set()
    assert calls == []


def test_stale_keyrelease_widget_cannot_rebind_same_index():
    view, deps, _, records, calls, _ = case()
    owner.on_simplified_key(view, deps, SimpleNamespace(widget=object()), 0)
    assert records == {} and calls == []


@pytest.mark.parametrize("fault", ["navigate", "replace_row", "change_word", "change_simplified"])
def test_manual_claim_race_refuses_before_sidecar_and_flags(fault):
    view, deps, rows, records, calls, _ = case()
    def claim():
        calls.append("claim")
        if fault == "navigate":
            view.parent.current_page = SimpleNamespace(stem="next")
        elif fault == "replace_row":
            view.row_entries[0] = SimpleNamespace(x=10, y=20, word="word0")
            view.parent.entries[0] = view.row_entries[0]
        elif fault == "change_word":
            view.vars[0].set("changed while claiming")
        else:
            view.simplified_vars[0].set("changed while claiming")
        return True
    view.parent._claim_page_for_manual_edit = claim
    owner.on_simplified_key(view, deps, SimpleNamespace(), 0)
    assert records == {}
    assert view.simplified_manual_flags == [False, False]
    assert view._simplified_dirty_pages == set()
    assert calls == ["claim"]


def test_delayed_clipboard_callback_retains_frozen_entry_identity():
    view, deps, _, records, calls, idle = case()
    assert owner._claim_simplified_clipboard_edit(view, deps, 0) is None
    assert len(idle) == 1
    view.row_entries.reverse()
    idle.pop()()
    assert records == {}
    assert view.simplified_manual_flags == [False, False]
    assert calls == ["claim"]


def test_delayed_clipboard_normal_case_updates_only_bound_row():
    view, deps, _, records, calls, idle = case()
    assert owner._claim_simplified_clipboard_edit(view, deps, 0) is None
    idle.pop()()
    assert list(records) == ["10:20"]
    assert view.simplified_manual_flags == [True, False]


@pytest.mark.parametrize("fault", [
    "page_changed", "partial_render", "deleted_entry", "duplicate_pixel_coordinate",
])
def test_auto_refresh_does_not_reassign_stale_coordinates(fault):
    view, deps, rows, records, calls, _ = case()
    view.simplified_auto_refresh_flags[0] = True
    if fault == "page_changed":
        view.parent.current_page = SimpleNamespace(stem="next")
    elif fault == "partial_render":
        view.row_entries.pop()
    elif fault == "deleted_entry":
        view.parent.entries.pop()
    else:
        rows[1].x, rows[1].y = rows[0].x, rows[0].y
    original = view.simplified_vars[0].get()
    owner._refresh_simplified_for_index(view, deps, 0)
    assert view.simplified_vars[0].get() == original
    assert records == {} and view._simplified_dirty_pages == set()


def test_auto_refresh_normal_reordered_rows_uses_original_pixel_identity():
    view, deps, _, records, calls, _ = case()
    view.simplified_auto_refresh_flags[0] = True
    owner._refresh_simplified_for_index(view, deps, 0)
    assert records == {"10:20": {"x": 10, "y": 20, "source_word": "word0",
                                 "text": "auto:word0", "manual": False}}
    # The rendered display can legitimately be a check-mark placeholder;
    # the actual converted bytes and source X/Y must still match.
    assert view.simplified_vars[0].get() == "√"
    assert view.simplified_actual_values[0] == "auto:word0"


@pytest.mark.parametrize("fault", [
    "page_changed", "partial_render", "duplicate_pixel_coordinate", "missing_bound",
])
def test_regenerate_refuses_ambiguous_whole_page_without_persist(fault):
    view, deps, rows, records, calls, _ = case()
    if fault == "page_changed":
        view.parent.current_page = SimpleNamespace(stem="next")
    elif fault == "partial_render":
        view.row_entries.pop()
    elif fault == "duplicate_pixel_coordinate":
        rows[1].x, rows[1].y = rows[0].x, rows[0].y
    else:
        del view.row_entries
    owner.regenerate_simplified_current_page(view, deps)
    assert records == {} and calls == []
    assert view.simplified_manual_flags == [False, False]


def test_regenerate_normal_preserves_bound_coordinates_and_persists():
    view, deps, _, records, calls, _ = case()
    owner.regenerate_simplified_current_page(view, deps)
    assert list(records) == ["10:20", "20:30"]
    assert [records[k]["source_word"] for k in records] == ["word0", "word1"]
    assert [records[k]["text"] for k in records] == [
        "converted:word0", "converted:word1",
    ]
    assert ("persist", "page") in calls
    assert view._simplified_dirty_pages == {"page"}


@pytest.mark.parametrize("fault", ["navigate", "change_word", "change_row"])
def test_regenerate_claim_race_does_not_replace_human_values(fault):
    view, deps, _, records, calls, _ = case()
    if fault == "navigate":
        def claim():
            view.parent.current_page = SimpleNamespace(stem="next")
            return True
    elif fault == "change_word":
        def claim():
            view.vars[0].set("human typing")
            return True
    else:
        def claim():
            view.row_entries[0] = SimpleNamespace(x=10, y=20, word="word0")
            view.parent.entries[0] = view.row_entries[0]
            return True
    view.parent._claim_page_for_manual_edit = claim
    owner.regenerate_simplified_current_page(view, deps)
    assert records == {} and ("persist", "page") not in calls
    assert view.simplified_actual_values == [None, None]
    assert view.simplified_manual_flags == [False, False]


@pytest.mark.parametrize("dirty_before", [False, True])
@pytest.mark.parametrize("failure", ["before_publish", "after_partial_ui", "foreign_in_cache"])
def test_regenerate_failed_persist_restores_existing_manual_page(
    dirty_before, failure,
):
    """A refused whole-page save must not masquerade as regenerated manual text."""
    view, deps, rows, records, calls, _ = case()
    original = {
        "10:20": {"x": 10, "y": 20, "source_word": "word0",
                  "text": "hand0", "manual": True},
        "20:30": {"x": 20, "y": 30, "source_word": "word1",
                  "text": "hand1", "manual": True},
        "999:999": {"text": "unrelated human entry"},
    }
    records.update({k: dict(v) for k, v in original.items()})
    for i in range(2):
        view.simplified_vars[i].set(f"hand{i}")
    view.simplified_actual_values[:] = ["hand0", "hand1"]
    view.simplified_manual_flags[:] = [True, True]
    view.simplified_auto_refresh_flags[:] = [True, True]
    if dirty_before:
        view._simplified_dirty_pages.add("page")
    def persist(_stem):
        calls.append("persist_called")
        if failure == "foreign_in_cache":
            # Simulate synchronous editor reentrancy while disk commit refuses.
            records["999:999"] = {"text": "third-party newer edit"}
        raise RuntimeError(failure)
    view._persist_simplified_page = persist
    with pytest.raises(RuntimeError, match=failure):
        owner.regenerate_simplified_current_page(view, deps)
    assert [v.get() for v in view.simplified_vars] == ["hand0", "hand1"]
    assert view.simplified_actual_values == ["hand0", "hand1"]
    assert view.simplified_manual_flags == [True, True]
    assert view.simplified_auto_refresh_flags == [True, True]
    assert records["10:20"] == original["10:20"]
    assert records["20:30"] == original["20:30"]
    assert records["999:999"] == (
        {"text": "third-party newer edit"} if failure == "foreign_in_cache"
        else original["999:999"]
    )
    assert view._simplified_dirty_pages == (
        {"page"} if dirty_before or failure == "foreign_in_cache" else set()
    )
    assert not any(isinstance(x, tuple) and x[0] == "refresh" for x in calls)
    assert not view.parent.status_var.get().startswith("已重新简体化")


def test_regenerate_widget_exception_midpage_restores_prior_human_values():
    view, deps, _, records, calls, _ = case()
    before = {"10:20": {"text": "human0"}, "20:30": {"text": "human1"}}
    records.update({k: dict(v) for k, v in before.items()})
    view.simplified_manual_flags[:] = [True, True]
    view.simplified_actual_values[:] = ["human0", "human1"]
    view.simplified_auto_refresh_flags[:] = [True, True]
    class FailingOnce(Var):
        def __init__(self, value):
            super().__init__(value)
            self.fail = True
        def set(self, value):
            if self.fail:
                self.fail = False
                raise RuntimeError("Tk widget removed mid-regeneration")
            super().set(value)
    view.simplified_vars[1] = FailingOnce("manual1")
    with pytest.raises(RuntimeError, match="Tk widget removed"):
        owner.regenerate_simplified_current_page(view, deps)
    assert [v.get() for v in view.simplified_vars] == ["manual0", "manual1"]
    assert view.simplified_actual_values == ["human0", "human1"]
    assert view.simplified_manual_flags == [True, True]
    assert view.simplified_auto_refresh_flags == [True, True]
    assert records == before
    assert "page" not in view._simplified_dirty_pages
    assert not any(isinstance(x, tuple) and x[0] == "persist" for x in calls)


def test_regenerate_failure_preserves_newer_reentrant_widget_text():
    view, deps, _, records, calls, _ = case()
    records["10:20"] = {"text": "human0"}
    view.simplified_manual_flags[:] = [True, True]
    view.simplified_actual_values[:] = ["human0", "human1"]
    def persist(_stem):
        view.simplified_vars[0].set("newer typing")
        records["10:20"] = {"text": "newer saved edit", "manual": True}
        raise RuntimeError("concurrent edit")
    view._persist_simplified_page = persist
    with pytest.raises(RuntimeError, match="concurrent edit"):
        owner.regenerate_simplified_current_page(view, deps)
    assert view.simplified_vars[0].get() == "newer typing"
    assert records["10:20"]["text"] == "newer saved edit"
    assert "page" in view._simplified_dirty_pages
