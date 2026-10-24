"""Round 29: original Tk app/settings API and extracted widget ownership."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from picture_capture import app as gui
from picture_capture.ui import main_workspace_build
from picture_capture.ui.settings import interactive_panels


def test_widget_owners_and_historical_class_signatures():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(root.glob("*.py"))) == 10
    expected = {
        "ui/main_workspace_build.py": {"build_ui"},
        "ui/settings/interactive_panels.py": {"add_check_group", "scrollable_settings_page"},
    }
    for relative, names in expected.items():
        source = root / relative
        assert source.is_file() and not (root / source.name).exists()
        tree = ast.parse(source.read_text(encoding="utf-8"))
        assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == names
        assert not any(isinstance(node, (ast.ClassDef, ast.Assign, ast.AnnAssign)) for node in tree.body)
    assert list(inspect.signature(gui.PictureCaptureApp._build_ui).parameters) == ["self"]
    assert list(inspect.signature(gui.SettingsDialog._scrollable_settings_page).parameters) == ["self", "tab"]
    assert list(inspect.signature(gui.SettingsDialog._add_check_group).parameters) == [
        "self", "parent", "title", "checks", "intro",
    ]
    assert gui.PictureCaptureApp._build_ui.__module__ == "picture_capture.app"
    assert gui.SettingsDialog._add_check_group.__module__ == "picture_capture.app"


def test_app_and_dialog_methods_forward_live_tk_modules(monkeypatch):
    called = []
    def make_spy(name):
        def spy(self, *args, deps, **kwargs):
            called.append((name, self, args, kwargs, deps))
            return name
        return spy
    monkeypatch.setattr(main_workspace_build, "build_ui", make_spy("workspace"))
    monkeypatch.setattr(interactive_panels, "scrollable_settings_page", make_spy("scroll"))
    monkeypatch.setattr(interactive_panels, "add_check_group", make_spy("checks"))
    owner = object()
    tab = object()
    assert gui.PictureCaptureApp._build_ui(owner) == "workspace"
    assert gui.SettingsDialog._scrollable_settings_page(owner, tab) == "scroll"
    assert gui.SettingsDialog._add_check_group(
        owner, tab, "设置", [("a", "A")], intro="说明",
    ) == "checks"
    assert [x[0] for x in called] == ["workspace", "scroll", "checks"]
    assert all(x[1] is owner for x in called)
    assert called[1][2] == (tab,)
    assert called[2][2] == (tab, "设置", [("a", "A")])
    assert called[2][3]["intro"] == "说明"
    for _, _, _, _, deps in called:
        assert deps["ttk"] is gui.ttk
        assert deps["tk"] is gui.tk


def test_workspace_and_help_geometry_conventions_are_preserved():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (root / "app.py").read_text(encoding="utf-8")
    workspace = (root / "ui/main_workspace_build.py").read_text(encoding="utf-8")
    panels = (root / "ui/settings/interactive_panels.py").read_text(encoding="utf-8")
    assert "_main_workspace_build.build_ui(" in app
    assert "_interactive_settings_panels.scrollable_settings_page(" in app
    assert "_interactive_settings_panels.add_check_group(" in app
    assert 'self.status_bar.pack(side="bottom", fill="x")' in workspace
    assert 'install_workspace_tools(self, sidebar, sidebar_host)' in workspace
    assert "self._apply_initial_section_states()" in workspace
    assert "help_canvas.yview_scroll(" in panels
    assert "textvariable=self._settings_help_body_var" in panels
    assert 'child_row = 0 if index < 3 else 1' in panels
    assert 'child_col = index if index < 3 else index - 3' in panels
