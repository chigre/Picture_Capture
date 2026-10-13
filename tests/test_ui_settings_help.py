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


def test_bind_help_widget_recurses_into_child_controls():
    class Widget:
        def __init__(self, children=()):
            self.children = list(children)
            self.bindings = []

        def bind(self, event, _callback, add=None):
            self.bindings.append((event, add))

        def winfo_children(self):
            return list(self.children)

    class Dialog:
        def _bind_help_widget(self, widget, callback):
            settings_help.bind_help_widget(self, widget, callback)

    grandchild = Widget()
    child = Widget([grandchild])
    root = Widget([child])

    settings_help.bind_help_widget(Dialog(), root, lambda: None)

    for widget in (root, child, grandchild):
        assert ("<Enter>", "+") in widget.bindings
        assert ("<FocusIn>", "+") in widget.bindings


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


def test_help_body_is_live_bound_in_every_tab_not_snapshotted_at_construction():
    """Regression: selecting ⓘ changed titles but left most tabs on intro text."""
    source = (Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py").read_text(
        encoding="utf-8"
    )
    panel_start = source.index("    def _scrollable_settings_page(", source.index("class SettingsDialog"))
    panel_end = source.index("    def _settings_intro(", panel_start)
    panel = source[panel_start:panel_end]
    assert "textvariable=self._settings_help_title_var" in panel
    assert "textvariable=self._settings_help_body_var" in panel
    assert "text=self._settings_help_body_var.get()" not in panel
    assert "_settings_help_body_label" not in source

    # The responsive label binder must recognize textvariable-backed widgets
    # so switching among longer/shorter parameter explanations still wraps.
    binder = Path(settings_help.__file__).read_text(encoding="utf-8")
    assert 'label.cget("textvariable")' in binder
    assert "label.configure(wraplength=available)" in binder


def test_parameter_and_checkbox_info_show_individual_help_on_all_observers():
    from picture_capture.ui.settings import schema

    class ObservableVar:
        def __init__(self):
            self.value = ""
            self.observers = []

        def set(self, value):
            self.value = value
            for observer in self.observers:
                observer.append(value)

        def get(self):
            return self.value

    class Dialog:
        SETTING_LABELS = schema.SETTING_LABELS
        SETTING_HELP = schema.SETTING_HELP
        SETTING_UNITS = schema.SETTING_UNITS
        SETTING_HELP_IMAGES = schema.SETTING_HELP_IMAGES
        CHECK_HELP = schema.CHECK_HELP

        def __init__(self):
            self._settings_help_title_var = ObservableVar()
            self._settings_help_body_var = ObservableVar()
            self._settings_help_current_image = None
            self._field_meta = {}
            self.render_requests = 0

        def _show_settings_help(self, title, body, image_name=None):
            settings_help.show_settings_help(self, title, body, image_name)

        def _schedule_settings_help_image_render(self):
            self.render_requests += 1

    dialog = Dialog()
    # Simulate separate tab help panes observing one StringVar.
    normal_panel, advanced_panel = [], []
    dialog._settings_help_body_var.observers.extend([normal_panel, advanced_panel])
    settings_help.show_setting_help(dialog, "body_indent")
    first = dialog._settings_help_body_var.get()
    assert dialog._settings_help_title_var.get() == "正文缩进"
    assert "普通画线" in first
    assert "单位：" in first
    settings_help.show_setting_help(dialog, "row_padding")
    second = dialog._settings_help_body_var.get()
    assert second != first
    assert "单位：" in second
    assert dialog._settings_help_title_var.get() != "正文缩进"

    settings_help.show_check_help(dialog, "自动检测栏数", "ordinary_auto_columns")
    third = dialog._settings_help_body_var.get()
    assert third != second
    assert third == schema.CHECK_HELP["ordinary_auto_columns"]
    assert normal_panel == advanced_panel == [first, second, third]
    assert dialog.render_requests == 3
