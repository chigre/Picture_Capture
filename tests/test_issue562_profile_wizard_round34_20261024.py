"""Round 34: large Profile Wizard form/body/headword extraction without changing Tk contracts."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from picture_capture.profile import setup, wizard_state_initialization, wizard_tab_builders

ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture/profile"


def _method(source: str, name: str):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ProjectProfileWizard")
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)


def test_original_wizard_entrances_and_canonical_ast_owners():
    original = (ROOT / "setup.py").read_text(encoding="utf-8")
    state = (ROOT / "wizard_state_initialization.py").read_text(encoding="utf-8")
    tabs = (ROOT / "wizard_tab_builders.py").read_text(encoding="utf-8")
    for method, forward in (
        ("_build_vars", "_wizard_wizard_state_initialization.build_vars("),
        ("_build_template_tab", "_wizard_wizard_tab_builders.build_template_tab("),
        ("_build_headword_tab", "_wizard_wizard_tab_builders.build_headword_tab("),
    ):
        extracted = ast.get_source_segment(original, _method(original, method))
        assert forward in extracted
        assert len(extracted.splitlines()) < 27
    assert len(ast.get_source_segment(state, next(n for n in ast.parse(state).body if isinstance(n, ast.FunctionDef))).splitlines()) > 245
    assert len(tabs.splitlines()) > 500
    assert "self._refresh_symbol_template_summary()" in state
    assert "self.headword_combo.bind(" in tabs
    assert "self._refresh_template_controls()" in tabs
    assert "from .setup import" not in state + tabs


def test_wizard_live_binding_and_signatures(monkeypatch):
    assert str(inspect.signature(setup.ProjectProfileWizard._build_vars)) == "(self) -> 'None'"
    assert "tab" in inspect.signature(setup.ProjectProfileWizard._build_headword_tab).parameters
    assert "tab" in inspect.signature(setup.ProjectProfileWizard._build_template_tab).parameters
    calls = []
    monkeypatch.setattr(wizard_state_initialization, "build_vars", lambda self, *, deps: calls.append(("vars", self, deps)))
    monkeypatch.setattr(wizard_tab_builders, "build_headword_tab", lambda self, tab, *, deps: calls.append(("headword", self, tab, deps)))
    monkeypatch.setattr(wizard_tab_builders, "build_template_tab", lambda self, tab, *, deps: calls.append(("template", self, tab, deps)))
    obj = setup.ProjectProfileWizard.__new__(setup.ProjectProfileWizard)
    tab = object()
    obj._build_vars()
    obj._build_template_tab(tab)
    obj._build_headword_tab(tab)
    assert [c[0] for c in calls] == ["vars", "template", "headword"]
    assert calls[0][1] is obj and calls[1][1:3] == (obj, tab) and calls[2][1:3] == (obj, tab)
    assert calls[0][2]["tk"] is setup.tk
    assert calls[0][2]["parse_visual_marker_samples"] is setup.parse_visual_marker_samples
    assert calls[0][2]["recommended_headword_structures"] is setup.recommended_headword_structures
    assert calls[1][3]["SEPARATOR_LABEL_TO_VALUE"] is setup.SEPARATOR_LABEL_TO_VALUE
    assert calls[2][3]["VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE"] is setup.VISUAL_TEMPLATE_MODE_LABEL_TO_VALUE


def test_profile_tabs_keep_callbacks_and_correct_widget_roles():
    owner = (ROOT / "wizard_tab_builders.py").read_text(encoding="utf-8")
    assert 'text="③ 什么才算一个新词条？"' in owner
    assert 'text="② 正文在哪里？"' in owner
    assert "self._headword_structure_changed" in owner
    assert "self._refresh_template_controls()" in owner
    assert "self.after_idle(self._refresh_template_controls)" in owner
    assert "self.after_idle(self._custom_name_changed)" in owner
