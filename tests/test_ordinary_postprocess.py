from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_postprocess import (
    _separator_near_next_line,
    stabilize_ordinary_visual_entries,
)
from picture_capture.processing import derive_nominal_geometry


def _settings() -> AppSettings:
    return AppSettings(
        columns=1,
        manual_x=0,
        column_width=300,
        gutter=0,
        start_y=10,
        bottom_y=290,
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


def test_separator_is_anchored_to_upcoming_line_not_previous_line_bottom():
    ink = np.zeros((90, 180), dtype=bool)
    ink[10:20, 0:120] = True
    ink[42:54, 40:150] = True

    separator = _separator_near_next_line(ink, 42, 20.0)

    assert separator is not None
    assert 39 <= separator <= 41
    assert separator > 20


def test_projection_recovers_large_disconnected_cjk_head():
    image = Image.new("RGB", (320, 300), "white")
    draw = ImageDraw.Draw(image)
    # A large display ideograph represented by two disconnected radicals.
    draw.rectangle((24, 42, 38, 92), fill="black")
    draw.rectangle((45, 42, 78, 92), fill="black")
    # Normal body rows establish the ordinary line-height reference.
    for y in range(125, 265, 24):
        draw.rectangle((4, y, 220, y + 11), fill="black")

    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    result = stabilize_ordinary_visual_entries(
        image, [], geometry, settings,
    )

    heads = [entry for entry in result if entry.ocr_source == "ordinary_visual_head"]
    assert heads
    assert any("ORDINARY_OVERSIZED_HEAD_PROJECTION" in entry.issue_type for entry in heads)
    assert min(entry.y for entry in heads) < 42


def test_page_proven_visual_lane_removes_sparse_residual_vb_body_rows():
    image = Image.new("RGB", (320, 300), "white")
    draw = ImageDraw.Draw(image)
    body_rows = [40, 72, 104, 136, 168, 200, 232]
    for y in body_rows:
        draw.rectangle((4, y, 220, y + 11), fill="black")
    # Three indented structural rows prove the page-level entry lane.
    for y in (72, 136, 200):
        draw.rectangle((46, y, 54, y + 11), fill="black")
        draw.rectangle((62, y, 160, y + 9), fill="black")

    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    x = int(geometry.column_starts[0])
    entries = [
        Entry(word="", x=x, y=60, confidence=0.96, ocr_source="ordinary_visual_lane"),
        Entry(word="", x=x, y=124, confidence=0.96, ocr_source="ordinary_visual_lane"),
        Entry(word="", x=x, y=188, confidence=0.96, ocr_source="ordinary_visual_lane"),
        # Only two residual VB false positives: this deliberately fails the old
        # >=7 legacy / >=5 body-support gate but should still be removed now.
        Entry(word="", x=x, y=28, confidence=0.98, ocr_source="ordinary_vb"),
        Entry(word="", x=x, y=92, confidence=0.98, ocr_source="ordinary_vb"),
    ]

    result = stabilize_ordinary_visual_entries(
        image, entries, geometry, settings,
    )

    assert not [entry for entry in result if entry.ocr_source == "ordinary_vb"]
    lanes = [entry for entry in result if entry.ocr_source == "ordinary_visual_lane"]
    assert len(lanes) == 3
    # Re-anchored separators sit immediately above their upcoming rows.
    assert all(any(abs(entry.y - (row - 1)) <= 2 for row in (72, 136, 200)) for entry in lanes)
