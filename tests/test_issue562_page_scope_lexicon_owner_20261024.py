"""Native page scope / wordslist owner and behavior contracts (#562)."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture import app as shell
from picture_capture.ui import page_scope_workflow as page_scope
from picture_capture.ui import lexicon_compare_workflow as lexicon

ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture"
GROUPS = [
    ("page_scope_workflow.py", page_scope, "_page_scope", "_page_scope_deps", ["_page_number","_parse_page_spec","selected_page_indices","_paddle_temp_matches_page","cleanup_paddleocr_temp_selected_scope","jump_to_page_spec"]),
    ("lexicon_compare_workflow.py", lexicon, "_lexicon_compare", "_lexicon_compare_deps", ["reload_wordslist_reference","_request_wordslist_reload","import_legacy_words","_default_old_new_compare_source","_looks_page_aware_compare_source","compare_old_new_selected_scope"]),
]


@pytest.mark.parametrize("filename,module,symbol,factory,names", GROUPS)
def test_physical_implementation_delegates_maintain_original_native_abi(
    filename, module, symbol, factory, names,
):
    app_ast = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    app_cls = next(n for n in app_ast.body if isinstance(n, ast.ClassDef)
                   and n.name == "PictureCaptureApp")
    callbacks = {n.name: n for n in app_cls.body if isinstance(n, ast.FunctionDef)}
    owner_ast = ast.parse((ROOT / "ui" / filename).read_text(encoding="utf-8"))
    owned = {n.name: n for n in owner_ast.body if isinstance(n, ast.FunctionDef)}
    assert set(names) <= set(owned)
    for name in names:
        assert name in callbacks
        calls = [n for n in ast.walk(callbacks[name]) if isinstance(n, ast.Call)]
        assert any(isinstance(n.func, ast.Attribute)
                   and isinstance(n.func.value, ast.Name) and n.func.value.id == symbol
                   and n.func.attr == name for n in calls)
        assert any(isinstance(n.func, ast.Name) and n.func.id == factory for n in calls)
        assert list(inspect.signature(getattr(shell.PictureCaptureApp, name)).parameters)
    assert not any(isinstance(n, ast.ImportFrom)
                   and n.module in {"app", "picture_capture.app"}
                   for n in ast.walk(owner_ast))


def test_static_helpers_preserve_callable_class_descriptor_and_match_names():
    cls = shell.PictureCaptureApp
    for method in ("_page_number", "_paddle_temp_matches_page"):
        assert isinstance(cls.__dict__[method], staticmethod)
    assert cls._page_number(Path("0008.png")) == 8
    assert cls._page_number(Path("cover.png")) is None
    assert cls._paddle_temp_matches_page(Path("0008.json"), "0008")
    assert cls._paddle_temp_matches_page(Path("0008_diagnostics.txt"), "0008")
    assert not cls._paddle_temp_matches_page(Path("00081.json"), "0008")
    assert not cls._paddle_temp_matches_page(Path("0008x.json"), "0008")


def test_live_original_module_bindings_are_snapshotted_at_callback(monkeypatch):
    marker = object()
    monkeypatch.setattr(shell, "read_pdic", marker)
    monkeypatch.setattr(shell, "bookmarked_page_indices", marker)
    monkeypatch.setattr(shell, "resolve_wordslist_path", marker)
    assert shell._lexicon_compare_deps().read_pdic is marker
    assert shell._page_scope_deps().bookmarked_page_indices is marker
    assert shell._lexicon_compare_deps().resolve_wordslist_path is marker


def test_page_range_never_silently_expands_into_auxiliary_scans():
    pages = [Path("0000_01.png"), Path("0001.png"), Path("0002.png"),
             Path("0002_01.png"), Path("0003.png")]
    view = SimpleNamespace(
        project=SimpleNamespace(images=pages),
        _page_number=shell.PictureCaptureApp._page_number,
    )
    import re
    deps = SimpleNamespace(re=re)
    assert page_scope._parse_page_spec(view, deps, "1-3") == [1, 2, 4]
    assert page_scope._parse_page_spec(view, deps, "0002") == [2]
    with pytest.raises(ValueError, match="不存在"):
        page_scope._parse_page_spec(view, deps, "1-4")


def test_page_scope_current_bookmark_and_to_specified_selection():
    pages=[Path(f"{i:04d}.png") for i in range(1,6)]
    selector=SimpleNamespace(project=SimpleNamespace(images=pages),current_index=1)
    mode=["current"]
    selector.page_range_var=SimpleNamespace(get=lambda:mode[0])
    selector.page_range_spec_var=SimpleNamespace(get=lambda:"0004")
    selector._bookmark_stems=lambda:["0001","0005"]
    selector._parse_page_spec=lambda s:[3]
    def bookmarked(images,stems):
        return [i for i,p in enumerate(images) if p.stem in stems]
    deps=SimpleNamespace(bookmarked_page_indices=bookmarked)
    assert page_scope.selected_page_indices(selector,deps)==[1]
    mode[0]="bookmarks"
    assert page_scope.selected_page_indices(selector,deps)==[0,4]
    mode[0]="to_specified"
    assert page_scope.selected_page_indices(selector,deps)==[1,2,3]
    mode[0]="to_end"
    assert page_scope.selected_page_indices(selector,deps)==[1,2,3,4]


def test_wordslist_reload_rejects_missing_project_and_preserves_current_state(tmp_path):
    view=SimpleNamespace(project=None)
    deps=shell._lexicon_compare_deps()
    with pytest.raises(ValueError,match="尚未打开项目"):
        lexicon.reload_wordslist_reference(view,deps)
    errors=[]
    lexicon._request_wordslist_reload(view,deps,on_error=lambda e:errors.append(e))
    assert len(errors)==1 and isinstance(errors[0],ValueError)
