"""Regression checks for persistent mode menu, simple page controls and rail density."""
from pathlib import Path

from picture_capture.ui import workspace_tools
from picture_capture.ui import simple_page_controls

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_window_mode_buttons_on_upper_right_preserve_native_caption():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'mode_bar.pack(side="top", fill="x", before=app.main_paned)' in source
    assert 'mode_group.pack(side="right")' in source
    assert 'for caption in ("极简", "紧凑", "正常", "最大")' in source
    assert 'lambda mode=caption: set_sidebar_mode(app, mode)' in source
    assert '_refresh_window_mode_buttons(app)' in source
    assert 'app.workspace_sidebar_mode_menu' not in source
    assert 'overrideredirect(' not in source


def test_light_and_dark_use_same_compact_button_geometry():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'style="PC.Sidebar.TFrame", width=DEFAULT_RAIL_WIDTH, height=33' in source
    assert 'entry.grid_propagate(False)' in source
    assert 'entry.configure(width=36 if extreme else app.workspace_rail_width)' in source
    assert 'padding=(0, 0), relief="flat"' in app
    assert 'style.configure("PC.QuickRail.TButton", font="TkDefaultFont"' in app
    assert 'padding=(0, 0), relief="flat"' in source


def test_simple_mode_clones_complete_range_and_navigation_controls():
    tools = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    controls = Path(simple_page_controls.__file__).read_text(encoding="utf-8")
    assert 'install_simple_page_controls(app, mini_host)' in tools
    assert 'install_simple_page_tree_actions(app, mini)' in tools
    assert 'displaycolumns=("page", "lined", "illustrations")' in tools
    for label in ('"当前"', '"至末页"', '"至指定"',
                  '"跳"', '"⨇"', '"⨈"', '"上"', '"下"'):
        assert label in controls
    assert 'radio(spec, "", "specified")' in controls
    assert 'variable=app.page_range_var, value=value' in controls
    assert 'textvariable=app.page_range_spec_var' in controls
    assert 'action(spec, "跳", app.jump_to_page_spec)' in controls
    assert 'app.jump_to_bookmark(-1)' in controls
    assert 'app.jump_to_bookmark(1)' in controls
    assert 'app.change_page(-1)' in controls
    assert 'app.change_page(1)' in controls
    assert 'app._bookmark_stems()' in controls
    assert 'app._set_page_section_count(index, updated)' in controls
    assert '"跳转到指定页面的第一个有效页面；ENTER为快捷键"' in controls
    assert 'action(actions, caption, callback)' in controls
    assert 'padx=0, pady=0' in controls


def test_quick_actions_are_always_short_and_horizontal_except_extreme():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'app.workspace_quick_actions_host = quick_host' in source
    assert '("普", "O", "校")[index]' in source
    assert '_create_macaron_action_button(' in source
    assert 'button.configure(text=title, width=2)' in source
    assert 'row=6 + index if extreme else 2' in source
    assert 'column=0 if extreme else index' in source
    assert 'sticky="ew", padx=0, pady=0' in source
    assert 'button.configure(text=compact if extreme else ordinary' not in source


def test_light_rail_button_height_and_dark_captions_are_consistently_centered():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'style="PC.Sidebar.TFrame", width=DEFAULT_RAIL_WIDTH, height=33' in source
    assert 'entry.grid_propagate(False)' in source
    assert 'text_button = tk.Button(' in source
    assert 'anchor="center", justify="center"' in source
    assert 'relief="flat", bd=0, highlightthickness=0' in source
    assert 'style.configure(button_style, anchor="center", justify="center")' in app
    assert 'anchor="center", justify="center"' in app


def test_theme_toggle_keeps_four_window_preset_commands_unchanged():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'theme_toggle.pack(side="left", padx=(0, 2))' in source
    assert 'for caption in ("极简", "紧凑", "正常", "最大"):' in source
    assert 'app.workspace_title_mode_buttons[caption] = button' in source
    assert 'app.set_appearance_mode(mode)' in source
