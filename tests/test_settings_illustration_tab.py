"""Settings Center illustration tab and detector threshold contract."""
from pathlib import Path

from picture_capture.models import AppSettings
from picture_capture.ui.settings import schema


def test_illustration_tab_owns_existing_visual_and_detection_settings():
    assert schema.ILLUSTRATION_DETECTION_FIELDS == (
        "illustration_detect_gray_threshold", "illustration_detect_parallel_workers",
        "illustration_detect_min_width",
        "illustration_detect_min_height", "illustration_detect_size_unit",
        "illustration_detect_min_occupancy_percent",
        "illustration_detect_padding", "illustration_detect_right_padding",
    )
    assert "illustration_fill_color" in schema.ILLUSTRATION_APPEARANCE_FIELDS
    assert "illustration_label_font_size" in schema.ILLUSTRATION_APPEARANCE_FIELDS
    assert "illustration_fill_opacity" in schema.ILLUSTRATION_APPEARANCE_FIELDS
    assert "illustration_detect_padding" not in schema.PROJECT_RUNTIME_FIELDS
    assert "illustration_fill_opacity" not in schema.DISPLAY_FIELDS
    assert "layout_mask_illustrations" not in [name for _, name in schema.NORMAL_CHECKS]


def test_illustration_detection_thresholds_preserve_previous_defaults():
    settings = AppSettings()
    assert settings.illustration_detect_gray_threshold == 170
    assert settings.illustration_detect_min_width == 5.5
    assert settings.illustration_detect_min_height == 2.8
    assert settings.illustration_detect_size_unit == "%"
    assert settings.illustration_detect_min_occupancy_percent == 3.5


def test_illustration_tab_placement_and_settings_persistence_wiring():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (root / "app.py").read_text(encoding="utf-8")
    settings_ui = (root / "ui" / "settings" / "illustration.py").read_text(encoding="utf-8")
    dialog_init = (root / "ui/settings/dialog_initialization.py").read_text(encoding="utf-8")
    assert "_settings_dialog_initialization.initialize_settings_dialog(" in app
    assert dialog_init.index('(normal_tab, "普通画线")') < dialog_init.index('(illustration_tab, "插图")') < dialog_init.index('(display_tab, "显示/校对")')
    assert '"illustration": illustration_tab' in dialog_init
    assert "_settings_illustration_ui.build_illustration_settings_tab(self, illustration_tab)" in dialog_init
    assert "dialog._add_setting_group(" in settings_ui
    assert "dialog._add_check_group(" in settings_ui
    # Color selection is now shared by all Settings Center *_color fields,
    # including Illustration and REF, instead of feature-local plain buttons.
    shared = (root / "ui" / "settings" / "color_picker.py").read_text(encoding="utf-8")
    form = (root / "ui/settings/field_form_runtime.py").read_text(encoding="utf-8")
    assert "_settings_field_form.setting_widget(" in app
    assert "_settings_color_ui.make_color_widget(parent, var)" in form
    assert "colorchooser.askcolor(" in shared
    assert "value.trace_add(" in shared
    assert "for name in COLOR_FIELDS" not in settings_ui
