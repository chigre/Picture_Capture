"""#562 focused filter scan/crop/row owner and compatibility regression."""
from __future__ import annotations
import ast
import inspect
from pathlib import Path
from types import SimpleNamespace
from picture_capture import app as gui
from picture_capture.ui import focused_filter_workflow as owner

ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture"
NAMES = ["run_focused_filter","_focused_batch_size","_filter_available_target_count","_update_filter_batch_indicator","_filter_batch_snapshot","_prepare_filter_batch_payload","_cache_filter_batch_payload","_apply_filter_batch_payload","_schedule_filter_next_batch_preload","change_filter_batch","_request_filter_batch_render","_render_filter_batch"]

def test_focused_filter_physical_ownership_and_no_heavy_import():
    tree = ast.parse((ROOT / "ui/focused_filter_workflow.py").read_text("utf-8"))
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name in NAMES:
        assert functions[name].end_lineno - functions[name].lineno >= 4
        assert functions[name].decorator_list == []
    assert not any(isinstance(n, ast.ImportFrom) and n.module in {"app", "processing"}
                   for n in ast.walk(tree))

def test_focused_filter_signatures_and_live_forwarding(monkeypatch):
    cls = gui.ReviewWindow
    assert list(inspect.signature(cls.run_focused_filter).parameters) == ["self"]
    assert list(inspect.signature(cls._render_filter_batch).parameters) == ["self", "targets", "crops"]
    assert list(inspect.signature(cls._prepare_filter_batch_payload).parameters) == [
        "targets", "pages", "settings", "viewer_width", "available_width", "review_zoom", "review_zoom_auto"]
    assert isinstance(inspect.getattr_static(cls, "_prepare_filter_batch_payload"), staticmethod)
    calls = []
    for name in NAMES:
        monkeypatch.setattr(owner, name, lambda *args, _name=name: calls.append((_name, args)))
    fake = SimpleNamespace()
    cls.run_focused_filter(fake)
    cls._focused_batch_size(fake)
    cls._filter_available_target_count(fake)
    cls._update_filter_batch_indicator(fake)
    cls._filter_batch_snapshot(fake, 0)
    cls._cache_filter_batch_payload(fake, (0, ()), ())
    cls._apply_filter_batch_payload(fake, 0, (0, ()), ())
    cls._schedule_filter_next_batch_preload(fake)
    cls.change_filter_batch(fake, 1)
    cls._request_filter_batch_render(fake)
    cls._render_filter_batch(fake, [], [])
    cls._prepare_filter_batch_payload([], [], None, 10, 250, 1.0, False)
    assert [name for name, _ in calls] == [n for n in NAMES if n != "_prepare_filter_batch_payload"] + ["_prepare_filter_batch_payload"]
    assert all(args[0] is fake and isinstance(args[1], owner.FocusedFilterDeps) for _, args in calls[:-1])
    assert isinstance(calls[-1][1][0], owner.FocusedFilterDeps)

def test_focused_live_module_patchpoints(monkeypatch):
    token = object()
    monkeypatch.setattr(gui, "messagebox", token)
    assert gui._focused_filter_deps().messagebox is token
    monkeypatch.setattr(gui, "review_auto_fit_zoom", token)
    assert gui._focused_filter_deps().review_auto_fit_zoom is token
    assert len(owner.FocusedFilterDeps.__dataclass_fields__) == 27
