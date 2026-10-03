from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.layout_transform import LayoutTransform
from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_evidence_fusion import promote_evidence_to_layout_roles
from picture_capture.ordinary_large_head_evidence import detect_ordinary_large_head_entries
from picture_capture.ordinary_symbol_evidence import detect_ordinary_symbol_entries
from picture_capture.visual_marker_templates import (
    build_visual_marker_sample,
    match_visual_marker_template,
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
        # Deliberately OFF: OCR rescue must not gate ordinary sampled evidence.
        profile_symbol_visual_rescue_enabled=False,
        profile_symbol_template_mode="template_first",
        profile_symbol_template_threshold=0.50,
        profile_symbol_templates_json=serialize_visual_marker_samples([sample]),
        # Also parameterized to prove an explicitly sampled bracket role remains
        # authoritative even if an older parser Boolean is off.
        profile_cjk_allow_bracketed_headword=bracket_enabled,
    )
    return image, settings


def test_visual_symbol_sample_promotes_no_indent_body_row_with_ocr_rescue_off():
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


def test_explicit_bracket_sample_is_authoritative_even_if_old_bracket_flag_is_off():
    image, settings = _bracket_sample_settings(bracket_enabled=False)
    understanding, _lines = _understanding_with_rows()
    evidence = detect_ordinary_symbol_entries(image, understanding, settings)
    assert evidence
    assert evidence[0].issue_type == "ORDINARY_VISUAL_BRACKET_SAMPLE"


def test_closed_box_cannot_match_bracket_open_sample():
    sample_image = Image.new("RGB", (12, 24), "white")
    draw = ImageDraw.Draw(sample_image)
    draw.line((1, 1, 1, 22), fill="black", width=2)
    draw.line((1, 1, 8, 1), fill="black", width=2)
    draw.line((1, 22, 8, 22), fill="black", width=2)
    sample = build_visual_marker_sample(
        sample_image,
        role="bracket_open",
        literal="【",
        sample_id="bracket",
    )

    boxed = np.zeros((24, 12), dtype=bool)
    boxed[1:23, 1:3] = True
    boxed[1:23, 9:11] = True
    boxed[1:3, 1:11] = True
    boxed[21:23, 1:11] = True
    assert match_visual_marker_template(
        boxed,
        [sample],
        roles={"bracket_open"},
    ) is None


def test_broken_boxed_number_does_not_match_real_bracket_sample():
    _sample_image, settings = _bracket_sample_settings()
    image = Image.new("RGB", (100, 80), "white")
    draw = ImageDraw.Draw(image)

    # Deliberately break the right border so this shape has no enclosed hole.
    # It remains a box-like numbered marker, not the sampled 【 glyph.
    draw.line((10, 10, 10, 29), fill="black", width=2)
    draw.line((10, 10, 18, 10), fill="black", width=2)
    draw.line((10, 29, 18, 29), fill="black", width=2)
    draw.line((18, 10, 18, 16), fill="black", width=2)
    draw.line((18, 23, 18, 29), fill="black", width=2)

    understanding, lines = _understanding_with_rows()
    evidence = detect_ordinary_symbol_entries(image, understanding, settings)
    assert evidence == []
    assert lines[0].role == "body"


def test_visual_evidence_never_demotes_existing_indent_entry():
    understanding, lines = _understanding_with_rows(roles=("entry", "body"))
    # Re-observing evidence on a row that is already an indent entry is a no-op:
    # promotion counts only body->entry transitions, and the neighboring body
    # row must remain untouched.
    promoted = promote_evidence_to_layout_roles(
        understanding,
        [Entry(word="", x=10, y=15, ocr_source="ordinary_large_head_evidence")],
    )
    assert promoted == 0
    assert lines[0].role == "entry"
    assert lines[1].role == "body"


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
    # A docstring may name the historical module while explaining independence;
    # the dependency contract is that the detector does not import it.
    assert "from .ordinary_cjk_large_heads" not in source
    assert "import ordinary_cjk_large_heads" not in source
    assert "def _candidate_boxes" in source


def test_profile_ui_explains_visual_samples_are_ordinary_evidence():
    from picture_capture import profile_ordinary_evidence_ui as ui

    source = open(ui.__file__, "r", encoding="utf-8").read()
    assert "普通画线：视觉词头证据（OCR-independent）" in source
    assert "启用大字头 detector（CJK）" in source
    assert "有有效样本即参与普通画线" in source
    assert "OCR 漏掉/错认符号时允许视觉形状补救" in source
    assert "完全独立" in source
    assert "从页面采样…" in source
    assert "多个样本按最佳匹配（max/OR）使用" in source
    assert 'child.cget("text") == "本词典视觉标记样本"' in source
    assert 'child.cget("text") == "大字单字可以作为词头"' in source


def test_launcher_installs_universal_ordinary_profile_ui():
    import picture_capture.launcher as launcher

    source = open(launcher.__file__, "r", encoding="utf-8").read()
    assert "build_ordinary_evidence_profile_wizard" in source
    assert "build_project_profile_wizard(profile_setup.ProjectProfileWizard)" in source
