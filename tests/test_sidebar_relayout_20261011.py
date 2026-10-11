"""Regression checks for persistent mode menu, simple page controls and rail density."""
from pathlib import Path

from picture_capture.ui import workspace_tools
from picture_capture.ui import simple_page_controls

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_window_mode_menu_is_click_to_open_not_hover_to_dismiss():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'lambda: toggle_sidebar_modes(app)' in source
    assert 'def toggle_sidebar_modes(app: Any)' in source
    assert 'def dismiss_mode_on_outside_click(event: tk.Event)' in source
    assert 'not _within(event.widget, mode_menu)' in source
    assert 'mode_menu.place_forget()' in source
    assert 'schedule_mode_hide' not in source
    assert 'mode_menu, *mode_menu.winfo_children()' not in source
    assert 'widget.bind("<Leave>", schedule_mode_hide' not in source


def test_light_and_dark_use_same_compact_button_geometry():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'style="PC.Sidebar.TFrame", width=155, height=33' in source
    assert 'entry.grid_propagate(False)' in source
    assert 'entry.configure(width=36 if extreme else 155)' in source
    assert 'padding=(0, 0), relief="flat"' in app
    assert 'style.configure("PC.QuickRail.TButton", font="TkDefaultFont"' in app
    assert 'padding=(0, 0), relief="flat"' in source


def test_simple_mode_clones_complete_range_and_navigation_controls():
    tools = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    controls = Path(simple_page_controls.__file__).read_text(encoding="utf-8")
    assert 'install_simple_page_controls(app, mini_host)' in tools
    assert 'install_simple_page_tree_actions(app, mini)' in tools
    assert 'displaycolumns=("bookmark", "page", "lined", "illustrations")' in tools
    for label in ('"当前"', '"至末页"', '"至指定页"',
                  '"指定"', '"跳"', '"⨇"', '"⨈"', '"上"', '"下"'):
        assert label in controls
    assert 'variable=app.page_range_var' in controls
    assert 'textvariable=app.page_range_spec_var' in controls
    assert 'command=app.jump_to_page_spec' in controls
    assert 'app.jump_to_bookmark(-1)' in controls
    assert 'app.jump_to_bookmark(1)' in controls
    assert 'app.change_page(-1)' in controls
    assert 'app.change_page(1)' in controls
    assert 'app._bookmark_stems()' in controls
    assert 'app._set_page_section_count(index, updated)' in controls
    assert '"跳转到指定页面的第一个有效页面；ENTER为快捷键"' in controls
    assert 'style="PC.SimplePage.TButton"' in controls
    assert 'padx=0, pady=0' in controls


def test_quick_actions_are_always_short_and_horizontal_except_extreme():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'app.workspace_quick_actions_host = quick_host' in source
    assert '("普", "O", "校")[index]' in source
    assert 'style="PC.QuickRail.TButton"' in source
    assert 'button.configure(text=title, width=2)' in source
    assert 'row=index if extreme else 0' in source
    assert 'column=0 if extreme else index' in source
    assert 'sticky="ew", padx=0, pady=0' in source
    assert 'button.configure(text=compact if extreme else ordinary' not in source
