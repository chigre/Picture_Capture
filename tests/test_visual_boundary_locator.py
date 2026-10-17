"""Safe pixel gap localization and bracketed headword direction regressions."""
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.layout_transform import LayoutTransform
from picture_capture.ordinary_bracket_pair import recover_bracketed_ordinary_entries
from picture_capture.geometry.visual_boundary_locator import safe_gap_above


def _pair(image: Image.Image, x: int, y: int, distance: int = 130):
    draw = ImageDraw.Draw(image)
    # Opening and closing 【 】 with narrow rectangular stems and triangular tips.
    for closing, left in ((False, x), (True, x + distance)):
        if closing:
            draw.rectangle((left + 15, y, left + 20, y + 52), fill=0)
            draw.polygon([(left, y), (left + 20, y), (left + 20, y + 8)], fill=0)
            draw.polygon([(left, y + 52), (left + 20, y + 52),
                          (left + 20, y + 44)], fill=0)
        else:
            draw.rectangle((left, y, left + 5, y + 52), fill=0)
            draw.polygon([(left, y), (left + 20, y), (left, y + 8)], fill=0)
            draw.polygon([(left, y + 52), (left + 20, y + 52),
                          (left, y + 44)], fill=0)


def test_gap_locator_avoids_both_previous_and_following_ink():
    gray = np.full((250, 300), 255, dtype=np.uint8)
    gray[90:125, :] = 10
    gray[160:204, 80:230] = 10
    boundary = safe_gap_above(gray, 160, 48)
    assert 125 < boundary < 160
    assert np.all(gray[boundary - 1:boundary + 2] == 255)


def test_missing_gap_remains_bounded_and_never_jumps_a_line():
    gray = np.zeros((220, 120), dtype=np.uint8)
    boundary = safe_gap_above(gray, 150, 40)
    assert 150 - 22 <= boundary <= 148


def test_cjk_bracket_detection_maps_coordinates_back_from_rotated_canonical():
    canonical = Image.new("L", (400, 330), 255)
    _pair(canonical, 50, 130)
    transform = LayoutTransform("rotate_ccw90")
    source_size = (330, 400)
    entries = recover_bracketed_ordinary_entries(
        [], canonical, [SimpleNamespace(left=20, right=360)],
        15, 300, 40, transform=transform, source_size=source_size,
    )
    assert len(entries) == 1
    u, v = transform.source_to_canonical_point(
        entries[0].x, entries[0].y, source_size,
    )
    assert u == 20
    assert 110 <= v <= 130


def test_bracket_boundary_is_stable_when_existing_entry_is_source_space():
    canonical = Image.new("L", (400, 330), 255)
    _pair(canonical, 50, 130)
    transform = LayoutTransform("mirror_x")
    source_size = canonical.size
    x, y = transform.canonical_to_source_point(20, 125, source_size)
    from picture_capture.models import Entry

    entries = recover_bracketed_ordinary_entries(
        [Entry("existing", x, y)], canonical,
        [SimpleNamespace(left=20, right=360)],
        15, 300, 40, transform=transform, source_size=source_size,
    )
    assert len(entries) == 1


def test_cjk_bracket_scan_keeps_script_identity_in_vertical_writing():
    from picture_capture.models import AppSettings
    from picture_capture.page_understanding import (
        uses_cjk_role_model, uses_cjk_script,
    )

    settings = AppSettings(
        dictionary_profile_id="cjk_bracketed",
        layout_writing_mode="vertical-rl",
    )
    assert uses_cjk_script(settings) is True
    assert uses_cjk_role_model(settings) is False
