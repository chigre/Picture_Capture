"""Index-first main window and real right-side dock regression coverage."""
from pathlib import Path

from picture_capture.ui import workspace_tools


def test_index_first_workspace_preserves_page_index_and_four_fixed_buttons():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (root / "app.py").read_text(encoding="utf-8")
    assert "install_workspace_tools(self, sidebar)" in app
    assert "self._build_quick_settings(controls)" not in app
    assert 'page_panel = self._section_frame(sidebar, "六、页面列表"' in app
    assert 'self.project_action_bar.pack(side="bottom", fill="x")' in app
    for action in ("项目中心", "项目Profile", "设置中心", "帮助中心"):
        assert f'("{action}", self.' in app


def test_workspace_dock_is_embedded_and_preserves_widgets_when_hidden():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert "ttk.Frame(panes" in source
    assert "panes.add(dock, weight=0)" in source
    assert "app.main_paned.forget(app.workspace_tools_dock)" in source
    assert "app._build_quick_settings(content)" in source
    assert "panes.sashpos(1, total - width)" in source
    assert "tk.Toplevel(" not in source
    assert "grab_set(" not in source


def test_task_shortcuts_group_navigation_and_keyboard():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'jump.bind("<<ComboboxSelected>>", on_select)' in source
    assert "app._set_section_expanded(candidate, candidate is section)" in source
    assert "app._set_section_expanded(section, True)" in source
    assert 'app.bind("<Control-Shift-t>"' in source
    assert 'app.bind("<Control-k>"' in source
    assert 'dock.bind("<Escape>"' in source
    assert 'menu_button.configure(menu=task_menu)' in source
    assert 'for label, title in TASK_GROUPS:' in source
    assert '("OCR", "三、共享 OCR 通道 / OCR画线")' in source
    assert '("画线/校对", "四、画线 / OCR / 插图 / 校对")' in source
    assert 'shortcuts.grid(row=2' not in source


def test_narrow_dock_preserves_access_to_wide_controls():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'orient="horizontal", command=canvas.xview' in source
    assert 'width=max(e.width, content.winfo_reqwidth())' in source
