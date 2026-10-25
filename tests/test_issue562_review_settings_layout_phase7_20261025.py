"""Physical ReviewWindow layout and SettingsDialog form ownership, Issue #562."""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import patch

from picture_capture import app
from picture_capture.ui import review_layout_events
from picture_capture.ui.settings import field_form_runtime, interactive_panels


def test_original_class_callbacks_keep_signatures_and_real_owner_implementation():
    owners = {
        review_layout_events: (app.ReviewWindow, (
            "_review_flat_button", "_review_collapsible_section", "_toggle_review_right_section",
            "_toggle_focused_panel", "_fit_review_left_pane_to_toolbar",
            "_initialize_review_layout_and_rows", "_review_image_area_width",
            "_review_canvas_configured", "_apply_auto_review_zoom_resize",
            "_stored_review_zoom_percent")),
        field_form_runtime: (app.SettingsDialog, ("_setting_var",)),
        interactive_panels: (app.SettingsDialog, ("_add_collapsible_settings", "_settings_intro")),
    }
    for module, (cls, names) in owners.items():
        for name in names:
            public = getattr(cls, name)
            physical = getattr(module, name)
            assert public.__module__ == "picture_capture.app"
            assert "deps={" in inspect.getsource(public)
            assert len(inspect.getsource(physical).splitlines()) >= 4
            assert inspect.signature(public).parameters["self"]
    assert "body.pack_forget()" in inspect.getsource(review_layout_events._toggle_review_right_section)
    assert "after(120," in inspect.getsource(review_layout_events._review_canvas_configured)


def test_review_right_section_collapse_and_expand_state():
    calls = []
    class Var:
        def __init__(self, value): self.value = value
        def get(self): return self.value
        def set(self, value): self.value = value
    state = Var(True)
    title = Var("▾ 网络")
    body = SimpleNamespace(pack=lambda **kw: calls.append(("body-pack",kw)),
                           pack_forget=lambda: calls.append(("body-hide",)))
    frame = SimpleNamespace(pack_configure=lambda **kw: calls.append(("frame",kw)))
    section = {"title":"网络", "title_var":title, "body":body, "frame":frame,
               "expand_when_open":True}
    stub = SimpleNamespace(_review_right_sections={"network":section},
                           review_right_section_expanded={"network":state})
    app.ReviewWindow._toggle_review_right_section(stub,"network")
    assert state.get() is False and title.get() == "▸ 网络"
    assert calls == [("body-hide",), ("frame",{"expand":False})]
    calls.clear()
    app.ReviewWindow._toggle_review_right_section(stub,"network")
    assert state.get() is True and title.get() == "▾ 网络"
    assert calls == [("body-pack",{"fill":"both","expand":True}),
                     ("frame",{"expand":True})]


def test_review_canvas_resize_is_debounced_on_main_tk_event_loop():
    calls=[]
    canvas=SimpleNamespace(itemconfigure=lambda *a,**kw:calls.append(("configure",a,kw)))
    stub=SimpleNamespace(canvas=canvas,rows_window="window",review_zoom_auto=True,
        _review_auto_zoom_width=100,_review_auto_zoom_job=None,
        _review_image_area_width=lambda width: 155,
        _apply_auto_review_zoom_resize=lambda: None,
        after=lambda delay,callback: calls.append(("after",delay,callback)) or "after-id")
    app.ReviewWindow._review_canvas_configured(stub,SimpleNamespace(width=200))
    assert calls[0] == ("configure",("window",),{"width":200})
    assert calls[1][0:2] == ("after",120)
    assert stub._review_auto_zoom_width == 155
    assert stub._review_auto_zoom_job == "after-id"


def test_review_zoom_stores_fractional_percent_without_integer_cast():
    assert app.ReviewWindow._stored_review_zoom_percent(
        SimpleNamespace(review_zoom_auto=False,review_zoom=1.2575)) == 125.75
    assert app.ReviewWindow._stored_review_zoom_percent(
        SimpleNamespace(review_zoom_auto=True,review_zoom=1.2575)) == 0.0


def test_settings_percent_conversion_uses_live_legacy_patchpoints(monkeypatch):
    s=SimpleNamespace(paddle_left_tolerance=17)
    stub=SimpleNamespace(parent=SimpleNamespace(settings=s,image=None),
        vars={},SETTING_CHOICES={})
    monkeypatch.setattr(app,"_column_pixels_to_percent",lambda settings,value:value/2)
    monkeypatch.setattr(app,"_format_layout_percent",lambda value:f"{value:.1f}%")
    monkeypatch.setattr(app.tk,"StringVar",lambda value:SimpleNamespace(get=lambda:value))
    result=app.SettingsDialog._setting_var(stub,"paddle_left_tolerance")
    assert result.get() == "8.5%"
    assert stub.vars["paddle_left_tolerance"] is result


def test_review_image_width_accounts_for_live_sequence_gutter():
    stub=SimpleNamespace(canvas=SimpleNamespace(winfo_width=lambda:220))
    with patch("picture_capture.ui.review_crop_sequence.review_sequence_gutter",return_value=35):
        assert app.ReviewWindow._review_image_area_width(stub) == 173
        assert app.ReviewWindow._review_image_area_width(stub,100) == 53
