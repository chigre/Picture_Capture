"""Contracts for compact layout settings shared with Project Profile."""
from pathlib import Path

from picture_capture.models import AppSettings
from picture_capture.profile_indent_ui import (
    INDENT_TYPE_CHOICES, apply_indent_type_label, indent_type_label,
)
from picture_capture.profile_semantics import (
    READING_LABELS, apply_reading_choice, reading_choice_from_settings,
)
from picture_capture.ui import compact_layout_profile_menu
from picture_capture.ui import compact_task_menus, workspace_tools

BASE = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_metadata_and_reading_bind_to_real_project_profile_fields():
    mod = compact_layout_profile_menu
    assert mod.PROFILE_TEXT_FIELDS == (
        ("词典全称", "dictionary_full_name"),
        ("词典简称(字母)", "dictionary_abbreviation"),
        ("ISBN", "dictionary_isbn"),
        ("正文页码", "dictionary_body_page_range"),
    )
    assert list(READING_LABELS.values()) == [
        "横排：左→右", "横排：右→左",
        "纵排：右→左", "纵排：左→右",
    ]
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "apply_reading_choice(app.settings, selected)" in source
    assert "apply_indent_type_label(app.settings, raw)" in source
    assert "app.save_settings()" in source
    assert "panel.refresh_from_settings = refresh" in source
    assert "app.sync_quick_settings()" in source
    rail = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'refresh = getattr(section, "refresh_from_settings", None)' in rail


def test_reading_and_indent_options_have_real_semantic_backends():
    s = AppSettings()
    for choice, text in READING_LABELS.items():
        apply_reading_choice(s, choice)
        assert reading_choice_from_settings(s) == choice
        assert text in READING_LABELS.values()
    for choice in INDENT_TYPE_CHOICES:
        apply_indent_type_label(s, choice)
        assert indent_type_label(s) == choice


def test_all_seven_backend_auto_checkboxes_and_two_read_only_placeholders():
    rows = compact_layout_profile_menu.LAYOUT_ROWS
    assert len(rows) == 9
    assert [row[2] for row in rows] == [
        "ordinary_auto_columns",
        "ordinary_auto_start_y",
        "ordinary_auto_manual_x",
        "ordinary_auto_column_width",
        "ordinary_auto_gutter",
        "ordinary_auto_character_height",
        "ordinary_auto_row_padding",
        None, None,
    ]
    assert [row[1] for row in rows][-2:] == [
        "body_indent", "horizontal_tolerance",
    ]
    source = Path(compact_layout_profile_menu.__file__).read_text(encoding="utf-8")
    assert 'if auto_name is None:' in source
    assert 'state="disabled"' in source
    assert 'variable=tk.BooleanVar(value=False)' in source
    assert 'app.quick_bool_vars[auto_name] = variable' in source
    assert 'command=app._quick_parameter_changed' in source
    assert 'state = "normal" if bool(master.get()) else "disabled"' in source
    assert 'text="使用自动版面参数", variable=master' in source
    assert 'auto_row = row()' in source
    assert 'auto_row, text="自动检测", command=app.detect_layout_current' in source
    assert 'detect_button.pack(side="left", padx=(5, 0), pady=(0, 2))' in source


def test_per_field_percent_and_px_rows_reuse_quick_settings():
    source = Path(compact_layout_profile_menu.__file__).read_text(encoding="utf-8")
    app_source = (BASE / "app.py").read_text(encoding="utf-8")
    assert 'textvariable=app.quick_vars[name]' in source
    assert 'textvariable=app.quick_pixel_vars[name]' in source
    state = (BASE / "ui/quick_state.py").read_text(encoding="utf-8")
    assert '"body_indent": float' in state
    assert 'app.quick_pixel_vars[name] = tk.StringVar(' in state
    assert 'app._quick_pixel_parameter_changed(field)' in state
    assert 'app._quick_percent_parameter_changed(field)' in state
    assert "return build_layout_profile_menu(app, parent)" in Path(
        compact_task_menus.__file__
    ).read_text(encoding="utf-8")


def test_header_footer_side_and_ab_controls_use_profile_setup_semantics():
    source = Path(compact_layout_profile_menu.__file__).read_text(encoding="utf-8")
    for label, name in [
        ("页眉:", "profile_header_mode"),
        ("页尾:", "profile_footer_mode"),
        ("页边内容:", "profile_side_content_mode"),
        ("排除高度%", "profile_header_percent"),
        ("排除高度%", "profile_footer_percent"),
        ("固定页边宽度%", "profile_side_percent"),
        ("A页排除宽度%", "profile_side_percent_a"),
        ("B页排除宽度%", "profile_side_percent_b"),
    ]:
        assert f'("{label}", "{name}"' in source
    assert 'choice("profile_first_page_variant", "A/B起始页", ("A", "B"))' in source
    assert 'app.settings.profile_page_pair_mode = (' in source
    assert '"alternate" if selected in {"outer", "inner"} else "same"' in source
    assert "if not 0 <= val <= limit:" in source


def test_crop_width_lives_in_postproduction_and_reuses_live_float_setting():
    source = Path(compact_layout_profile_menu.__file__).read_text(encoding="utf-8")
    from picture_capture.ui import compact_task_menus, compact_display_menu
    post = Path(compact_task_menus.__file__).read_text(encoding="utf-8")
    display = Path(compact_display_menu.__file__).read_text(encoding="utf-8")
    assert 'caption(ratio_row, "向右比例%", 15)' not in source
    assert 'textvariable=app.quick_vars["right_ratio"]' not in source
    assert 'value(row, "向右比例%", "right_ratio", 4)' in display
    assert post.index('_label(width_row, "切图宽度(%)")') < post.index(
        'for group in POSTPRODUCTION_ACTIONS:'
    )
    assert 'width_row, app.quick_vars["crop_width_percent"], 5, app._quick_parameter_changed' in post
    assert "ordinary_host.pack_forget()" in source
    assert "illustrated_host.pack(fill=" in source
    from picture_capture.models import AppSettings
    from picture_capture.ui.quick_state import QUICK_FIELD_TYPES
    assert AppSettings().right_ratio == 100.0
    assert AppSettings().crop_width_percent == 100.0
    assert QUICK_FIELD_TYPES["right_ratio"] is float
    assert QUICK_FIELD_TYPES["crop_width_percent"] is float
    app = (BASE / "app.py").read_text(encoding="utf-8")
    assert 'if name == "right_ratio" and not 1 <= float(value) <= 100:' in app


def test_review_right_panel_opens_only_reference_list_by_default():
    source = (BASE / "app.py").read_text(encoding="utf-8")
    start = source.index("self.review_right_section_expanded = {")
    end = source.index("self._review_right_sections:", start)
    initial = source[start:end]
    assert 'value=(key == "reference")' in initial
    assert '("display", "digit", "accent", "ocr", "network", "reference")' in initial
    assert 'value=(key not in {"digit", "accent"})' not in initial
    assert 'right, "reference", "参考词表",' in source
    assert 'fill="both", expand=True, pady=(0, 0)' in source
    assert 'def _toggle_review_right_section(self, key: str)' in source
    assert 'body.pack_forget()' in source
    assert 'body.pack(fill="both", expand=True)' in source


def test_layout_autodetect_button_reuses_seven_field_range_detector():
    source = Path(compact_layout_profile_menu.__file__).read_text(encoding="utf-8")
    app_source = (BASE / "app.py").read_text(encoding="utf-8")
    process = (BASE / "processing_core.py").read_text(encoding="utf-8")
    parent = source.index('auto_row = row()')
    checkbox = source.index('text="使用自动版面参数"', parent)
    button = source.index('text="自动检测", command=app.detect_layout_current', parent)
    rows = source.index('for title, name, auto_name in LAYOUT_ROWS:', parent)
    assert parent < checkbox < button < rows
    assert 'app._attach_tooltip(\n        detect_button,' in source
    assert 'def detect_layout_current(self) -> None:' in app_source
    assert 'return _run_detect_layout_current(self)' in app_source
    detector = (BASE / "layout_detection_actions.py").read_text(encoding="utf-8")
    detector = detector.split('def detect_layout_current(self) -> None:', 1)[1].split(
        'def detect_layout_consistency_selected(self)', 1
    )[0]
    assert 'indices = self.selected_page_indices()' in detector
    assert 'return detect_layout_parameters(opened, settings)' in detector
    assert 'aggregate_layout_estimates(' in detector
    assert 'self.sync_quick_settings(); self.save_settings(); self.redraw()' in detector
    assert 'if name == "bottom_y":' in detector
    assert 'if body_indent_was_auto:' in detector
    assert 'if horizontal_tolerance_was_auto:' in detector
    assert process.count('"ordinary_auto_') >= 7
    from picture_capture.processing_core import ORDINARY_AUTO_LAYOUT_FIELDS
    assert tuple(name for name, _switch in ORDINARY_AUTO_LAYOUT_FIELDS) == (
        "columns", "start_y", "manual_x", "column_width", "gutter",
        "character_height", "row_padding",
    )
