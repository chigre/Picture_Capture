from pathlib import Path

from picture_capture.ui.settings import help as settings_help


def test_settings_help_module_has_no_reverse_app_dependency_and_keeps_resource_path():
    source = Path(settings_help.__file__).read_text(encoding="utf-8")
    assert "picture_capture.app" not in source
    assert "from ...app import" not in source
    assert "import picture_capture.app" not in source

    path = settings_help.settings_help_image_path("layout_settings.png")
    assert path.is_file()
    assert path.parent.name == "layout_example"
    assert path.parent.parent.name == "data"


def test_settings_help_extraction_keeps_dialog_wrappers_and_behavior_boundary():
    root = Path(__file__).resolve().parents[1]
    app = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    helper = (root / "src" / "picture_capture" / "ui" / "settings" / "help.py").read_text(encoding="utf-8")

    settings_start = app.index("class SettingsDialog")
    settings_end = app.index("class ReviewWindow", settings_start)
    settings = app[settings_start:settings_end]

    for method, helper_name in (
        ("_show_settings_help", "show_settings_help"),
        ("_settings_help_image_path", "settings_help_image_path"),
        ("_load_settings_help_image", "load_settings_help_image"),
        ("_schedule_settings_help_image_render", "schedule_settings_help_image_render"),
        ("_render_settings_help_images", "render_settings_help_images"),
        ("_show_setting_help", "show_setting_help"),
        ("_show_check_help", "show_check_help"),
        ("_bind_help_widget", "bind_help_widget"),
        ("_bind_responsive_labels", "bind_responsive_labels"),
    ):
        assert f"def {method}(" in settings
        assert f"_settings_help_ui.{helper_name}(" in settings

    assert "label_width = int(label.winfo_width())" not in settings
    assert "label_width = int(label.winfo_width())" in helper
    assert "themed_display_image(rendered, dialog.parent.appearance_mode)" in helper
    assert 'container.bind("<Configure>", schedule, add="+")' in helper
