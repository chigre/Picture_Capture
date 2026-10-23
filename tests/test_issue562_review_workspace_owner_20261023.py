"""#562 review Tk owner migration and binding compatibility."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture import app as app_module
from picture_capture.ui import review_workspace_workflow as leaf

PACKAGE = Path(__file__).resolve().parents[1] / "src/picture_capture"


def test_review_owner_holds_full_functions_and_no_heavy_app_import():
    tree = ast.parse((PACKAGE / "ui/review_workspace_workflow.py").read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in ("_build", "_request_render_rows", "render_rows"):
        assert len(functions[name].body) > 10
    assert not any(
        isinstance(n, ast.ImportFrom) and n.module in {"app", "processing"}
        for n in ast.walk(tree)
    )


def test_review_original_signatures_remain_compatible():
    cls = app_module.ReviewWindow
    assert list(inspect.signature(cls._build).parameters) == ["self"]
    signature = inspect.signature(cls._request_render_rows)
    assert list(signature.parameters) == ["self", "focus_index", "reset_scroll"]
    assert signature.parameters["focus_index"].default is None
    assert signature.parameters["reset_scroll"].default is False
    signature = inspect.signature(cls.render_rows)
    assert list(signature.parameters) == ["self", "preloaded_crops"]
    assert signature.parameters["preloaded_crops"].default is None


def test_review_callbacks_delegate_and_preserve_arguments(monkeypatch):
    events = []
    monkeypatch.setattr(leaf, "_build", lambda self, deps: events.append(("build", self, deps)))
    monkeypatch.setattr(
        leaf, "_request_render_rows",
        lambda self, deps, *, focus_index=None, reset_scroll=False:
            events.append(("request", self, deps, focus_index, reset_scroll)),
    )
    monkeypatch.setattr(
        leaf, "render_rows", lambda self, deps, preloaded_crops=None:
        events.append(("render", self, deps, preloaded_crops)),
    )
    owner = SimpleNamespace()
    app_module.ReviewWindow._build(owner)
    app_module.ReviewWindow._request_render_rows(owner, focus_index=2, reset_scroll=True)
    preloaded = []
    app_module.ReviewWindow.render_rows(owner, preloaded)
    assert [x[0] for x in events] == ["build", "request", "render"]
    assert all(x[1] is owner and isinstance(x[2], leaf.ReviewWorkspaceDeps) for x in events)
    assert events[1][3:] == (2, True)
    assert events[2][3] is preloaded


def test_review_deps_capture_live_module_patchpoints(monkeypatch):
    patched = object()
    monkeypatch.setattr(app_module, "review_auto_fit_zoom", patched)
    assert app_module._review_workspace_deps().review_auto_fit_zoom is patched
    assert len(leaf.ReviewWorkspaceDeps.__dataclass_fields__) == 18
    font_token = object()
    monkeypatch.setattr(app_module, "AUTO_FONT_FAMILY", font_token)
    assert app_module._review_workspace_deps().AUTO_FONT_FAMILY is font_token
