"""Round 30: settings form/save and proofreading ttk style ownership."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from picture_capture import app as gui
from picture_capture.ui.settings import field_form_runtime
from picture_capture.ui import review_style_policy


def test_owners_are_parseable_functions_and_no_root_shims():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(root.glob("*.py"))) == 10
    owners = {
        "ui/settings/field_form_runtime.py": {
            "setting_widget", "add_setting_group", "save_settings",
        },
        "ui/review_style_policy.py": {"configure_review_styles"},
    }
    for rel, funcs in owners.items():
        source = root / rel
        assert source.is_file()
        assert not (root / source.name).exists()
        tree = ast.parse(source.read_text(encoding="utf-8"))
        assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == funcs
        assert not any(isinstance(node, (ast.ClassDef, ast.Assign, ast.AnnAssign)) for node in tree.body)


def test_old_api_signatures_and_module_origin():
    expected = (
        (gui.SettingsDialog._setting_widget, ["self", "parent", "name"]),
        (gui.SettingsDialog._add_setting_group, [
            "self", "parent", "title", "names", "intro", "help_images", "single_line_labels",
        ]),
        (gui.SettingsDialog.save, ["self", "close", "show_errors"]),
        (gui.ReviewWindow._configure_review_styles, ["self"]),
    )
    for method, args in expected:
        assert method.__module__ == "picture_capture.app"
        assert list(inspect.signature(method).parameters) == args


def test_form_and_review_methods_supply_current_patchable_dependencies(monkeypatch):
    calls = []
    def fake(name):
        def inner(owner, *args, deps, **kwargs):
            calls.append((name, owner, args, kwargs, deps))
            return name
        return inner
    monkeypatch.setattr(field_form_runtime, "setting_widget", fake("widget"))
    monkeypatch.setattr(field_form_runtime, "add_setting_group", fake("group"))
    monkeypatch.setattr(field_form_runtime, "save_settings", fake("save"))
    monkeypatch.setattr(review_style_policy, "configure_review_styles", fake("review"))

    owner = object()
    parent = object()
    assert gui.SettingsDialog._setting_widget(owner, parent, "ocr_language") == "widget"
    assert gui.SettingsDialog._add_setting_group(
        owner, parent, "普通参数", ["columns"], intro="说明",
        help_images=True, single_line_labels=True,
    ) == "group"
    assert gui.SettingsDialog.save(owner, close=False, show_errors=False) == "save"
    assert gui.ReviewWindow._configure_review_styles(owner) == "review"

    assert [item[0] for item in calls] == ["widget", "group", "save", "review"]
    assert all(item[1] is owner for item in calls)
    assert calls[1][3] == {
        "intro": "说明", "help_images": True, "single_line_labels": True,
    }
    assert calls[2][3] == {"close": False, "show_errors": False}
    assert calls[0][4]["font"] is gui.font
    assert calls[0][4]["ttk"] is gui.ttk
    assert calls[1][4]["font"] is gui.font
    assert calls[2][4]["_layout_percent_to_pixels"] is gui._layout_percent_to_pixels
    assert calls[2][4]["parse_headword_filter_rules"] is gui.parse_headword_filter_rules
    assert calls[2][4]["messagebox"] is gui.messagebox
    assert calls[3][4]["appearance_palette"] is gui.appearance_palette


def test_original_settings_validation_and_review_style_tokens_preserved():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (root / "app.py").read_text(encoding="utf-8")
    forms = (root / "ui/settings/field_form_runtime.py").read_text(encoding="utf-8")
    review = (root / "ui/review_style_policy.py").read_text(encoding="utf-8")
    assert "_settings_field_form.save_settings(" in app
    assert "_settings_field_form.setting_widget(" in app
    assert "_settings_field_form.add_setting_group(" in app
    assert "_review_style_policy.configure_review_styles(" in app
    for required in (
        "validate_projection_width(", "validate_separator_gap_controls(",
        "validate_ref_box_controls(", "validate_color_controls(",
        "profile_header_percent", "profile_footer_percent",
        "normalize_content_font_setting(", "parse_headword_filter_rules(",
        "write_project_profile(", "sync_quick_settings()",
    ):
        assert required in forms
    for style in ("PCR.Surface.TFrame", "PCR.Toolbar.TFrame", "PCR.Header.TLabel"):
        assert style in review
