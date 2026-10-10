"""Index-first workspace must keep fixed navigation and business bindings."""
from pathlib import Path

from picture_capture.ui import workspace_tools


def test_index_first_workspace_preserves_page_list_and_project_footer():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (root / "app.py").read_text(encoding="utf-8")
    assert "install_workspace_tools(self, sidebar)" in app
    assert "self._build_quick_settings(controls)" not in app
    assert 'page_panel = self._section_frame(sidebar, "六、页面列表"' in app
    assert "self.project_action_bar.pack(side=\"bottom\", fill=\"x\")" in app
    assert '("项目中心", self.open_recent_project)' in app
    assert '("项目Profile", self.open_project_profile)' in app
    assert '("设置中心", self.open_settings)' in app
    assert '("帮助中心", self.show_help_dialog)' in app


def test_workspace_palette_is_nonmodal_and_preserves_quick_builder():
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert "palette.withdraw()" in source
    assert 'palette.protocol("WM_DELETE_WINDOW", palette.withdraw)' in source
    assert "app._build_quick_settings(content)" in source
    assert 'command=lambda: toggle_workspace_tools(app)' in source
    assert "grab_set(" not in source
