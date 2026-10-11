"""New layout regression tests for upper-right modes and narrow page range."""
from pathlib import Path

from picture_capture.ui.workspace_tools import compact_page_column_widths

SRC = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "ui"


def test_mode_buttons_at_upper_right_keep_os_caption():
    text = (SRC / "workspace_tools.py").read_text(encoding="utf-8")
    assert 'mode_bar.pack(side="top", fill="x", before=app.main_paned)' in text
    assert 'mode_group.pack(side="right")' in text
    assert 'for caption in ("极简", "紧凑", "正常", "最大")' in text
    assert 'project_group.pack(side="left", padx=(4, 0))' in text
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
    assert 'button.state(["selected"] if mode == active else ["!selected"])' in text
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
    assert '.grid(row=0, column=column, sticky="w", padx=0, pady=0)' in controls
    assert 'value="specified", style="PC.Workspace80.TRadiobutton"' in controls
    assert 'style="PC.Workspace80.TEntry"' in controls
    assert 'indicatorsize=10' in workspace


def test_project_shortcuts_never_hide_or_switch_to_icons():
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
    sep1, quick, sep2 = Frame(), Frame(270), Frame()
    app = SimpleNamespace(
        project_action_bar=project,
        workspace_header_mode_group=mode,
        workspace_header_mode_separator=sep1,
        workspace_header_quick_host=quick,
        workspace_header_project_separator=sep2,
        workspace_header_project_buttons=["项目", "Profile", "设置", "帮助"],
    )
    assert required_header_width(app) == 408
    for width in (240, 320, 500, 650):
        _refresh_header_toolbar(app, width)
        assert project.events == []
        assert not any(event == "pack" for event, _ in quick.events)
    _refresh_header_toolbar(app, 800)
    assert project.events == []
    assert quick.events[-1][0] == "pack"
    _refresh_header_toolbar(app, 240)
    assert project.events == []
    assert quick.events[-1][0] == "hide"

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
    assert window.minimum == (408, 2)


def test_project_buttons_always_use_text_and_left_packing():
    source = (SRC / "workspace_tools.py").read_text(encoding="utf-8")
    assert '("项目", app.open_recent_project,' in source
    assert '("Profile", app.open_project_profile,' in source
    assert '("设置", app.open_settings,' in source
    assert '("帮助", app.show_help_dialog,' in source
    assert 'project_group.pack(side="left", padx=(4, 0))' in source
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
    theme = source.index('theme_toggle = ttk.Button(')
    modes = source.index('for caption in ("极简", "紧凑", "正常", "最大"):')
    assert theme < modes
    assert 'text="◑", width=3, style="PC.WindowMode.TButton"' in source
    assert 'theme_toggle.pack(side="left", padx=(0, 5))' in source
    assert 'app._attach_tooltip(theme_toggle, "切换浅色/深色模式")' in source
    assert 'command=lambda: toggle_workspace_appearance(app)' in source
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
