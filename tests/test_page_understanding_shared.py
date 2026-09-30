from __future__ import annotations

import inspect

from PIL import Image, ImageDraw

from picture_capture import dictionary_page_design as base
from picture_capture.models import AppSettings, Entry
from picture_capture.page_understanding import (
    block_evidence_for_entry,
    understand_page,
)
from picture_capture.page_understanding_fusion import apply_page_understanding
from picture_capture.profile_indent_ui import apply_indent_type_label
import picture_capture.processing as processing


def _draw_line(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    *,
    width: int = 240,
    height: int = 11,
) -> None:
    draw.rectangle((x, y, x + width, y + height), fill="black")


def _settings(*, cjk: bool, body_indent: bool = False) -> AppSettings:
    settings = AppSettings(
        columns=1,
        layout_columns_policy="fixed",
        start_y=10,
        manual_x=20,
        column_width=310,
        gutter=20,
        character_height=20,
        ordinary_auto_layout=False,
        detection_method="left_edge",
        dictionary_profile_id="cjk_visual" if cjk else "latin_regular",
        ocr_language="chi_tra" if cjk else "eng",
        paddle_language="chinese_cht" if cjk else "en",
        profile_header_mode="none",
        profile_footer_mode="none",
        profile_side_content_mode="none",
        profile_cjk_allow_single_headword=True,
        profile_cjk_allow_bracketed_headword=True,
    )
    if body_indent:
        apply_indent_type_label(settings, "正文缩进")
    return settings


def _cjk_page() -> Image.Image:
    image = Image.new("RGB", (360, 520), "white")
    draw = ImageDraw.Draw(image)
    for y in (42, 98, 154, 210, 266, 322, 378, 434, 480):
        _draw_line(draw, 20, y, width=285)
    for index, y in enumerate((70, 182, 294, 406)):
        if index % 2:
            draw.rectangle((43, y, 51, y + 4), fill="black")
        _draw_line(draw, 65, y, width=205)
    return image


def _latin_body_indent_page() -> Image.Image:
    image = Image.new("RGB", (360, 520), "white")
    draw = ImageDraw.Draw(image)
    # Explicit body-indent design: entries sit on the outer lane x=20 while
    # continuation/body paragraphs sit on a stable inward lane x=70.
    for y in (50, 170, 290, 410):
        _draw_line(draw, 20, y, width=260)
    for y in (82, 114, 202, 234, 322, 354, 442, 474):
        _draw_line(draw, 70, y, width=210)
    return image


def test_cjk_ocr_observation_is_aligned_and_missing_layout_entries_are_rescued():
    image = _cjk_page()
    settings = _settings(cjk=True)
    understanding = understand_page(image, settings)

    assert understanding.physical_reliable
    assert understanding.semantic_reliable
    assert understanding.semantic_entries

    design = understanding.semantic_entries[0]
    ocr = Entry(
        word="詞",
        x=design.x + 3,
        y=design.y + 5,
        confidence=0.98,
        ocr_source="paddle",
        candidate_id="ocr-1",
    )
    fused = apply_page_understanding([ocr], understanding, mode="ocr")

    confirmed = [entry for entry in fused if entry.word == "詞"]
    assert len(confirmed) == 1
    assert confirmed[0].y == design.y
    assert "PAGE_UNDERSTANDING_CONFIRMED" in confirmed[0].issue_type
    assert len(fused) >= len(understanding.semantic_entries)
    assert any(
        entry.ocr_source.startswith("page_understanding:ocr_layout_rescue")
        for entry in fused
        if not entry.word
    )


def test_hard_negative_consensus_blocks_layout_only_rescue():
    image = _cjk_page()
    settings = _settings(cjk=True)
    understanding = understand_page(image, settings)
    blocked_entry = understanding.semantic_entries[0]
    located = processing._geometry_from_page_understanding(understanding)
    column = processing.column_index_for_click(
        blocked_entry.x, located, blocked_entry.y,
    )
    _u, v = located.source_to_canonical(blocked_entry.x, blocked_entry.y)

    fused = apply_page_understanding(
        [],
        understanding,
        mode="combined",
        hard_negative_rows=[(int(column), int(v))],
    )

    assert not any(
        abs(entry.y - blocked_entry.y) <= understanding.line_height * 0.28
        for entry in fused
    )
    assert understanding.arbitration_stats["hard_negative_blocked_rescue"] == 1


def test_generic_body_indent_is_negative_evidence_not_a_latin_entry_generator():
    image = _latin_body_indent_page()
    settings = _settings(cjk=False, body_indent=True)
    understanding = understand_page(image, settings)

    assert understanding.role_model == "generic"
    assert understanding.physical_reliable
    assert not understanding.semantic_entries
    assert understanding.generic_body_indent_reliable

    column = understanding.layout.columns[0]
    body_line = next(line for line in column.lines if line.role == "body")
    outer_line = next(line for line in column.lines if line.role == "other_indent")
    reference = understanding.line_height

    body_y = base._boundary_before(column.lines, body_line.y0, reference)
    outer_y = base._boundary_before(column.lines, outer_line.y0, reference)
    body_candidate = Entry(word="", x=column.left, y=understanding.layout.body_top + body_y)
    outer_candidate = Entry(word="", x=column.left, y=understanding.layout.body_top + outer_y)

    body_evidence = block_evidence_for_entry(understanding, body_candidate)
    assert body_evidence is not None and body_evidence.on_body_lane

    filtered = apply_page_understanding(
        [body_candidate, outer_candidate], understanding, mode="ordinary"
    )
    assert outer_candidate in filtered
    assert body_candidate not in filtered
    assert understanding.arbitration_stats["generic_body_suppressed"] == 1


def test_accepted_ocr_semantic_positive_survives_body_lane_conflict_for_review():
    image = _latin_body_indent_page()
    settings = _settings(cjk=False, body_indent=True)
    understanding = understand_page(image, settings)
    column = understanding.layout.columns[0]
    body_line = next(line for line in column.lines if line.role == "body")
    body_y = base._boundary_before(
        column.lines, body_line.y0, understanding.line_height,
    )
    ocr = Entry(
        word="recognized-head",
        x=column.left,
        y=understanding.layout.body_top + body_y,
        confidence=0.97,
        ocr_source="paddle",
        candidate_id="accepted-1",
        final_engine="paddle",
    )

    filtered = apply_page_understanding([ocr], understanding, mode="ocr")

    assert len(filtered) == 1
    assert filtered[0].word == "recognized-head"
    assert "PAGE_UNDERSTANDING_LAYOUT_CONFLICT" in filtered[0].issue_type
    assert understanding.arbitration_stats["layout_conflicts"] == 1
    assert understanding.arbitration_stats["generic_body_suppressed"] == 0


def test_processing_builds_shared_understanding_before_all_detector_modes():
    source = inspect.getsource(processing.detect_entries)
    assert "understand_page(" in source
    assert "_core.detect_entries(" in source  # complete fallback remains available
    assert "_shared_detector_observations(" in source
    assert "apply_page_understanding(" in source
    assert source.index("understand_page(") < source.index("_core.detect_entries(")
    assert '"ocr" if method == "paddleocr"' in source
    assert '"combined" if method == "combined"' in source
    assert "_hard_negative_rows_from_candidates" in source


def test_reliable_page_uses_one_geometry_for_ocr_and_combined_generation():
    source = inspect.getsource(processing._shared_detector_observations)
    assert "_geometry_from_page_understanding(understanding)" in source
    assert "detect_paddle_headwords(" in source
    assert "_fuse_detection_entries(" in source
    assert "derive_geometry(" not in source


def test_combined_vb_observation_does_not_duplicate_cjk_layout_reasoning():
    source = inspect.getsource(processing._detect_entries_left_edge)
    assert 'if method not in {"combined", "paddleocr"}' in source
    assert "finalize_indented_topology(" in source
    assert "recover_cjk_oversized_heads(" in source
