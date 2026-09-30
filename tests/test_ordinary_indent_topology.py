from __future__ import annotations

from PIL import Image, ImageDraw

from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_cjk_large_heads import recover_cjk_oversized_heads
from picture_capture.ordinary_indent_topology import (
    _observe_column,
    _observe_column_raw,
    finalize_indented_topology,
)
from picture_capture.processing import derive_nominal_geometry


def _settings() -> AppSettings:
    return AppSettings(
        columns=1,
        manual_x=0,
        column_width=320,
        gutter=0,
        start_y=10,
        bottom_y=450,
        crop_to_bottom_y=True,
        character_height=20,
        row_padding=0,
        follow_column_deformation=False,
        dictionary_profile_id="cjk_visual",
        ocr_language="chi_tra",
        paddle_language="chinese_cht",
        profile_cjk_allow_bracketed_headword=True,
        profile_cjk_allow_single_headword=True,
    )


def _block_page() -> tuple[Image.Image, list[int], list[int], list[int]]:
    """Body at x=6; bracket structure at x=44; optional small prefixes vary."""
    image = Image.new("RGB", (340, 460), "white")
    draw = ImageDraw.Draw(image)
    body_rows = [40, 88, 136, 184, 232, 280, 328, 424]
    plain_entries = [64, 208, 352]
    numbered_entries = [112, 256, 400]

    for y in body_rows:
        draw.rectangle((6, y, 260, y + 9), fill="black")

    for y in plain_entries:
        draw.rectangle((44, y, 49, y + 9), fill="black")
        draw.rectangle((56, y, 190, y + 8), fill="black")

    for index, y in enumerate(numbered_entries):
        # Small prefix moves FIRST ink, but the full-height bracket anchor stays.
        prefix_x = 19 + index * 4
        draw.rectangle((prefix_x, y, prefix_x + 8, y + 3), fill="black")
        draw.rectangle((44, y, 49, y + 9), fill="black")
        draw.rectangle((56, y, 190, y + 8), fill="black")

    return image, body_rows, plain_entries, numbered_entries


def _body_indented_page() -> tuple[Image.Image, list[int], list[int]]:
    """Mirror semantic relation: body at x=46, headword bracket at x=8."""
    image = Image.new("RGB", (340, 420), "white")
    draw = ImageDraw.Draw(image)
    body_rows = [40, 88, 136, 184, 232, 280, 328, 376]
    entry_rows = [64, 160, 256, 352]
    for y in body_rows:
        draw.rectangle((46, y, 260, y + 9), fill="black")
    for y in entry_rows:
        draw.rectangle((8, y, 13, y + 9), fill="black")
        draw.rectangle((20, y, 180, y + 8), fill="black")
    return image, body_rows, entry_rows


def test_structural_anchor_ignores_optional_number_prefix():
    image, _body_rows, plain_entries, numbered_entries = _block_page()
    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)

    topology = _observe_column(image, geometry, settings, 0)

    assert topology is not None
    assert topology.is_proven
    assert topology.body_is_proven
    assert abs(topology.body_center - 6) <= 3
    assert len(topology.entry_centers) == 1
    assert abs(topology.entry_centers[0] - 44) <= 3
    assert len(topology.entry_rows) == len(plain_entries) + len(numbered_entries)
    starts = [row.first_start for row in topology.entry_rows]
    structural = [row.start for row in topology.entry_rows]
    assert min(starts) < 30
    assert max(structural) - min(structural) <= 3


def test_headword_indent_final_gate_rejects_body_and_recovers_all_bracket_blocks():
    image, body_rows, plain_entries, numbered_entries = _block_page()
    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    x = int(geometry.column_starts[0])

    entries = [
        Entry(word="", x=x, y=body_rows[1] - 2, ocr_source="ordinary_vb"),
        Entry(word="", x=x, y=body_rows[4] - 2, ocr_source="ordinary_visual_lane"),
        Entry(word="", x=x, y=plain_entries[0] - 2, ocr_source="ordinary_vb"),
    ]

    result = finalize_indented_topology(image, entries, geometry, settings)

    assert not any(entry.y in {body_rows[1] - 2, body_rows[4] - 2} for entry in result)
    recovered = [
        entry for entry in result
        if entry.issue_type == "ORDINARY_BLOCK_BRACKET_ENTRY"
    ]
    assert len(recovered) >= len(plain_entries) + len(numbered_entries) - 1


def test_body_indent_option_reverses_semantic_lane_direction():
    image, _body_rows, entry_rows = _body_indented_page()
    settings = _settings()
    # Version 2 marks this as an explicit user choice, not the unrelated legacy
    # meaning of profile_cjk_brackets_in_body.
    settings.profile_parser_controls_version = 2
    settings.profile_cjk_brackets_in_body = True
    settings.bottom_y = 410
    geometry = derive_nominal_geometry(image.width, image.height, settings)

    topology = _observe_column(image, geometry, settings, 0)

    assert topology is not None
    assert topology.is_proven
    assert topology.indent_type == "body"
    assert abs(topology.body_center - 46) <= 3
    assert len(topology.entry_centers) == 1
    assert abs(topology.entry_centers[0] - 8) <= 3

    result = finalize_indented_topology(image, [], geometry, settings)
    recovered = [
        entry for entry in result
        if entry.issue_type == "ORDINARY_BLOCK_BRACKET_ENTRY"
    ]
    assert len(recovered) >= len(entry_rows) - 1


def test_oversized_head_is_recovered_by_independent_block_signature():
    image, _body_rows, _plain_entries, _numbered_entries = _block_page()
    draw = ImageDraw.Draw(image)
    draw.rectangle((34, 8, 47, 38), fill="black")
    draw.rectangle((52, 8, 72, 38), fill="black")

    settings = _settings()
    settings.start_y = 0
    geometry = derive_nominal_geometry(image.width, image.height, settings)

    result = recover_cjk_oversized_heads(image, [], geometry, settings)

    heads = [
        entry for entry in result
        if entry.issue_type == "ORDINARY_BLOCK_OVERSIZED_HEAD"
    ]
    assert heads
    assert all(entry.ocr_oversized_cjk for entry in heads)


def test_same_body_geometry_from_multiple_sources_cannot_bypass_final_gate():
    image, body_rows, _plain_entries, _numbered_entries = _block_page()
    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    x = int(geometry.column_starts[0])
    entries = [
        Entry(word="", x=x, y=body_rows[1] - 2, ocr_source="ordinary_vb"),
        Entry(word="", x=x, y=body_rows[3] - 2, ocr_source="ordinary_visual_lane"),
        Entry(word="", x=x, y=body_rows[5] - 2, ocr_source="ordinary_secondary"),
    ]

    result = finalize_indented_topology(image, entries, geometry, settings)

    false_y = {entry.y for entry in entries}
    assert not any(entry.y in false_y for entry in result)


def test_right_side_illustration_cannot_merge_left_body_lines_or_bypass_gate():
    image, body_rows, _plain_entries, _numbered_entries = _block_page()
    draw = ImageDraw.Draw(image)
    draw.rectangle((230, 80, 315, 335), fill="black")

    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    topology = _observe_column(image, geometry, settings, 0)

    assert topology is not None
    visible_body_y = {int(row.y0) + int(topology.top) for row in topology.body_rows}
    assert any(abs(y - 88) <= 2 for y in visible_body_y)
    assert any(abs(y - 184) <= 2 for y in visible_body_y)
    assert any(abs(y - 280) <= 2 for y in visible_body_y)

    x = int(geometry.column_starts[0])
    false_entries = [
        Entry(word="", x=x, y=86, ocr_source="ordinary_vb"),
        Entry(word="", x=x, y=182, ocr_source="ordinary_vb"),
        Entry(word="", x=x, y=278, ocr_source="ordinary_vb"),
    ]
    result = finalize_indented_topology(image, false_entries, geometry, settings)
    assert not any(entry.y in {86, 182, 278} for entry in result)


def test_body_only_continuation_column_suppresses_legacy_body_candidates():
    """Regression for a column containing only continuation definition text.

    Absence of an entry lane is not uncertainty once a stable ordinary body lane
    is proven. Legacy candidates on that lane are explicit false positives.
    """
    image = Image.new("RGB", (340, 300), "white")
    draw = ImageDraw.Draw(image)
    rows = [32, 64, 96, 128, 160, 192, 224, 256]
    for index, y in enumerate(rows):
        # Vary the leading glyph patch so this is ordinary prose, not a repeated
        # structural marker lane. Every row nevertheless shares one body X lane.
        draw.rectangle((6, y, 11 + (index % 3), y + 9), fill="black")
        draw.rectangle((18 + (index % 4), y, 260, y + 8), fill="black")

    settings = _settings()
    settings.bottom_y = 290
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    topology = _observe_column_raw(image, geometry, settings, 0)

    assert topology is not None
    assert topology.body_is_proven
    assert not topology.is_proven
    assert not topology.entry_lanes

    x = int(geometry.column_starts[0])
    entries = [
        Entry(word="", x=x, y=y - 2, confidence=.9, ocr_source="ordinary_vb")
        for y in rows[1:7]
    ]
    # A manual marker must never be removed by automatic topology filtering.
    manual = Entry(
        word="manual", x=x, y=rows[-1] - 2,
        confidence=1.0, ocr_source="ordinary_vb", manually_selected=True,
    )
    result = finalize_indented_topology(
        image, entries + [manual], geometry, settings,
    )

    assert not [entry for entry in result if not entry.manually_selected]
    assert manual in result


def test_repeated_headword_only_lane_is_not_declared_body():
    """A list of repeated bracket starts must not become body by majority vote."""
    image = Image.new("RGB", (340, 300), "white")
    draw = ImageDraw.Draw(image)
    rows = [32, 72, 112, 152, 192, 232]
    for y in rows:
        draw.rectangle((44, y, 49, y + 9), fill="black")
        draw.rectangle((56, y, 180, y + 8), fill="black")

    settings = _settings()
    settings.bottom_y = 290
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    topology = _observe_column_raw(image, geometry, settings, 0)

    # Without a separate ordinary prose lane the model should remain uncertain,
    # not relabel the repeated structural lane as body and delete it.
    assert topology is None

    x = int(geometry.column_starts[0])
    legacy = [
        Entry(word="", x=x, y=rows[1] - 2, ocr_source="ordinary_vb")
    ]
    result = finalize_indented_topology(image, legacy, geometry, settings)
    assert result == legacy
