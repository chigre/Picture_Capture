"""Issue #562: app-root physical UI lifecycle, sidebar and quick-editor owners."""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from picture_capture import app
from picture_capture.ui import main_appearance_policy, main_sidebar_sections, quick_settings_apply


def test_root_app_ui_methods_forward_live_globals_to_real_owners():
    cases = {
        main_appearance_policy: ("_app_icon_toplevel_mapped","_maximize_main_window",
            "_apply_current_appearance","_appearance_toplevel_mapped",
            "_appearance_mode_selected","_cancel_system_appearance_poll",
            "_schedule_system_appearance_poll","_poll_system_appearance","set_appearance_mode"),
        main_sidebar_sections: ("_ensure_sidebar_navigation_width","_section_frame",
            "_set_section_expanded","_toggle_section","_apply_initial_section_states",
            "_apply_new_project_sidebar_defaults"),
        quick_settings_apply: ("_quick_percent_parameter_changed",
            "_quick_pixel_parameter_changed","_quick_parameter_changed","_quick_geometry_value"),
    }
    for owner, names in cases.items():
        for name in names:
            original = getattr(app.PictureCaptureApp, name)
            implementation = getattr(owner, name)
            assert original.__module__ == "picture_capture.app"
            assert "return _" in inspect.getsource(original)
            assert len(inspect.getsource(implementation).splitlines()) >= 3
    assert "grid_remove()" in inspect.getsource(main_sidebar_sections._set_section_expanded)
    assert "after_idle(" in inspect.getsource(main_appearance_policy._appearance_toplevel_mapped)


def test_quick_geometry_header_footer_and_vertical_values_unchanged():
    s = SimpleNamespace(layout_writing_mode="horizontal-tb",
        profile_header_mode="present", profile_header_percent=12.5,
        profile_footer_mode="present", profile_footer_percent=7.5,
        start_y=1, bottom_y=1)
    instance=SimpleNamespace(settings=s,image=SimpleNamespace(width=800,height=1000))
    assert app.PictureCaptureApp._quick_geometry_value(instance,"start_y") == 125
    assert app.PictureCaptureApp._quick_geometry_value(instance,"bottom_y") == 925
    s.layout_writing_mode="vertical-rl"
    assert app.PictureCaptureApp._quick_geometry_value(instance,"start_y") == 1
    instance.image=None
    assert app.PictureCaptureApp._quick_geometry_value(instance,"bottom_y") == 1


def test_sidebar_new_project_defaults_preserve_real_navigation_api():
    sections={"preprocess":object(),"normal":object(),"pages":object()}
    changes=[]
    instance=SimpleNamespace(section_expanded={},_collapsible_sections=sections,
        _set_section_expanded=lambda section,expanded,persist: changes.append((section,expanded,persist)))
    app.PictureCaptureApp._apply_new_project_sidebar_defaults(instance)
    assert instance.section_expanded["preprocess"] is False
    assert instance.section_expanded["normal"] is True
    assert instance.section_expanded["pages"] is True
    assert changes == [(sections["preprocess"],False,False),(sections["normal"],True,False),(sections["pages"],True,False)]
