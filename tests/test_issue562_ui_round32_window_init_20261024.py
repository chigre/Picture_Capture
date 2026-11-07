"""Round 32: full Tk SettingsDialog / ReviewWindow constructor separation."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from picture_capture import app as gui
from picture_capture.ui.settings import dialog_initialization
from picture_capture.ui import review_window_initialization


def test_only_canonical_submodules_own_window_widget_initialization():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(pkg.glob("*.py"))) == 5
    mapping = {
        "ui/settings/dialog_initialization.py": {"initialize_settings_dialog"},
        "ui/review_window_initialization.py": {"initialize_review_window"},
    }
    for path, functions in mapping.items():
        source = pkg / path
        assert source.is_file() and not (pkg / source.name).exists()
        tree = ast.parse(source.read_text(encoding="utf-8"))
        assert {n.name for n in tree.body if isinstance(n, ast.FunctionDef)} == functions
        assert not any(isinstance(n, (ast.ClassDef, ast.Assign, ast.AnnAssign)) for n in tree.body)
        impl = source.read_text(encoding="utf-8")
        assert "super().__init__(" not in impl.split("def initialize_", 1)[1]
    assert list(inspect.signature(gui.SettingsDialog.__init__).parameters) == [
        "self", "parent", "initial_tab",
    ]
    assert list(inspect.signature(gui.ReviewWindow.__init__).parameters) == [
        "self", "parent",
    ]
    assert gui.SettingsDialog.__init__.__module__ == "picture_capture.app"
    assert gui.ReviewWindow.__init__.__module__ == "picture_capture.app"


def test_old_constructors_initialize_toplevel_before_delegation(monkeypatch):
    steps = []
    def fake_super(self, parent):
        steps.append(("toplevel", self, parent))
    monkeypatch.setattr(gui.tk.Toplevel, "__init__", fake_super)
    def settings_spy(self, parent, initial_tab=None, *, deps):
        steps.append(("settings", self, parent, initial_tab, deps))
    def review_spy(self, parent, *, deps):
        steps.append(("review", self, parent, deps))
    monkeypatch.setattr(dialog_initialization, "initialize_settings_dialog", settings_spy)
    monkeypatch.setattr(review_window_initialization, "initialize_review_window", review_spy)
    owner = object()
    settings = gui.SettingsDialog.__new__(gui.SettingsDialog)
    review = gui.ReviewWindow.__new__(gui.ReviewWindow)
    gui.SettingsDialog.__init__(settings, owner, initial_tab="ocr")
    gui.ReviewWindow.__init__(review, owner)
    assert [s[0] for s in steps] == ["toplevel", "settings", "toplevel", "review"]
    assert steps[0][1:3] == (settings, owner)
    assert steps[1][1:4] == (settings, owner, "ocr")
    assert steps[2][1:3] == (review, owner)
    assert steps[3][1:3] == (review, owner)
    settings_deps = steps[1][4]
    review_deps = steps[3][3]
    assert settings_deps["ttk"] is gui.ttk
    assert settings_deps["LATIN_ORDER"] == gui.LATIN_ORDER
    assert settings_deps["DETECTION_LABELS"] is gui.DETECTION_LABELS
    assert settings_deps["_settings_illustration_ui"] is gui._settings_illustration_ui
    assert settings_deps["fit_window_to_work_area"] is gui.fit_window_to_work_area
    assert review_deps["tk"] is gui.tk
    assert review_deps["threading"] is gui.threading
    assert review_deps["_review_window_dimensions"] is gui._review_window_dimensions


def test_settings_constructor_retains_full_tabs_help_auto_save_and_no_modal_grab():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (pkg / "app.py").read_text(encoding="utf-8")
    settings = (pkg / "ui/settings/dialog_initialization.py").read_text(encoding="utf-8")
    assert "_settings_dialog_initialization.initialize_settings_dialog(" in app
    for anchor in (
        'self.title("设置中心")',
        "self._scrollable_settings_page(",
        "self._add_setting_group(",
        "self._add_check_group(",
        "self._settings_help_body_var",
        "notebook.bind(",
        "self._build_crop_settings_tab(",
        "self._profile_label_to_key",
        'self.protocol("WM_DELETE_WINDOW", self._close_validated)',
        'trace_add("write", lambda *_args: self._schedule_autosave())',
    ):
        assert anchor in settings
    tree = ast.parse(settings)
    init = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "initialize_settings_dialog")
    assert not any(
        isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
        and x.func.attr in {"transient", "grab_set"}
        for x in ast.walk(init)
    )


def test_review_constructor_keeps_source_geometry_sidebar_and_live_event_bindings():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (pkg / "app.py").read_text(encoding="utf-8")
    source = (pkg / "ui/review_window_initialization.py").read_text(encoding="utf-8")
    assert "_review_window_initialization.initialize_review_window(" in app
    assert "from .workspace_tools import _preset_work_geometry" in source
    for token in (
        "self.geometry(", "self.minsize(",
        "self._configure_review_styles()",
        "self._build()",
        "self.after_idle(self._initialize_review_layout_and_rows)",
        "self.digit_map_vars",
        'self.protocol("WM_DELETE_WINDOW", self._close_review)',
        'self.review_extended_crop_multiplier_var.trace_add(',
    ):
        assert token in source


def test_extracted_review_window_keeps_annotation_only_entry_identity():
    from pathlib import Path
    owner = (Path(__file__).resolve().parents[1] / "src/picture_capture/ui/review_window_initialization.py").read_text(encoding="utf-8")
    assert "from ..models import AppSettings, Entry as WordEntry" in owner
    assert "self.row_entries: list[WordEntry] = []" in owner
    assert "from ..app import" not in owner
