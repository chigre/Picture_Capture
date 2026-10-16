"""Unlined QA: search left-prefix whitespace to discover potentially missed headwords."""
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from picture_capture.crop.settings import (
    DEFAULT_UNLINED_LEFT_WHITE_PERCENT,
    UNLINED_LEFT_WHITE_PERCENT_KEY,
    normalize_crop_settings_payload,
)
from picture_capture.models import AppSettings
from picture_capture.unlined_line_export import (
    UnlinedRow,
    _save_unlined_rows,
    left_contiguous_white_percent,
)


@pytest.mark.parametrize(
    ("ink_x", "expected_white", "should_select"),
    [(0, 0.0, False), (10, 10.0, False), (50, 50.0, False),
     (51, 51.0, True), (80, 80.0, True), (None, 100.0, True)],
)
def test_contiguous_left_white_threshold_is_strictly_greater(
    ink_x, expected_white, should_select, tmp_path: Path
):
    source = Image.new("RGB", (100, 20), "white")
    if ink_x is not None:
        ImageDraw.Draw(source).rectangle((ink_x, 3, 99, 16), fill="black")
    assert left_contiguous_white_percent(source) == expected_white
    output = tmp_path / "output"
    page = tmp_path / "page.png"
    exported, matched, skipped, merged = _save_unlined_rows(
        source, page, [UnlinedRow(0, 0, "body", (0, 0, 100, 20), 0)],
        output, merge_by_page=False, filter_enabled=True, filter_blank=True,
        left_white_percent=50.0,
    )
    assert (exported, matched, skipped, merged) == (
        int(should_select), int(should_select), int(not should_select), False
    )
    if should_select:
        with Image.open(output / "page_UL_000.png") as saved:
            assert saved.size == (100, 20)
            assert saved.getpixel((0, 0)) == (255, 255, 255)
    source.close()


def test_paper_tint_single_noise_pixel_and_real_text():
    scan = Image.new("RGB", (100, 24), (220, 213, 198))
    draw = ImageDraw.Draw(scan)
    draw.point((1, 3), fill="black")  # isolated dust; not a printed column
    draw.rectangle((60, 4, 71, 19), fill=(35, 35, 35))
    assert left_contiguous_white_percent(scan) == 60.0
    scan.close()


def test_compact_five_percent_band_is_denominator_and_merged_rows_keep_left_white(tmp_path):
    # 5% of 600px = 30px crop; first dark pixels at 20px of those 30px.
    source = Image.new("RGB", (600, 60), "white")
    draw = ImageDraw.Draw(source)
    draw.rectangle((20, 3, 29, 18), fill="black")
    draw.rectangle((24, 32, 29, 47), fill="black")
    rows = [
        UnlinedRow(0, 0, "body", (0, 0, 30, 24), 0),
        UnlinedRow(0, 1, "body", (0, 28, 30, 52), 0),
    ]
    first = source.crop(rows[0].source_box)
    assert left_contiguous_white_percent(first) == pytest.approx(100 * 20 / 30)
    first.close()
    target_dir = tmp_path / "PSW_UNLINED"
    result = _save_unlined_rows(
        source, tmp_path / "page.png", rows, target_dir,
        merge_by_page=True, filter_enabled=True, filter_blank=True,
        left_white_percent=50.0,
    )
    assert result == (1, 2, 0, True)
    with Image.open(target_dir / "page_UL_PAGE.png") as image:
        assert image.size == (30, 48)
        assert image.getpixel((0, 5)) == (255, 255, 255)
        assert image.getpixel((20, 5)) == (0, 0, 0)
        assert image.getpixel((23, 36)) == (255, 255, 255)
        assert image.getpixel((24, 36)) == (0, 0, 0)
    assert not (target_dir / "page.UnlinedLines").exists()
    source.close()


def test_settings_default_is_50_even_for_legacy_08_ink_setting():
    settings = AppSettings()
    defaults = normalize_crop_settings_payload(None, settings)
    assert defaults[UNLINED_LEFT_WHITE_PERCENT_KEY] == DEFAULT_UNLINED_LEFT_WHITE_PERCENT == 50.0
    previous = dict(defaults)
    previous.pop(UNLINED_LEFT_WHITE_PERCENT_KEY, None)
    previous["unlined_export_blank_ink_percent"] = 0.8
    migrated = normalize_crop_settings_payload(previous, settings)
    assert migrated[UNLINED_LEFT_WHITE_PERCENT_KEY] == 50.0
