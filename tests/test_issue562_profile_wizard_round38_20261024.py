"""Round 38 — Wizard shell, reading/OCR and headword help canonical owners."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture.profile import (
    setup, wizard_shell_builder, wizard_reading_controls, wizard_headword_explanations,
)

ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture/profile"


def _legacy_methods():
    source = (ROOT / "setup.py").read_text(encoding="utf-8")
    cls = next(item for item in ast.parse(source).body if isinstance(item, ast.ClassDef) and item.name == "ProjectProfileWizard")
    return source, {item.name: item for item in cls.body if isinstance(item, ast.FunctionDef)}


def test_round38_legacy_signatures_and_canonical_physical_owners():
    source, methods = _legacy_methods()
    mappings = {
        "_build_ui": "_wizard_shell_builder.build_ui(",
        "_apply_initial_pane_split": "_wizard_shell_builder.apply_initial_pane_split(",
        "_apply_left_wraps": "_wizard_shell_builder.apply_left_wraps(",
        "_show_right_image_page": "_wizard_shell_builder.show_right_image_page(",
        "_on_wizard_tab_changed": "_wizard_shell_builder.on_wizard_tab_changed(",
        "_build_reading_tab": "_wizard_reading_controls.build_reading_tab(",
        "_build_language_section": "_wizard_reading_controls.build_language_section(",
        "_body_page_range_changed": "_wizard_reading_controls.body_page_range_changed(",
        "_refresh_language_summary": "_wizard_reading_controls.refresh_language_summary(",
        "_refresh_headword_description": "_wizard_headword_explanations.refresh_headword_description(",
        "_refresh_headword_structure_summary": "_wizard_headword_explanations.refresh_headword_structure_summary(",
        "_refresh_headword_specificity_visibility": "_wizard_headword_explanations.refresh_headword_specificity_visibility(",
    }
    for name, owner in mappings.items():
        text = ast.get_source_segment(source, methods[name])
        assert owner in text
        assert len(text.splitlines()) < 25
    assert list(inspect.signature(setup.ProjectProfileWizard._build_language_section).parameters) == ["self", "parent", "row"]
    assert inspect.signature(setup.ProjectProfileWizard._build_language_section).parameters["row"].kind is inspect.Parameter.KEYWORD_ONLY
    assert list(inspect.signature(setup.ProjectProfileWizard._body_page_range_changed).parameters) == ["self", "_event"]
    for file in ("wizard_shell_builder.py", "wizard_reading_controls.py", "wizard_headword_explanations.py"):
        assert "from .setup import" not in (ROOT / file).read_text(encoding="utf-8")


def test_round38_wizard_original_entrypoints_forward_live_globals(monkeypatch):
    calls = []
    monkeypatch.setattr(wizard_shell_builder, "build_ui", lambda obj, *, deps: calls.append(("ui", obj, deps)))
    monkeypatch.setattr(wizard_shell_builder, "apply_left_wraps", lambda obj, *, deps: calls.append(("wrap", obj, deps)))
    monkeypatch.setattr(wizard_shell_builder, "on_wizard_tab_changed", lambda obj, event, *, deps: calls.append(("tab", obj, event, deps)))
    monkeypatch.setattr(wizard_reading_controls, "build_reading_tab", lambda obj, tab, *, deps: calls.append(("reading", obj, tab, deps)))
    monkeypatch.setattr(wizard_reading_controls, "build_language_section", lambda obj, parent, *, row, deps: calls.append(("language", obj, parent, row, deps)))
    monkeypatch.setattr(wizard_reading_controls, "body_page_range_changed", lambda obj, event, *, deps: calls.append(("range", obj, event, deps)))
    monkeypatch.setattr(wizard_reading_controls, "refresh_language_summary", lambda obj, *, deps: calls.append(("summary", obj, deps)))
    monkeypatch.setattr(wizard_headword_explanations, "refresh_headword_description", lambda obj, *, deps: calls.append(("help", obj, deps)))
    monkeypatch.setattr(wizard_headword_explanations, "refresh_headword_structure_summary", lambda obj: calls.append(("structure", obj)))
    monkeypatch.setattr(wizard_headword_explanations, "refresh_headword_specificity_visibility", lambda obj: calls.append(("visibility", obj)))
    obj = setup.ProjectProfileWizard.__new__(setup.ProjectProfileWizard)
    parent = SimpleNamespace()
    event = object()
    obj._build_ui()
    obj._apply_left_wraps()
    obj._on_wizard_tab_changed(event)
    obj._build_reading_tab(parent)
    obj._build_language_section(parent, row=4)
    obj._body_page_range_changed(event)
    obj._refresh_language_summary()
    obj._refresh_headword_description()
    obj._refresh_headword_structure_summary()
    obj._refresh_headword_specificity_visibility()
    assert [x[0] for x in calls] == ["ui", "wrap", "tab", "reading", "language", "range", "summary", "help", "structure", "visibility"]
    assert calls[0][2]["ttk"] is setup.ttk and calls[1][2]["tk"] is setup.tk
    assert calls[2][2] is event and calls[3][2] is parent
    assert calls[3][3]["READING_LABELS"] is setup.READING_LABELS
    assert calls[4][2:4] == (parent, 4) and calls[4][4]["OCR_LANGUAGE_LABEL_TO_VALUE"] is setup.OCR_LANGUAGE_LABEL_TO_VALUE
    assert calls[5][2] is event and calls[5][3]["representative_page_indices"] is setup.representative_page_indices
    assert calls[6][2]["language_effective_settings"] is setup.language_effective_settings
    assert calls[7][2]["dictionary_profile_preset"] is setup.dictionary_profile_preset
    assert calls[7][2]["HEADWORD_HELP_LINES"] is setup.HEADWORD_HELP_LINES


def test_round38_shell_keeps_wizard_sash_tabs_and_ui_navigation():
    owner = (ROOT / "wizard_shell_builder.py").read_text(encoding="utf-8")
    assert 'self.profile_paned.add(left_panel, weight=40)' in owner
    assert 'self.profile_paned.add(right_panel, weight=60)' in owner
    assert 'self.profile_paned.sashpos(0, round(pane_width * 0.40))' in owner
    for title in ('"1 词典与阅读"', '"2 页面模板"', '"3 词头结构"', '"4 测试确认"'):
        assert title in owner
    assert "self._build_right_image_workspace(right_panel)" in owner
    assert "self._build_reading_tab(self.tab_contents[0])" in owner
    assert "self._build_validation_tab(self.tab_contents[3])" in owner
    assert "self.notebook.bind(\"<<NotebookTabChanged>>\"" in owner
    assert "self.after_idle(self._apply_initial_pane_split)" in owner
    assert 'left_panel.bind(' in owner
    assert 'child.configure(wraplength=wrap, justify="left")' in owner


def test_round38_reading_controls_preserve_ocr_and_body_range_revisions():
    owner = (ROOT / "wizard_reading_controls.py").read_text(encoding="utf-8")
    for text in ('text="词典全称："', 'text="词典简称(字母)："', 'text="ISBN："', 'text="正文页码："', 'text="索引语言（2 位）"'):
        assert text in owner
    assert 'self.body_page_range_entry.bind("<FocusOut>", self._body_page_range_changed)' in owner
    assert 'self._build_language_section(tab, row=4)' in owner
    assert "add_wizard_layout_selector(self, tab, row=6)" in owner
    assert 'combo.bind("<<ComboboxSelected>>", lambda _e: self._ocr_language_changed())' in owner
    assert '"write", lambda *_args: self.after_idle(self._refresh_language_summary)' in owner
    assert "configured_body_page_indices(len(self.project.images), raw)" in owner
    assert "self._profile_revision += 1" in owner
    assert "self._mark_validation_stale()" in owner
    assert "self._start_sample_thumbnail_load()" in owner
    assert "if self.notebook.index(self.notebook.select()) == 1:" in owner
    assert "language_effective_settings(language, temp.layout_writing_mode)" in owner


def test_round38_headword_help_cjk_and_tail_structure_remain_visible():
    owner = (ROOT / "wizard_headword_explanations.py").read_text(encoding="utf-8")
    assert "dictionary_profile_preset(key)" in owner
    assert "self._refresh_headword_structure_summary()" in owner
    assert "self._refresh_headword_specificity_visibility()" in owner
    assert "HEADWORD_HELP_LINES" in owner
    assert '"latin_regular"' in owner
    assert '"cjk_visual"' in owner
    assert "self.headword_help_frame" in owner
    assert "self.tail_structure_summary_var.set(" in owner
    assert "self.headword_structure_summary_var.set(" in owner
    assert "self.cjk_specificity_frame.grid_remove()" in owner
    assert "self.symbol_inventory_frame.grid_remove()" in owner
