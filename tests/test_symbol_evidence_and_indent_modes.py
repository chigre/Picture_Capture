from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.dictionary_page_design import (
    ColumnDesign,
    DictionaryPageLayout,
    IndentMode,
    LayoutLine,
    PageRegion,
    PageRegions,
)
from picture_capture.layout_transform import LayoutTransform
from picture_capture.models import AppSettings
from picture_capture.page_understanding import _apply_explicit_indent_semantics
from picture_capture.processing import _uses_cjk_indent_topology
from picture_capture.profile_indent_ui import (
    INDENT_SEMANTICS_VERSION,
    apply_indent_type_label,
    indent_type_label,
)
from picture_capture.profile_validation_modes import _understanding_summary
from picture_capture.symbol_evidence import (
    SymbolEvidenceResult,
    detect_symbol_evidence,
    fuse_symbol_evidence,
)
from picture_capture.visual_marker_templates import (
    build_visual_marker_sample,
    serialize_visual_marker_samples,
)


def test_indent_semantics_v3_supports_no_visible_indent_without_breaking_v2() -> None:
    legacy_entry = AppSettings()
    legacy_entry.profile_parser_controls_version = 2
    legacy_entry.profile_cjk_brackets_in_body = False
    assert indent_type_label(legacy_entry) == "词头缩进"

    legacy_body = AppSettings()
    legacy_body.profile_parser_controls_version = 2
    legacy_body.profile_cjk_brackets_in_body = True
    assert indent_type_label(legacy_body) == "正文缩进"

    current = AppSettings()
    apply_indent_type_label(current, "无明显缩进")
    assert current.profile_parser_controls_version >= INDENT_SEMANTICS_VERSION
    assert current.profile_cjk_brackets_in_body is None
    assert indent_type_label(current) == "无明显缩进"

    apply_indent_type_label(current, "正文缩进")
    assert current.profile_cjk_brackets_in_body is True
    assert indent_type_label(current) == "正文缩进"

    apply_indent_type_label(current, "词头缩进")
    assert current.profile_cjk_brackets_in_body is False
    assert indent_type_label(current) == "词头缩进"


def _ring_image(size: int = 24) -> Image.Image:
    image = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse((3, 3, size - 4, size - 4), outline=0, width=4)
    return image


def _simple_layout() -> DictionaryPageLayout:
    transform = LayoutTransform("identity")
    line = LayoutLine(
        column=0,
        y0=36,
        y1=58,
        first_x=6,
        anchor_x=6,
        anchor_width=18,
        anchor_height=20,
        gap_before=16,
        patch=np.zeros((8, 8), dtype=bool),
        role="body",
    )
    body = IndentMode(center=6.0, tolerance=4.0, lines=[line], role="body")
    column = ColumnDesign(
        index=0,
        left=0,
        right=120,
        gutter_after=0,
        lines=[line],
        indent_modes=[body],
        body_mode=body,
        entry_modes=[],
    )
    region = PageRegion(
        name="body",
        source_box=(0, 0, 120, 100),
        canonical_box=(0, 0, 120, 100),
        origin="configured",
    )
    return DictionaryPageLayout(
        transform=transform,
        source_size=(120, 100),
        canonical_size=(120, 100),
        regions=PageRegions(body=region),
        body_top=0,
        body_bottom=100,
        columns=[column],
        ordinary_line_height=22.0,
        ordinary_line_pitch=28.0,
        ordinary_char_width=18.0,
        ordinary_char_height=22.0,
        indent_type="none",
        reliable=True,
        reason="synthetic",
    )


def _page_with_ring_marker() -> Image.Image:
    page = Image.new("RGB", (120, 100), "white")
    draw = ImageDraw.Draw(page)
    draw.ellipse((5, 39, 24, 58), outline="black", width=4)
    # Separate text block on the same visual line.  It is deliberately detached
    # so connected-component matching sees the sampled marker by itself.
    draw.rectangle((36, 42, 88, 56), fill="black")
    return page


def _settings_for_sample(role: str) -> AppSettings:
    sample = build_visual_marker_sample(
        _ring_image(),
        role=role,
        literal="○" if role == "entry_marker" else "【",
        sample_id=f"sample-{role}",
    )
    settings = AppSettings()
    settings.profile_symbol_inventory_enabled = True
    settings.profile_symbol_visual_rescue_enabled = True
    settings.profile_symbol_template_version = 1
    settings.profile_symbol_template_mode = "template_first"
    settings.profile_symbol_template_threshold = 0.55
    settings.profile_symbol_lane_required = False
    settings.profile_symbol_templates_json = serialize_visual_marker_samples([sample])
    return settings


def test_sampled_entry_marker_is_an_ocr_free_candidate() -> None:
    layout = _simple_layout()
    result = detect_symbol_evidence(
        _page_with_ring_marker(),
        _settings_for_sample("entry_marker"),
        layout,
    )
    assert len(result.entry_markers) == 1
    assert not result.bracket_openers
    candidates = result.entry_candidates()
    assert len(candidates) == 1
    assert candidates[0].ocr_source == "symbol_evidence:entry_marker"
    assert "SYMBOL_ENTRY_MARKER_RESCUE" in candidates[0].issue_type


def test_sampled_bracket_only_confirms_and_never_rescues_by_itself() -> None:
    layout = _simple_layout()
    result = detect_symbol_evidence(
        _page_with_ring_marker(),
        _settings_for_sample("bracket_open"),
        layout,
    )
    assert len(result.bracket_openers) == 1
    assert not result.entry_markers
    assert result.entry_candidates() == []

    understanding = SimpleNamespace(layout=layout, line_height=22.0)
    fused, stats = fuse_symbol_evidence([], result, understanding)
    assert fused == []
    assert stats["symbol_rescued"] == 0


def test_no_indent_neutralizes_directional_roles_and_legacy_cjk_topology() -> None:
    layout = _simple_layout()
    column = layout.columns[0]
    entry_line = LayoutLine(
        column=0,
        y0=68,
        y1=88,
        first_x=32,
        anchor_x=32,
        anchor_width=18,
        anchor_height=20,
        gap_before=10,
        patch=np.zeros((8, 8), dtype=bool),
        role="entry",
    )
    entry_mode = IndentMode(
        center=32.0,
        tolerance=4.0,
        lines=[entry_line],
        role="entry",
    )
    column.lines.append(entry_line)
    column.indent_modes.append(entry_mode)
    column.entry_modes = [entry_mode]
    layout.indent_type = "headword"

    settings = AppSettings()
    settings.dictionary_profile_id = "cjk_visual"
    settings.ocr_language = "chi_tra"
    apply_indent_type_label(settings, "无明显缩进")

    label = _apply_explicit_indent_semantics(layout, settings)
    assert label == "无明显缩进"
    assert layout.indent_type == "none"
    assert column.entry_modes == []
    assert entry_line.role == "other_indent"
    assert _uses_cjk_indent_topology(settings) is False


def test_profile_validation_summary_reports_no_indent_and_symbol_counts() -> None:
    layout = _simple_layout()
    evidence = detect_symbol_evidence(
        _page_with_ring_marker(),
        _settings_for_sample("entry_marker"),
        layout,
    )
    understanding = SimpleNamespace(
        layout=layout,
        physical_reliable=True,
        semantic_reliable=False,
        role_model="generic",
        semantic_entries=[],
        generic_body_indent_reliable=False,
        symbol_evidence=evidence,
    )
    text = _understanding_summary(understanding)
    assert "缩进版式：无明显缩进" in text
    assert "不使用缩进方向判定" in text
    assert "符号样本：入口 1 / 括号 0" in text


def test_symbol_result_container_separates_entry_and_bracket_roles() -> None:
    assert SymbolEvidenceResult(markers=[]).entry_candidates() == []
