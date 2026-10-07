from __future__ import annotations

from PIL import Image

from picture_capture import app, layout_percent_helpers as layout


def test_phase7g_app_reexports_layout_percent_helpers() -> None:
    for name in (
        "LAYOUT_PERCENT_AXES",
        "_layout_percent_denominator",
        "_layout_pixels_to_percent",
        "_layout_percent_to_pixels",
        "_format_layout_percent",
        "_column_pixels_to_percent",
        "_column_percent_to_pixels",
        "_review_height_pixels_to_percent",
        "_review_height_percent_to_pixels",
        "_format_review_height_percent",
    ):
        assert getattr(app, name) is getattr(layout, name)


def test_layout_percent_helpers_keep_axis_contract() -> None:
    image = Image.new("RGB", (1000, 2000), "white")

    assert layout._layout_pixels_to_percent(image, "manual_x", 125) == 12.5
    assert layout._layout_pixels_to_percent(image, "start_y", 200) == 10.0
    assert layout._layout_percent_to_pixels(image, "column_width", 25.0) == 250
    assert layout._layout_percent_to_pixels(image, "character_height", 1.5) == 30
    assert layout._format_layout_percent(12.500) == "12.5"
