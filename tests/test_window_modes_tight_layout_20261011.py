"""New layout regression tests for upper-right modes and narrow page range."""
from pathlib import Path

from picture_capture.ui.workspace_tools import compact_page_column_widths

SRC = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "ui"


def test_mode_buttons_at_upper_right_keep_os_caption():
    text = (SRC / "workspace_tools.py").read_text(encoding="utf-8")
    assert 'mode_bar.pack(side="top", fill="x", before=app.main_paned)' in text
    assert 'mode_group.pack(side="right")' in text
    assert 'for caption in ("极简", "紧凑", "正常", "最大")' in text
    assert 'project_group.pack(side="left", padx=(2, 0))' in text
    assert 'app.workspace_header_mode_group = mode_group' in text
    assert 'app.after_idle(lambda: enforce_header_min_width(app))' in text
    assert 'for label, command, tip in project_actions:' in text
    assert 'for label, symbol, command, tip in project_actions:' not in text
    assert 'app.after_idle(lambda: install_header_quick_controls(app))' in text
    assert 'app.workspace_header_quick_host = ttk.Frame(mode_bar' in text
    assert 'rail, 0, "☰", "工具菜单"' not in text
    assert 'app._attach_tooltip(text_button, tip)' not in text
    assert 'app.project_action_bar = project_group' in text
    assert 'app.workspace_header_project_buttons.append(button)' in text
    assert 'app.project_footer_buttons.append(button)' in text
    assert 'button.configure(' in text
    assert 'bg=colors.get("tree_selected") if mode == active' in text
    assert 'overrideredirect(' not in text


def test_compact_page_columns_fit_a_120px_rail():
    columns = ("bookmark", "page", "section", "lined", "fill_status", "illustrations")
    labels = dict(zip(columns, ("●", "页面", "域", "线", "填充状态", "图")))
    rows = [("●", "long_dictionary_filename_1001", "2", "●", "已填充", "●")]
    shown = ("page", "lined", "illustrations")
    sizes = compact_page_column_widths(
        labels, rows, columns, shown, 100, lambda value: len(value) * 7,
    )
    assert sizes["page"] >= len("页面") * 7 + 16
    assert sizes["lined"] >= len("线") * 7 + 16
    assert sizes["illustrations"] >= len("图") * 7 + 16
    assert sum(sizes[column] for column in shown) == 100
    wider = compact_page_column_widths(
        labels, rows, columns, shown, 220, lambda value: len(value) * 7,
    )
    assert wider["page"] == sizes["page"] + 120
    assert sum(wider[column] for column in shown) == 220


def test_page_range_radio_buttons_share_one_row_with_small_entry():
    controls = (SRC / "simple_page_controls.py").read_text(encoding="utf-8")
    workspace = (SRC / "workspace_tools.py").read_text(encoding="utf-8")
    for radio in ('(0, "当前", "current")', '(1, "至末页", "to_end")',
                  '(2, "至指定", "to_specified")'):
        assert radio in controls
    assert 'radio(controls, caption, value).grid(' in controls
    assert 'row=0, column=column, sticky="w", padx=0, pady=0' in controls
    assert 'radio(spec, "", "specified")' in controls
    assert 'field = tk.Entry(' in controls
    assert 'jump = action(spec, "跳", app.jump_to_page_spec)' in controls
    assert 'highlightthickness=0, padx=0, pady=0' in controls
    assert 'app.workspace_compact_range_widgets = []' in controls
    assert 'indicatorsize=10' in workspace


def test_project_shortcuts_use_measured_space_and_keep_all_labels():
    from types import SimpleNamespace
    from picture_capture.ui.workspace_tools import (
        _refresh_header_toolbar, required_header_width, enforce_header_min_width,
    )

    class Frame:
        def __init__(self, reqwidth=1):
            self.events = []
            self.reqwidth = reqwidth

        def pack(self, **kwargs):
            self.events.append(("pack", kwargs))

        def pack_forget(self):
            self.events.append(("hide", {}))

        def winfo_reqwidth(self):
            return self.reqwidth

    project, mode = Frame(220), Frame(160)
    mode_sep, quick, zoom, zoom_sep = Frame(1), Frame(270), Frame(180), Frame(1)
    shortcuts = [Frame(30) for _ in ("普", "O", "校")]
    app = SimpleNamespace(
        project_action_bar=project,
        workspace_header_mode_group=mode,
        workspace_header_mode_separator=mode_sep,
        workspace_header_quick_host=quick,
        workspace_header_zoom_group=zoom,
        workspace_header_zoom_separator=zoom_sep,
        workspace_header_shortcut_buttons=shortcuts,
        workspace_header_project_buttons=["项目", "Profile", "设置", "帮助"],
    )
    assert required_header_width(app) == 384
    # No magic 650px threshold or exaggerated quick-menu minimum.
    # Fixed labels: 384, actions: 93, zoom extras: 191; no divider.
    _refresh_header_toolbar(app, 476)
    assert app._workspace_header_quick_density == "none"
    assert project.events == []
    _refresh_header_toolbar(app, 477)
    assert app._workspace_header_quick_density == "actions"
    assert quick.events[-1][0] == "pack"
    assert zoom.events[-1][0] == "hide"
    assert project.events == []
    _refresh_header_toolbar(app, 667)
    assert app._workspace_header_quick_density == "actions"
    _refresh_header_toolbar(app, 668)
    assert app._workspace_header_quick_density == "full"
    assert zoom.events[-1][0] == "pack"
    assert quick.events[-1][0] == "pack"
    assert project.events == []
    _refresh_header_toolbar(app, 390)
    assert app._workspace_header_quick_density == "none"
    assert quick.events[-1][0] == "hide"
    assert project.events == []

    class Window:
        def __init__(self):
            self.minimum = (1, 2)

        def minsize(self, *args):
            if args:
                self.minimum = tuple(args)
            return self.minimum

    window = Window()
    window.project_action_bar = project
    window.workspace_header_mode_group = mode
    enforce_header_min_width(window)
    assert window.minimum == (384, 2)


def test_early_header_configure_is_rechecked_after_quick_controls_exist():
    from types import SimpleNamespace
    from picture_capture.ui.workspace_tools import _refresh_header_toolbar

    # The mode bar first receives <Configure> while the deferred toolbar is
    # empty. It should wait instead of caching a false visibility decision.
    project = SimpleNamespace(winfo_reqwidth=lambda: 190)
    mode = SimpleNamespace(winfo_reqwidth=lambda: 165)
    app = SimpleNamespace(project_action_bar=project, workspace_header_mode_group=mode)
    _refresh_header_toolbar(app, 900)
    assert not hasattr(app, "_workspace_header_quick_density")

    source = (SRC / "workspace_tools.py").read_text(encoding="utf-8")
    assert 'app.workspace_header_shortcut_buttons.append(button)' in source
    assert 'app.after_idle(lambda: _refresh_header_toolbar(' in source
    assert 'app.workspace_header_mode_bar.winfo_width()' in source
    assert 'max(650,' not in source
    assert 'max(250,' not in source


def test_project_buttons_always_use_text_and_left_packing():
    source = (SRC / "workspace_tools.py").read_text(encoding="utf-8")
    assert '("项目", app.open_recent_project,' in source
    assert '("Profile", app.open_project_profile,' in source
    assert '("设置", app.open_settings,' in source
    assert '("帮助", app.show_help_dialog,' in source
    assert 'project_group.pack(side="left", padx=(2, 0))' in source
    assert '_compact_header_button(app, project_group, label, command)' in source
    assert 'workspace_header_mode_separator' not in source
    assert 'workspace_header_project_separator' not in source
    assert 'project_separator.pack(' not in source
    responsive = source.split("def _refresh_header_toolbar(", 1)[1].split(
        "def install_header_quick_controls(", 1
    )[0]
    assert 'project_group.pack_forget()' not in responsive
    assert 'button.configure(text=' not in responsive
    assert 'app.workspace_header_project_buttons.append(button)' in source


def test_header_actions_share_view_zoom_var_and_preserve_bottom_toolbar():
    text = (SRC / "workspace_tools.py").read_text(encoding="utf-8")
    section = text.split("def install_header_quick_controls(", 1)[1].split(
        "def _refresh_window_mode_buttons(", 1
    )[0]
    assert 'textvariable=app.view_zoom_var, width=5' in section
    assert 'widget.bind("<Return>", app.apply_view_zoom_text)' in section
    assert 'widget.bind("<FocusOut>", app.apply_view_zoom_text)' in section
    for callback in ('app.zoom(0.87)', 'app.zoom(1.15)',
                     'app.fit_page_width', 'app.fit_page_height',
                     'app.fit_single_column_width', 'app.run_normal_draw_action',
                     'app.run_ocr_draw_action', 'app.open_review'):
        assert callback in section
    assert 'app.workspace_quick_actions_host = quick_host' in text
    assert 'app.after_idle(lambda: install_compact_zoom_controls(app))' in text
    assert 'app.workspace_quick_action_buttons.append(button)' in text
    assert 'app.workspace_quick_zoom_controls.append(widget)' in text


def test_theme_toggle_is_immediately_left_of_extreme_mode_and_uses_existing_appearance_state():
    from types import SimpleNamespace
    from picture_capture.ui.workspace_tools import toggle_workspace_appearance

    source = (SRC / "workspace_tools.py").read_text(encoding="utf-8")
    theme = source.index('theme_toggle = _compact_header_button(')
    modes = source.index('for caption in ("极简", "紧凑", "正常", "最大"):')
    assert theme < modes
    assert 'app, mode_group, "◑", lambda: toggle_workspace_appearance(app)' in source
    assert 'theme_toggle.pack(side="left", padx=(0, 2))' in source
    assert 'app._attach_tooltip(theme_toggle, "切换浅色/深色模式")' in source
    assert 'lambda: toggle_workspace_appearance(app)' in source
    assert 'app.workspace_theme_toggle_button = theme_toggle' in source

    selected = []
    app = SimpleNamespace(appearance_mode="light")
    def select(mode):
        selected.append(mode)
        app.appearance_mode = mode
    app.set_appearance_mode = select

    assert toggle_workspace_appearance(app) == "dark"
    assert toggle_workspace_appearance(app) == "light"
    assert selected == ["dark", "light"]

    # A system-selected resolved dark appearance must toggle to light, too.
    app.appearance_mode = "dark"
    assert toggle_workspace_appearance(app) == "light"
    assert selected[-1] == "light"


def test_light_and_dark_range_controls_use_identical_geometry(monkeypatch):
    from types import SimpleNamespace
    from picture_capture.ui import simple_page_controls as page

    class Widget:
        def __init__(self, role):
            self.role = role
            self.options = {}
        def winfo_exists(self):
            return True
        def configure(self, **kwargs):
            self.options.update(kwargs)

    radios = [Widget("radio"), Widget("radio")]
    field = Widget("entry")
    button = Widget("button")
    app = SimpleNamespace(
        workspace_compact_range_widgets=[
            ("radio", radios[0]), ("radio", radios[1]),
            ("entry", field), ("button", button),
        ],
        _main_ui_colors=dict(
            sidebar="#f0f0f0", button="#f4f5f7", text="#000000",
            button_hover="#e7eaee",
        ),
    )
    page.refresh_compact_range_appearance(app)
    assert radios[0].options["selectcolor"] == "#f0f0f0"
    assert field.options["bg"] == "#f4f5f7"
    assert button.options["activebackground"] == "#e7eaee"
    app._main_ui_colors = dict(
        sidebar="#272b32", button="#353940", text="#f1f1f1",
        button_hover="#434952",
    )
    page.refresh_compact_range_appearance(app)
    assert radios[0].options["bg"] == "#272b32"
    assert radios[1].options["fg"] == "#f1f1f1"
    assert field.options["insertbackground"] == "#f1f1f1"
    assert button.options["bg"] == "#353940"
    assert "refresh_compact_range_appearance(self)" in (
        __import__("inspect").getsource(
            __import__("picture_capture.app", fromlist=["PictureCaptureApp"]).PictureCaptureApp
        )
    )


def test_header_buttons_are_compact_in_both_themes_and_preserve_preprocess_lock():
    from picture_capture.ui import workspace_tools
    from types import SimpleNamespace
    from pathlib import Path

    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    app_src = (SRC.parent / "app.py").read_text(encoding="utf-8")
    assert 'button = tk.Button(' in source
    assert 'font="TkDefaultFont", anchor="center", justify="center"' in source
    assert 'bd=0, relief="flat", highlightthickness=0, padx=3, pady=1' in source
    assert 'button._pc_skip_classic_appearance = True' in source
    assert 'refresh_compact_header_buttons(self)' in app_src
    assert 'if isinstance(widget, ttk.Widget):' in app_src
    assert 'old_state = widget.cget("state")' in app_src

    class Button:
        def __init__(self):
            self.options = {}
        def configure(self, **options):
            self.options.update(options)
        def winfo_exists(self):
            return True

    mode_buttons = {caption: Button() for caption in ("极简", "紧凑", "正常", "最大")}
    project_buttons = [Button() for _ in range(4)]
    toggle = Button()
    app = SimpleNamespace(
        appearance_mode="light", workspace_mode="紧凑",
        workspace_title_mode_buttons=mode_buttons,
        workspace_header_project_buttons=project_buttons,
        workspace_theme_toggle_button=toggle,
        _main_ui_colors={
            "button": "#f4f5f7", "button_hover": "#e7eaee",
            "tree_selected": "#dce8f7", "text": "#000000",
        },
    )
    workspace_tools.refresh_compact_header_buttons(app)
    assert mode_buttons["紧凑"].options["bg"] == "#dce8f7"
    assert mode_buttons["正常"].options["bg"] == "#f4f5f7"
    app.appearance_mode = "dark"
    app.workspace_mode = "极简"
    app._main_ui_colors = {
        "button": "#353940", "button_hover": "#434952",
        "tree_selected": "#355A75", "text": "#f1f1f1",
    }
    workspace_tools.refresh_compact_header_buttons(app)
    assert mode_buttons["极简"].options["bg"] == "#355A75"
    assert project_buttons[0].options["bg"] == "#353940"
    assert toggle.options["fg"] == "#f1f1f1"
