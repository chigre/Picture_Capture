"""Issue #562: physical owners for main canvas, PPP and quick-settings behaviors."""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from picture_capture import app
from picture_capture.ui import canvas_pointer_workflow as pointer
from picture_capture.ui import quick_settings_apply as quick
from picture_capture.ui import main_app_lifecycle as lifecycle
from picture_capture.ui.controllers.canvas import CanvasController


def test_physical_ui_owners_and_public_methods_are_retained():
    cases = {
        pointer: ("_polygon_display_name", "_set_polygon_display_name",
            "_update_polygon_label", "_commit_polygon_label_return",
            "_rectangle_bounds", "_set_rectangle_side",
            "_external_polygon_label_position", "_section_gap_entry_count"),
        quick: ("_style_color_button", "choose_overlay_color",
            "_apply_overlay_visibility_toggle", "_run_quick_autosave",
            "_refresh_quick_coordinate_labels"),
        lifecycle: ("guard",),
    }
    for owner, names in cases.items():
        for name in names:
            assert callable(getattr(app.PictureCaptureApp, name))
            assert callable(getattr(owner, name))
            assert "return " in inspect.getsource(getattr(app.PictureCaptureApp, name))
            assert len(inspect.getsource(getattr(owner, name)).splitlines()) >= 4
    assert "self._canvas_controller_for_call()" in inspect.getsource(app.PictureCaptureApp.fit_single_column_width)
    assert "available / fit_width" in inspect.getsource(CanvasController.fit_single_column_width)


def test_rectangle_side_and_legacy_class_patchpoint(monkeypatch):
    region=SimpleNamespace(points=[(10,20),(30,20),(30,40),(10,40)])
    assert app.PictureCaptureApp._rectangle_bounds(region)==(10,20,30,40)
    app.PictureCaptureApp._set_rectangle_side(region,"right",35)
    assert sorted({x for x,y in region.points}) == [10,35]
    monkeypatch.setattr(app.PictureCaptureApp, "_rectangle_bounds", staticmethod(lambda region: None))
    old=list(region.points)
    app.PictureCaptureApp._set_rectangle_side(region,"left",0)
    assert region.points==old


def test_ppp_labels_resolve_current_patchable_helpers(monkeypatch):
    region=SimpleNamespace(label="original")
    monkeypatch.setattr(app,"label_text",lambda label: "patched")
    assert app.PictureCaptureApp._polygon_display_name(region,0)=="patched"
    monkeypatch.setattr(app,"user_edited_link",lambda label, name: label+"-"+name)
    instance=SimpleNamespace()
    app.PictureCaptureApp._set_polygon_display_name(instance,region,"new")
    assert region.label=="original-new"


def test_single_column_zoom_and_invalid_width():
    state=SimpleNamespace(image=SimpleNamespace(width=1000),
        settings=SimpleNamespace(column_width=200,gutter=20),
        status_var=SimpleNamespace(set=lambda value: None),
        canvas=SimpleNamespace(winfo_width=lambda:480,xview_moveto=lambda v: None),
        update_idletasks=lambda:None,_update_view_zoom_label=lambda:None,
        redraw=lambda:None,_set_idle_cursor_status=lambda:None,view_scale=1.0)
    state._canvas_controller_for_call=lambda: CanvasController(state)
    app.PictureCaptureApp.fit_single_column_width(state)
    assert state.view_scale==2.0
    state.settings.column_width=0
    app.PictureCaptureApp.fit_single_column_width(state)
    assert state.view_scale==2.0


def test_quick_color_button_live_tk_provider():
    calls=[]
    button=SimpleNamespace(configure=lambda **kw: calls.append(kw))
    app.PictureCaptureApp._style_color_button(button,"#123456")
    assert calls[-1]["bg"]=="#123456"


def test_edit_guard_still_blocks_preprocess_before_claiming_page():
    messages=[]
    stub=SimpleNamespace(_preprocess_mode_active=lambda:True,
        status_var=SimpleNamespace(set=messages.append),
        _batch_active=False,project=None,current_page=None,image=None)
    assert app.PictureCaptureApp.guard(stub) is False
    assert "预处理模式" in messages[0]
