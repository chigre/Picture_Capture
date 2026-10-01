from __future__ import annotations

from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.layout_transform import LayoutTransform
from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_evidence_fusion import promote_evidence_to_layout_roles
from picture_capture.ordinary_large_head_evidence import detect_ordinary_large_head_entries
from picture_capture.ordinary_symbol_evidence import detect_ordinary_symbol_entries
from picture_capture.visual_marker_templates import (
    build_visual_marker_sample,
    serialize_visual_marker_samples,
)


def _understanding_with_rows(*, roles=("body", "body")):
    lines = [
        SimpleNamespace(y0=10, y1=30, first_x=0.0, role=roles[0]),
        SimpleNamespace(y0=40, y1=60, first_x=0.0, role=roles[1]),
    ]
    column = SimpleNamespace(left=10, right=90, lines=lines)
    layout = SimpleNamespace(
        body_top=0,
        body_bottom=80,
        ordinary_line_height=20.0,
        columns=[column],
        transform=LayoutTransform("identity"),
        source_size=(100, 80),
    )
    return SimpleNamespace(layout=layout), lines


def _bracket_sample_settings(*, bracket_enabled: bool = True) -> tuple[Image.Image, AppSettings]:
    image = Image.new("RGB", (100, 80), "white")
    draw = ImageDraw.Draw(image)
    draw.line((10, 10, 10, 29), fill="black", width=2)
    draw.line((10, 10, 17, 10), fill="black", width=2)
    draw.line((10, 29, 17, 29), fill="black", width=2)
    sample = build_visual_marker_sample(
        image.crop((10, 10, 18, 30)),
        role="bracket_open",
        literal="【",
        sample_id="sample-1",
    )
    settings = AppSettings(
        profile_symbol_visual_rescue_enabled=True,
        profile_symbol_template_mode="template_first",
        profile_symbol_template_threshold=0.50,
        profile_symbol_templates_json=serialize_visual_marker_samples([sample]),
        profile_cjk_allow_bracketed_headword=bracket_enabled,
    )
    return image, settings


def test_visual_symbol_sample_promotes_no_indent_body_row():
    image, settings = _bracket_sample_settings()
    understanding, lines = _understanding_with_rows()

    evidence = detect_ordinary_symbol_entries(image, understanding, settings)
    assert evidence
    assert evidence[0].issue_type == "ORDINARY_VISUAL_BRACKET_SAMPLE"
    assert lines[0].role == "body"

    promoted = promote_evidence_to_layout_roles(understanding, evidence)
    assert promoted == 1
    assert lines[0].role == "entry"
    assert lines[1].role == "body"


def test_disabled_bracket_structure_disables_bracket_visual_sample():
    image, settings = _bracket_sample_settings(bracket_enabled=False)
    understanding, _lines = _understanding_with_rows()
    assert detect_ordinary_symbol_entries(image, understanding, settings) == []


def test_visual_evidence_never_demotes_existing_indent_entry():
    understanding, lines = _understanding_with_rows(roles=("entry", "body"))
    promoted = promote_evidence_to_layout_roles(
        understanding,
        [Entry(word="", x=10, y=45, ocr_source="ordinary_large_head_evidence")],
    )
    assert promoted == 1
    assert lines[0].role == "entry"
    assert lines[1].role == "entry"


def test_large_head_detector_is_cjk_gated_and_independent_from_legacy_module():
    image = Image.new("RGB", (100, 80), "white")
    understanding, _lines = _understanding_with_rows()
    latin = AppSettings(
        dictionary_profile_id="latin_structured_symbols",
        profile_cjk_allow_single_headword=True,
    )
    assert detect_ordinary_large_head_entries(image, understanding, latin) == []

    import picture_capture.ordinary_large_head_evidence as module

    source = open(module.__file__, "r", encoding="utf-8").read()
    assert "ordinary_cjk_large_heads" not in source
    assert "def _candidate_boxes" in source


def test_profile_ui_places_visual_evidence_with_headword_structure():
    from picture_capture import profile_ordinary_evidence_ui as ui

    source = open(ui.__file__, "r", encoding="utf-8").read()
    assert "普通画线：视觉词头证据（OCR-independent）" in source
    assert "启用大字头 detector（CJK）" in source
    assert "启用特定符号视觉样本" in source
    assert "从页面采样…" in source
    assert "多个样本按最佳匹配（max/OR）使用" in source
    assert 'child.cget("text") == "本词典视觉标记样本"' in source
    assert 'child.cget("text") == "大字单字可以作为词头"' in source


def test_launcher_installs_universal_ordinary_profile_ui():
    import picture_capture.launcher as launcher

    source = open(launcher.__file__, "r", encoding="utf-8").read()
    assert "build_ordinary_evidence_profile_wizard" in source
    assert "build_project_profile_wizard(profile_setup.ProjectProfileWizard)" in source
