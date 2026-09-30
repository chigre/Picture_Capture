from __future__ import annotations

from PIL import Image, ImageDraw

from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_indent_topology import (
    _observe_column,
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
        bottom_y=430,
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


def _multi_lane_page() -> tuple[Image.Image, list[int], list[int], list[int]]:
    image = Image.new("RGB", (340, 440), "white")
    draw = ImageDraw.Draw(image)
    body_rows = [40, 72, 104, 136, 168, 200, 232, 264, 296, 328, 360, 408]
    entry_a = [56, 152, 248, 344, 392]
    entry_b = [120, 216, 312]

    # Dominant definition/prose lane.
    for y in body_rows:
        draw.rectangle((6, y, 260, y + 9), fill="black")

    # Two genuine entry sub-lanes.  They deliberately differ by less than one
    # character width, matching the real training page where bracketed and
    # numbered/variant forms formed separate stable first-ink modes.
    for y in entry_a:
        draw.rectangle((32, y, 44, y + 9), fill="black")
        draw.rectangle((49, y, 190, y + 8), fill="black")
    for y in entry_b:
        draw.rectangle((43, y, 55, y + 9), fill="black")
        draw.rectangle((60, y, 195, y + 8), fill="black")
    return image, body_rows, entry_a, entry_b


def test_topology_learns_body_and_multiple_entry_sublanes():
    image, _body_rows, _entry_a, _entry_b = _multi_lane_page()
    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)

    topology = _observe_column(image, geometry, settings, 0)

    assert topology is not None
    assert topology.is_proven
    assert abs(topology.body_center - 6) <= 3
    centers = list(topology.entry_centers)
    assert len(centers) >= 2
    assert any(abs(center - 32) <= 4 for center in centers)
    assert any(abs(center - 43) <= 4 for center in centers)
    assert len(topology.body_rows) >= 6
    assert len(topology.entry_rows) >= 8


def test_final_gate_keeps_all_proven_sublanes_and_rejects_body_or_other_rows():
    image, body_rows, entry_a, entry_b = _multi_lane_page()
    draw = ImageDraw.Draw(image)
    # One isolated paragraph-like indent between body and entry lanes.  It has
    # whitespace above but does not repeat enough to define a structural lane.
    draw.rectangle((20, 376, 230, 385), fill="black")

    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    x = int(geometry.column_starts[0])

    entries = [
        Entry(word="", x=x, y=body_rows[0] - 2, confidence=.8, ocr_source="ordinary_vb"),
        Entry(word="", x=x, y=body_rows[4] - 2, confidence=.9, ocr_source="ordinary_visual_lane"),
        # Isolated non-lane indentation must also be rejected now that topology
        # is proven; the old implementation preserved role="other".
        Entry(word="", x=x, y=374, confidence=.9, ocr_source="ordinary_vb"),
        Entry(word="", x=x, y=entry_a[0] - 2, confidence=.9, ocr_source="ordinary_vb"),
        Entry(word="", x=x, y=entry_b[0] - 2, confidence=.9, ocr_source="ordinary_vb"),
        Entry(
            word="", x=x, y=body_rows[8] - 2, confidence=.97,
            ocr_source="ordinary_visual_head",
            issue_type="ORDINARY_OVERSIZED_HEAD_PROJECTION",
            ocr_oversized_cjk=True,
        ),
    ]

    result = finalize_indented_topology(image, entries, geometry, settings)

    rejected_y = {body_rows[0] - 2, body_rows[4] - 2, 374}
    assert not any(int(entry.y) in rejected_y for entry in result)
    assert any(entry.ocr_source == "ordinary_visual_head" for entry in result)

    # Recovery should cover both proven sub-lanes, not only one chosen centre.
    topology_entries = [
        entry for entry in result
        if entry.issue_type == "ORDINARY_INDENT_TOPOLOGY_ENTRY"
    ]
    assert len(topology_entries) >= 6


def test_same_geometry_from_multiple_upstream_sources_cannot_bypass_final_gate():
    image, body_rows, _entry_a, _entry_b = _multi_lane_page()
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


def test_single_lane_page_does_not_trigger_topology_suppression():
    image = Image.new("RGB", (340, 260), "white")
    draw = ImageDraw.Draw(image)
    rows = [40, 72, 104, 136, 168, 200]
    for y in rows:
        draw.rectangle((6, y, 260, y + 9), fill="black")

    settings = _settings()
    settings.bottom_y = 250
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    x = int(geometry.column_starts[0])
    entries = [
        Entry(word="", x=x, y=rows[1] - 2, confidence=.8, ocr_source="ordinary_vb"),
        Entry(word="", x=x, y=rows[4] - 2, confidence=.8, ocr_source="ordinary_vb"),
    ]

    result = finalize_indented_topology(image, entries, geometry, settings)

    assert [(entry.x, entry.y, entry.ocr_source) for entry in result] == [
        (entry.x, entry.y, entry.ocr_source) for entry in entries
    ]
