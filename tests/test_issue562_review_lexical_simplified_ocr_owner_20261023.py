"""Regression and owner contracts for #562 ReviewWindow lexical/simplified/OCR extraction."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture import app as app_module
from picture_capture.ui import (
    review_lookup_workflow as lookup,
    review_simplified_workflow as simplified,
    review_ocr_compare_workflow as ocr,
)

ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture"
GROUPS = {
    "review_lookup_workflow.py": [
        "_refresh_cc_cedict_button_idle",
        "_set_lookup_source_states",
        "manage_cc_cedict",
        "_cc_simplified_comparison_details",
        "_refresh_cc_simplified_comparison",
        "show_cc_simplified_comparison",
        "open_lookup_source",
        "_toggle_network_lookup",
        "_active_review_word",
        "_schedule_network_lookup",
        "_start_network_lookup",
        "_poll_network_lookup_results",
        "_apply_network_lookup_result",
        "open_network_web_search"
    ],
    "review_simplified_workflow.py": [
        "_bound_row_entries",
        "_simplified_page_records",
        "_simplified_display_from_value",
        "_auto_simplified_value",
        "_capture_simplified_edits",
        "_persist_simplified_page",
        "_simplified_query_for_index",
        "lookup_simplified_online",
        "_focus_simplified_editor",
        "_claim_simplified_clipboard_edit",
        "on_simplified_key",
        "_refresh_simplified_for_index",
        "_refresh_all_simplified",
        "regenerate_simplified_current_page",
        "_apply_simplified_visibility",
        "_toggle_review_simplified"
    ],
    "review_ocr_compare_workflow.py": [
        "_change_review_ocr_compare_source",
        "_ocr_compare_word",
        "_refresh_editor_ocr_compare",
        "_show_ocr_options",
        "_refresh_ocr_similarity_colors",
        "use_ocr_word"
    ]
}
DISPATCH = {
    "review_lookup_workflow.py": ("_review_lookup", "_review_lookup_deps"),
    "review_simplified_workflow.py": ("_review_simplified", "_review_simplified_deps"),
    "review_ocr_compare_workflow.py": ("_review_ocr", "_review_ocr_deps"),
}


@pytest.mark.parametrize("name", list(GROUPS))
def test_canonical_implementation_and_original_tk_adapter(name):
    physical = ast.parse((ROOT / "ui" / name).read_text("utf-8"))
    shell = ast.parse((ROOT / "app.py").read_text("utf-8"))
    owner = {node.name: node for node in physical.body if isinstance(node, ast.FunctionDef)}
    klass = next(node for node in shell.body if isinstance(node, ast.ClassDef) and node.name == "ReviewWindow")
    wrappers = {node.name: node for node in klass.body if isinstance(node, ast.FunctionDef)}
    alias, fac = DISPATCH[name]
    for method in GROUPS[name]:
        assert method in owner and method in wrappers
        statements = [n for n in ast.walk(wrappers[method]) if isinstance(n, ast.Call)]
        assert any(isinstance(n.func, ast.Attribute)
                   and isinstance(n.func.value, ast.Name)
                   and n.func.value.id == alias and n.func.attr == method
                   for n in statements), method
        assert any(isinstance(n.func, ast.Name) and n.func.id == fac for n in statements)
    assert not any(isinstance(n, ast.ImportFrom) and n.module == "app"
                   for n in ast.walk(physical))


def test_legacy_static_and_keyword_defaults_preserved():
    cls = app_module.ReviewWindow
    assert isinstance(inspect.getattr_static(cls, "_simplified_display_from_value"), staticmethod)
    assert list(inspect.signature(cls._simplified_display_from_value).parameters) == [
        "original", "value", "manual",
    ]
    assert inspect.signature(cls._set_lookup_source_states).parameters["pending"].default is False
    assert inspect.signature(cls._schedule_network_lookup).parameters["force"].default is False
    assert inspect.signature(cls._simplified_page_records).parameters["page_stem"].default is None
    assert inspect.signature(cls._refresh_editor_ocr_compare).parameters["index"].default is None


def test_dep_sources_remain_live_for_monkeypatching(monkeypatch):
    patched = object()
    monkeypatch.setattr(app_module, "lookup_word_free", patched)
    monkeypatch.setattr(app_module, "write_simplified_records", patched)
    monkeypatch.setattr(app_module, "_review_similarity_color", patched)
    assert app_module._review_lookup_deps().lookup_word_free is patched
    assert app_module._review_simplified_deps().write_simplified_records is patched
    assert app_module._review_ocr_deps()._review_similarity_color is patched


def test_lookup_stale_serial_never_changes_visible_status():
    changed = []
    view = SimpleNamespace(_network_lookup_serial=8, _network_lookup_word="new",
                           network_lookup_status_var=SimpleNamespace(set=changed.append))
    lookup._apply_network_lookup_result(
        view, SimpleNamespace(tk=SimpleNamespace(TclError=Exception)), 7, "previous", None,
    )
    assert changed == []
    view.network_status_label = SimpleNamespace(configure=lambda **k: None)
    view._set_lookup_source_states = lambda **kw: changed.append(kw)
    lookup._apply_network_lookup_result(
        view, SimpleNamespace(tk=SimpleNamespace(TclError=Exception)), 8, "new", None,
    )
    assert changed[0] == "⚠ 网络词汇核验暂时失败；可点“网络搜索”手工确认。"
    assert changed[1] == {"empty": True}


def test_simplified_manual_edit_keeps_rendered_coordinate_identity():
    source = SimpleNamespace(x=42, y=91, word="甲")
    records = {}
    view = SimpleNamespace(
        parent=SimpleNamespace(current_page=SimpleNamespace(stem="page")),
        simplified_vars=[SimpleNamespace(get=lambda: "乙")],
        simplified_manual_flags=[False],
        simplified_actual_values=["甲"],
        _simplified_dirty_pages=set(),
        _bound_row_entries=lambda: [source],
        _simplified_page_records=lambda stem: records,
        _simplified_display_from_value=lambda original, value, manual: "√",
    )
    simplified._capture_simplified_edits(view, SimpleNamespace(simplified_entry_key=lambda x,y: f"{x}:{y}"), "page")
    assert view.simplified_manual_flags == [True]
    assert records["42:91"] == {"x":42,"y":91,"source_word":"甲","text":"乙","manual":True}
    assert "page" in view._simplified_dirty_pages


def test_simplified_persist_uses_original_page_path_and_clears_dirty_only_after_write():
    written = []
    page = Path("/tmp/project/page.png")
    view = SimpleNamespace(
        parent=SimpleNamespace(project=SimpleNamespace(images=[page]), current_page=page),
        _simplified_dirty_pages={"page"},
        _simplified_page_records=lambda stem: {"42:91": {"text": "乙"}},
    )
    deps = SimpleNamespace(
        simplified_review_path_for_image=lambda p: p.with_suffix(".review.json"),
        write_simplified_records=lambda path, stem, records: written.append((path,stem,records)),
    )
    simplified._persist_simplified_page(view, deps, "page")
    assert written == [(page.with_suffix(".review.json"), "page", {"42:91": {"text": "乙"}})]
    assert view._simplified_dirty_pages == set()


def test_ocr_comparison_uses_selected_engine_while_preserving_empty_neutral():
    view = SimpleNamespace(
        OCR_COMPARE_LABEL_TO_KEY={"P": "paddle", "F": "fusion"},
        review_ocr_compare_var=SimpleNamespace(get=lambda: "P"),
    )
    d = SimpleNamespace(_candidate_word_for_ocr_source=lambda candidate, source:
                        candidate.get(source,"") if candidate else "")
    assert ocr._ocr_compare_word(view, d, {"paddle":"ABC","fusion":"XYZ"}) == "ABC"
    assert ocr._ocr_compare_word(view, d, None) == ""
