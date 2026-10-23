"""#562 main canvas pointer owner, Tk dispatch and compatibility guards."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture import app as gui
from picture_capture.ui import canvas_pointer_workflow as owner

PKG = Path(__file__).resolve().parents[1] / "src/picture_capture"
METHOD_NAMES = ["_sync_polygon_label_texts","_nearest_polygon_vertex","_nearest_polygon_edge","_delete_polygon_region","_polygon_label_canvas_position","_update_polygon_canvas_geometry","_set_section_editing","_restore_cursor_guides_after_section_edit","_finish_section_editing","_nearest_section_boundary","_drag_page_section_boundary_to","toggle_polygon_drawing","canvas_left_click","canvas_left_drag","canvas_left_release","canvas_right_click"]


def test_canonical_pointer_owns_methods_and_no_heavy_app_import():
    tree = ast.parse((PKG / "ui/canvas_pointer_workflow.py").read_text("utf-8"))
    methods = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name in METHOD_NAMES:
        assert len(methods[name].body) > 2
        # All migrated functions are ordinary module functions; decorators
        # on adjacent legacy staticmethods belong only to app.py.
        assert methods[name].decorator_list == []
    assert not any(
        isinstance(n, ast.ImportFrom) and n.module in {"app", "processing"}
        for n in ast.walk(tree)
    )


def test_original_signatures_forward_without_instantiating_gui(monkeypatch):
    cls = gui.PictureCaptureApp
    calls = []
    for name in METHOD_NAMES:
        original = getattr(cls, name)
        assert inspect.signature(original).parameters
        monkeypatch.setattr(owner, name, lambda app, deps, *args, name=name:
                            calls.append((name, app, deps, args)))
    target = SimpleNamespace()
    event = object()
    region = object()
    cls._sync_polygon_label_texts(target)
    cls._nearest_polygon_vertex(target, 12, 12, 9.0)
    cls._nearest_polygon_edge(target, 12, 12, 9.0)
    cls._delete_polygon_region(target, region)
    cls._polygon_label_canvas_position(target, region, event)
    cls._update_polygon_canvas_geometry(target, 2)
    cls._set_section_editing(target, True)
    cls._restore_cursor_guides_after_section_edit(target)
    cls._finish_section_editing(target)
    cls._nearest_section_boundary(target, 12, 12)
    cls._drag_page_section_boundary_to(target, 12, 12)
    cls.toggle_polygon_drawing(target)
    cls.canvas_left_click(target, event)
    cls.canvas_left_drag(target, event)
    cls.canvas_left_release(target, event)
    cls.canvas_right_click(target, event)
    assert [x[0] for x in calls] == METHOD_NAMES
    assert all(x[1] is target and isinstance(x[2], owner.CanvasPointerDeps)
               for x in calls)


def test_pointer_live_dependency_patchpoints(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(gui, "nearest_polygon_segment", sentinel)
    assert gui._canvas_pointer_deps().nearest_polygon_segment is sentinel
    monkeypatch.setattr(gui, "PageSection", sentinel)
    assert gui._canvas_pointer_deps().PageSection is sentinel
    assert len(owner.CanvasPointerDeps.__dataclass_fields__) == 12


def test_original_static_geometry_contract_is_retained():
    cls = gui.PictureCaptureApp
    for name in ("_rectangle_bounds", "_set_rectangle_side",
                 "_external_polygon_label_position"):
        assert isinstance(inspect.getattr_static(cls, name), staticmethod)
    source = (PKG / "ui/canvas_pointer_workflow.py").read_text("utf-8")
    assert "from .workspace_mode_shortcuts import refresh_workspace_mode_shortcut_buttons" in source
