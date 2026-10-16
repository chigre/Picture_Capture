"""Compact OCR Profile and ordinary visual-evidence menu regressions."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.models import AppSettings
from picture_capture.ui import compact_headword_profile_menu as ocr
from picture_capture.ui import compact_ordinary_evidence_menu as visual
from picture_capture.ui import compact_profile_persistence as persistence
from picture_capture.ui import compact_layout_profile_menu as layout
from picture_capture.ui import workspace_tools

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_menu_placement_and_profile_refresh_owner():
    groups = list(workspace_tools.TASK_GROUPS)
    labels = [group[0] for group in groups]
    assert labels.index("OCR画线设置") == labels.index("OCR参数") + 1
    assert groups[labels.index("OCR画线设置")] == (
        "OCR画线设置", "▣", "三之一、OCR画线设置",
    )
    source = Path(workspace_tools.__file__).read_text(encoding="utf-8")
    assert 'sections["三之一、OCR画线设置"] = build_headword_profile_menu(app, content)' in source
    assert 'refresh = getattr(section, "refresh_from_settings", None)' in source

    layout_src = Path(layout.__file__).read_text(encoding="utf-8")
    first = layout_src.index('choice("profile_first_page_variant", "A/B起始页", ("A", "B"))')
    second = layout_src.index("_divider(ordinary_host)", first)
    third = layout_src.index("build_ordinary_visual_evidence(app, ordinary_host)", second)
    assert first < second < third
    assert "ordinary_visual_panel.refresh_from_settings()" in layout_src


def test_visual_evidence_reuses_profile_samples_and_dialogs():
    src = Path(visual.__file__).read_text(encoding="utf-8")
    for caption in (
        "普通模式画线：视觉词头证据", "启用大字头detector（CJK）",
        "从页面采样...", "查看/删除样本", "匹配阈值",
    ):
        assert caption in src
    assert "VisualMarkerCaptureDialog(" in src
    assert "VisualMarkerSamplesDialog(" in src
    assert "serialize_visual_marker_samples(" in src
    assert "parse_visual_marker_samples(" in src
    assert "profile_cjk_allow_single_headword" in src
    assert "0.35 <= value <= 0.95" in src


def test_ocr_profile_fields_have_single_settings_backend():
    specs = (*ocr.HEADWORD_CHECKS, *ocr.TAIL_CHECKS, *ocr.SYMBOL_CHECKS,
             *ocr.CJK_CHECKS)
    fields = [field for _label, field, _group in specs]
    fields += ["profile_entry_marker_symbols", "profile_bracket_open_symbols"]
    fields += list(ocr.NUMBER_BOUNDS)
    settings = AppSettings()
    assert len(fields) == len(set(fields))
    assert all(hasattr(settings, name) for name in fields)
    src = Path(ocr.__file__).read_text(encoding="utf-8")
    for caption in (
        "词头结构", "词后结构", "词头专属性（当前结构的视觉证据）",
        "CJK单字/括号词附加条件", "使用同栏 marker lane",
        "按OCR语言排除不兼容", "独立入口标记", "括号词头起始",
    ):
        assert caption in src
    assert "panel.refresh_from_settings = refresh" in src


def test_specificity_percent_converts_to_pixels_and_ranges_are_checked():
    settings = AppSettings()
    settings.column_width = 600
    settings.paddle_left_tolerance = 30
    assert ocr.read_profile_numeric(settings, "paddle_left_tolerance") == 5.0
    assert ocr.parse_profile_numeric(settings, "paddle_left_tolerance", "7.5") == 45
    assert ocr.parse_profile_numeric(settings, "paddle_height_ratio", "1.08") == 1.08
    assert ocr.parse_profile_numeric(settings, "profile_symbol_lane_tolerance_percent", "45") == 45
    assert ocr.parse_profile_numeric(settings, "profile_cjk_right_context_width_percent", "80") == 80
    for name, invalid in (
        ("paddle_left_tolerance", "101"),
        ("profile_symbol_lane_tolerance_percent", "19"),
        ("profile_symbol_lane_tolerance_percent", "45.5"),
        ("profile_cjk_right_context_width_percent", "201"),
        ("paddle_boldness_ratio", "nan"),
        ("paddle_min_candidate_score", "13"),
    ):
        with pytest.raises(ValueError):
            ocr.parse_profile_numeric(settings, name, invalid)


def test_persist_mirrors_profile_wizard_v3_and_invalidates_validation(monkeypatch):
    app = SimpleNamespace(
        settings=AppSettings(), project=SimpleNamespace(root=Path("/tmp/test-dictionary")),
        _batch_active=False, status_var=SimpleNamespace(set=lambda s: None),
    )
    app.settings.profile_last_validated_pages = [1, 2]
    called = []
    app.save_settings = lambda: called.append("save")
    app.sync_quick_settings = lambda: called.append("sync")
    app.redraw = lambda: called.append("redraw")
    monkeypatch.setattr(
        persistence, "write_project_profile",
        lambda path, settings, key, force: called.append(("profile", path, key, force)),
    )
    persistence.persist_profile_changes(app)
    assert app.settings.profile_last_validated_pages == []
    assert [called[0], called[-2], called[-1]] == ["save", "sync", "redraw"]
    assert called[1][0] == "profile" and called[1][-1] is True
    app._batch_active = True
    assert persistence.profile_changes_allowed(app) is False


def test_profile_preset_uses_existing_backend_and_symbol_roles():
    src = Path(ocr.__file__).read_text(encoding="utf-8")
    for snippet in (
        "apply_headword_profile(settings, name)",
        "recommended_headword_structures(name)",
        "profile_tail_structure_defaults(name)",
        "profile_symbol_inventory_defaults(name)",
        "_normalize_cjk_visual_symbol_roles(",
        "settings.profile_parser_controls_version = 1",
        "settings.profile_tail_structure_version = 1",
        "settings.profile_symbol_inventory_version = 1",
        "settings.paddle_allow_strong_edge_visual_rescue = value",
    ):
        assert snippet in src


def test_legacy_profile_alias_uses_same_selection_as_wizard():
    from picture_capture.profile_semantics import ordered_headword_profiles
    choices = ordered_headword_profiles()
    for label, key in choices:
        assert ocr.profile_label_for_current(key, choices) == label
    # The Profile preset resolver maps unknown historic IDs to its custom preset.
    assert ocr.profile_label_for_current("not-a-real-preset", choices) == next(
        label for label, key in choices if key == "custom"
    )
    source = Path(ocr.__file__).read_text(encoding="utf-8")
    assert 'if name == "cjk_visual":' in source
    assert "serialize_visual_marker_samples(samples)" in source
    assert 'settings.paddle_allow_strong_edge_visual_rescue = bool(' in source
