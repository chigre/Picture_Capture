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
        bottom_y=350,
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


def _two_lane_page() -> tuple[Image.Image, list[int], list[int]]:
    image = Image.new("RGB", (340, 360), "white")
    draw = ImageDraw.Draw(image)
    body_rows = [40, 72, 104, 136, 168, 200, 232, 264, 296, 328]
    entry_rows = [56, 152, 248, 312]

    # Dominant definition/prose lane: flush-left relative to the local column.
    for y in body_rows:
        draw.rectangle((6, y, 260, y + 9), fill="black")

    # Repeated bracketed-entry lane: distinctly indented and visually stable.
    for y in entry_rows:
        draw.rectangle((32, y, 44, y + 9), fill="black")
        draw.rectangle((49, y, 190, y + 8), fill="black")
    return image, body_rows, entry_rows


def test_topology_learns_body_and_indented_entry_lanes_separately():
    image, _body_rows, _entry_rows = _two_lane_page()
    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)

    topology = _observe_column(image, geometry, settings, 0)

    assert topology is not None
    assert topology.is_proven
    assert abs(topology.body_center - 6) <= 3
    assert abs(topology.entry_center - 32) <= 4
    assert topology.entry_center > topology.body_center
    assert len(topology.body_rows) >= 6
    assert len(topology.entry_rows) >= 3


def test_final_gate_removes_body_lane_candidates_from_any_ordinary_source():
    image, body_rows, entry_rows = _two_lane_page()
    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    x = int(geometry.column_starts[0])

    entries = [
        # Same false geometry, deliberately emitted by three different upstream
        # ordinary sources. Final classification must depend on the next line's
        # lane, not on which detector happened to create the candidate.
        Entry(word="", x=x, y=body_rows[0] - 2, confidence=.8, ocr_source="ordinary_vb"),
        Entry(word="", x=x, y=body_rows[3] - 2, confidence=.9, ocr_source="ordinary_visual_lane"),
        Entry(word="", x=x, y=body_rows[6] - 2, confidence=.9, ocr_source="ordinary_secondary"),
        # A true indented entry must survive.
        Entry(word="", x=x, y=entry_rows[0] - 2, confidence=.9, ocr_source="ordinary_vb"),
        # Display heads are a separate class and must survive even if their Y is
        # close to a body-lane row.
        Entry(
            word="", x=x, y=body_rows[8] - 2, confidence=.97,
            ocr_source="ordinary_visual_head",
            issue_type="ORDINARY_OVERSIZED_HEAD_PROJECTION",
            ocr_oversized_cjk=True,
        ),
    ]

    result = finalize_indented_topology(image, entries, geometry, settings)

    body_y = {body_rows[0] - 2, body_rows[3] - 2, body_rows[6] - 2}
    assert not any(int(entry.y) in body_y for entry in result)
    assert any(
        entry.ocr_source == "ordinary_visual_head"
        for entry in result
    )
    # The proven entry lane is recovered comprehensively, not only where an
    # upstream detector happened to fire.
    topology_entries = [
        entry for entry in result
        if entry.issue_type == "ORDINARY_INDENT_TOPOLOGY_ENTRY"
    ]
    assert len(topology_entries) >= 3


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
