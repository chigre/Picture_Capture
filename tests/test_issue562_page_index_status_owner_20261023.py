"""Page-index and saved word-fill status owner contracts for Issue #562."""
from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture import app as shell
from picture_capture.ui import page_index_workflow as page_index
from picture_capture.ui import word_fill_status_workflow as status


ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture"
GROUPS = {
    "page_index_workflow.py": [
        "_resize_sidebar_content",
        "_apply_page_list_display_columns",
        "_page_list_configured",
        "_fit_page_list_columns",
        "_hide_page_list_section_heading_hint",
        "_page_list_section_heading_motion",
        "_page_list_right_click",
        "_schedule_page_cell_overlay_refresh",
        "_page_list_scroll",
        "_page_list_hscroll",
        "_page_list_yscroll",
        "_update_page_list_sort_headings",
        "_apply_page_list_sort",
        "_schedule_page_list_resort",
        "_sort_page_list",
        "_page_list_column_at",
        "_page_section_count_text",
        "_set_page_section_count",
        "_edit_page_section_index",
        "toggle_current_page_section_editing",
        "_page_list_section_double_click",
        "_bookmark_stems",
        "_page_list_bookmark_click",
        "jump_to_bookmark",
        "_center_page_list_iid",
        "_set_page_list_selection",
        "_clear_lined_cell_overlays",
        "_visible_page_list_iids",
        "_refresh_lined_cell_overlays",
        "_page_metadata",
        "_page_illustration_count_text",
        "_update_page_row",
        "_refresh_page_metadata_step",
        "_refresh_page_quality_colors"
    ],
    "word_fill_status_workflow.py": [
        "_word_fill_status_path",
        "_load_word_fill_status",
        "_persist_word_fill_status",
        "_word_fill_status_text",
        "_record_word_fill_check",
        "_refresh_word_fill_check_from_line_count",
        "_clear_word_fill_checks_for_indices"
    ]
}
SYMBOLS = {
    "page_index_workflow.py": ("_page_index", "_page_index_deps"),
    "word_fill_status_workflow.py": ("_word_fill_status", "_word_fill_status_deps"),
}


@pytest.mark.parametrize("filename", list(GROUPS))
def test_physical_ownership_native_signature_and_explicit_dispatch(filename):
    app_tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    klass = next(n for n in app_tree.body if isinstance(n, ast.ClassDef)
                 and n.name == "PictureCaptureApp")
    wrappers = {n.name: n for n in klass.body if isinstance(n, ast.FunctionDef)}
    module_ast = ast.parse((ROOT / "ui" / filename).read_text(encoding="utf-8"))
    owners = {n.name: n for n in module_ast.body if isinstance(n, ast.FunctionDef)}
    symbol, factory = SYMBOLS[filename]
    for name in GROUPS[filename]:
        assert name in wrappers and name in owners
        dispatch = [n for n in ast.walk(wrappers[name]) if isinstance(n, ast.Call)]
        assert any(isinstance(n.func, ast.Attribute) and n.func.attr == name
                   and isinstance(n.func.value, ast.Name) and n.func.value.id == symbol
                   for n in dispatch)
        assert any(isinstance(n.func, ast.Name) and n.func.id == factory
                   for n in dispatch)
        params = inspect.signature(getattr(shell.PictureCaptureApp, name)).parameters
        assert list(params)[0] == "self", name
    assert not any(isinstance(n, ast.ImportFrom) and n.module == "app"
                   for n in ast.walk(module_ast))


def test_native_keyword_only_contracts_and_callback_varargs():
    cls = shell.PictureCaptureApp
    assert inspect.signature(cls._set_page_list_selection).parameters["ensure_visible"].kind is inspect.Parameter.KEYWORD_ONLY
    assert inspect.signature(cls._apply_page_list_sort).parameters["ensure_current_visible"].default is False
    assert inspect.signature(cls._record_word_fill_check).parameters["persist"].default is False
    assert inspect.signature(cls._page_list_scroll).parameters["args"].kind is inspect.Parameter.VAR_POSITIONAL


def test_live_original_module_helpers_bound_each_event(monkeypatch):
    marker = object()
    monkeypatch.setattr(shell, "_sorted_page_list_rows", marker)
    monkeypatch.setattr(shell, "read_page_sections", marker)
    monkeypatch.setattr(shell, "word_fill_status_path", marker)
    monkeypatch.setattr(shell, "_natural_text_key", marker)
    assert shell._page_index_deps()._sorted_page_list_rows is marker
    assert shell._page_index_deps().read_page_sections is marker
    assert shell._word_fill_status_deps().word_fill_status_path is marker
    assert shell._page_index_deps()._natural_text_key is marker


def test_word_fill_status_roundtrip_and_v1_legacy_state(tmp_path):
    pages = [tmp_path / "one.png", tmp_path / "two.png"]
    sidecar = tmp_path / "word_fill_check.json"
    view = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path, images=pages),
        _word_fill_check_status={},
        _word_fill_mismatch_pages=set(),
        _word_fill_status_path=lambda: sidecar,
    )
    dependencies = SimpleNamespace(json=json, os=__import__("os"))
    view._record_word_fill_check = lambda *args, **kw: status._record_word_fill_check(
        view, dependencies, *args, **kw,
    )
    view._persist_word_fill_status = lambda: status._persist_word_fill_status(view, dependencies)
    view._record_word_fill_check(0, 6, 4, source="TXT", persist=True)
    assert sidecar.exists()
    raw = json.loads(sidecar.read_text("utf-8"))
    assert raw["version"] == 2
    assert raw["pages"]["one"]["state"] == "mismatch"
    assert 0 in view._word_fill_mismatch_pages
    view._word_fill_check_status = {}
    view._word_fill_mismatch_pages.clear()
    status._load_word_fill_status(view, dependencies)
    assert view._word_fill_check_status["one"]["source"] == "TXT"
    assert 0 in view._word_fill_mismatch_pages
    sidecar.write_text(json.dumps({"version": 1, "pages": {
        "two": {"line_count": 5, "word_count": 3, "mismatch": True},
    }}), "utf-8")
    status._load_word_fill_status(view, dependencies)
    assert view._word_fill_check_status["two"]["state"] == "mismatch"
    assert view._word_fill_check_status["two"]["word_count"] == 3


def test_stale_status_only_when_line_count_changes():
    updates = []
    view = SimpleNamespace(
        project=SimpleNamespace(images=[Path("A.png")]),
        _word_fill_check_status={"A": {"state": "mismatch", "line_count": 4,
                                        "word_count": 2, "mismatch": True}},
        _word_fill_mismatch_pages={0},
        _persist_word_fill_status=lambda: updates.append("persist"),
    )
    status._refresh_word_fill_check_from_line_count(view, SimpleNamespace(), 0, 4, persist=True)
    assert view._word_fill_check_status["A"]["state"] == "mismatch" and updates == []
    status._refresh_word_fill_check_from_line_count(view, SimpleNamespace(), 0, 5, persist=True)
    assert view._word_fill_check_status["A"]["state"] == "stale"
    assert view._word_fill_check_status["A"]["mismatch"] is False
    assert 0 not in view._word_fill_mismatch_pages and updates == ["persist"]


def test_fill_status_summaries_and_unchecked_defaults():
    project = SimpleNamespace(images=[Path("one.png")])
    view = SimpleNamespace(project=project, _word_fill_check_status={})
    assert status._word_fill_status_text(view, SimpleNamespace(), 0) == "未核对"
    view._word_fill_check_status["one"] = {"state": "match", "line_count": 4, "word_count": 4}
    assert status._word_fill_status_text(view, SimpleNamespace(), 0) == "一致"
    view._word_fill_check_status["one"] = {"state": "mismatch", "line_count": 5, "word_count": 3}
    assert status._word_fill_status_text(view, SimpleNamespace(), 0) == "多 2"
    view._word_fill_check_status["one"]["state"] = "no_data"
    assert status._word_fill_status_text(view, SimpleNamespace(), 0) == "无资料"


def test_background_sort_never_autoscrolls_to_selected():
    calls = []
    rows = {"0": ("alpha",), "1": ("beta",)}
    tree = SimpleNamespace(
        item=lambda iid, key: rows[iid],
        get_children=lambda root: list(rows),
        move=lambda *args: calls.append(("move", args)),
        exists=lambda iid: True,
        see=lambda iid: calls.append(("see", iid)),
    )
    view = SimpleNamespace(
        page_list=tree, _page_list_sort_column="page", _page_list_sort_descending=False,
        current_index=1,
        _update_page_list_sort_headings=lambda: None,
        _schedule_page_cell_overlay_refresh=lambda: None,
        _center_page_list_iid=lambda iid: calls.append(("center", iid)),
    )
    deps = SimpleNamespace(_sorted_page_list_rows=lambda given, *_: given)
    page_index._apply_page_list_sort(view, deps)
    assert not any(item[0] in {"see", "center"} for item in calls)
    page_index._apply_page_list_sort(view, deps, ensure_current_visible=True)
    assert ("see", "1") in calls and ("center", "1") in calls


def test_bookmark_stems_ignores_empty_names():
    view = SimpleNamespace(settings=SimpleNamespace(page_bookmarks=["a", "", " ", "b"]))
    assert page_index._bookmark_stems(view, SimpleNamespace()) == {"a", "b"}


def test_section_count_unchanged_source_bounds_are_retained():
    original = [SimpleNamespace(top=10, bottom=75), SimpleNamespace(top=75, bottom=140)]
    written = []
    image = SimpleNamespace(size=(150, 160))
    geometry = SimpleNamespace(top=10, bottom=140)
    parent = SimpleNamespace(images=[Path("x.png")])
    view = SimpleNamespace(
        project=parent, current_index=0, current_page=parent.images[0], image=image,
        settings=SimpleNamespace(layout_transform="identity"),
        _get_cached_display_geometry=lambda: geometry,
        page_sections=[],
        _sort_entries_reading_order=lambda: None,
        _set_section_editing=lambda active: None,
        redraw=lambda: None,
        status_var=SimpleNamespace(set=lambda text: None),
    )
    deps = SimpleNamespace(
        read_page_sections=lambda _: original,
        Image=object(), normalize_page_rgb=object(),
        page_template_analysis_image=object(), derive_geometry=object(),
        PageSection=object(),
        effective_page_settings=lambda settings, size, index: settings,
        LayoutTransform=lambda kind: SimpleNamespace(kind=kind,
                                                       canonical_size=lambda s: s),
        write_page_sections=lambda path, sections, **kwargs: written.append((sections, kwargs)),
    )
    page_index._set_page_section_count(view, deps, 0, 2)
    assert len(written) == 1
    assert written[0][0] is original
    assert written[0][1]["canonical_width"] == 150
    assert written[0][1]["canonical_height"] == 160


def test_page_cell_visible_row_scanner_uses_injected_live_helper():
    calls = []
    tree = object()
    view = SimpleNamespace(page_list=tree)
    fake_deps = SimpleNamespace(visible_page_iids=lambda w: calls.append(w) or ["11", "12"])
    assert page_index._visible_page_list_iids(view, fake_deps) == ["11", "12"]
    assert calls == [tree]
