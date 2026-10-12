from __future__ import annotations

from PIL import Image

from picture_capture.crop.export_output import (
    normalize_project_crop_widths,
    prepare_crop_background,
)
from picture_capture.crop.settings import normalize_crop_settings_payload
from picture_capture.models import AppSettings


def test_white_to_alpha_is_exact_and_preserves_polygon_mask():
    original = Image.new("RGBA", (3, 1), (255, 255, 255, 255))
    original.putpixel((1, 0), (254, 255, 255, 255))
    original.putpixel((2, 0), (0, 0, 0, 0))
    transparent = prepare_crop_background(original, transparent=True)
    assert [transparent.getpixel((x, 0))[3] for x in range(3)] == [0, 255, 0]
    opaque = prepare_crop_background(original, transparent=False)
    assert opaque.mode == "RGB"
    assert opaque.getpixel((0, 0)) == (255, 255, 255)
    assert opaque.getpixel((1, 0)) == (254, 255, 255)
    assert opaque.getpixel((2, 0)) == (255, 255, 255)


def _write_png(path, width, *, color="white"):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, 4), color).save(path)


def test_auto_width_pads_all_entry_and_illustration_pngs(tmp_path):
    pww = tmp_path / "QT" / "PWW"
    pic = tmp_path / "QT" / "PIC"
    _write_png(pww / "a_WW_001(1).png", 8)
    _write_png(pww / "b_WW_002(1).png", 12)
    _write_png(pic / "a_PIC_001.png", 3)
    _write_png(pic / "b_WW_002(P1).png", 13)

    config = {"entry_width_mode": "auto", "illustration_pad_to_entry_width": True}
    stats = normalize_project_crop_widths(tmp_path, config)
    assert stats == {
        "target_width": 12,
        "entries_padded": 1,
        "illustrations_padded": 1,
        "oversize": 1,
    }
    with Image.open(pww / "a_WW_001(1).png") as img:
        assert img.size == (12, 4)
        assert img.getpixel((11, 0)) == (255, 255, 255)
    with Image.open(pic / "a_PIC_001.png") as img:
        assert img.size == (12, 4)
    with Image.open(pic / "b_WW_002(P1).png") as img:
        assert img.size == (13, 4)
    assert normalize_project_crop_widths(tmp_path, config)["entries_padded"] == 0


def test_fixed_width_png_padding_uses_transparent_filler(tmp_path):
    pww = tmp_path / "QT" / "PWW"
    pic = tmp_path / "QT" / "PIC"
    pww.mkdir(parents=True)
    pic.mkdir(parents=True)
    word = prepare_crop_background(Image.new("RGB", (5, 4), "white"), transparent=True)
    word.save(pww / "a_WW_001(1).png")
    polygon = Image.new("RGBA", (3, 4), (0, 0, 0, 0))
    polygon.putpixel((0, 0), (10, 20, 30, 255))
    polygon.save(pic / "a_PIC_001.png")

    stats = normalize_project_crop_widths(tmp_path, {
        "entry_width_mode": "fixed",
        "entry_fixed_width": 10,
        "entry_transparent_background": True,
        "illustration_transparent_background": True,
        "illustration_pad_to_entry_width": True,
    })
    assert stats["target_width"] == 10
    assert (stats["entries_padded"], stats["illustrations_padded"]) == (1, 1)
    for path in [pww / "a_WW_001(1).png", pic / "a_PIC_001.png"]:
        with Image.open(path) as output:
            assert output.mode == "RGBA"
            assert output.size == (10, 4)
            assert output.getpixel((9, 0))[3] == 0
    with Image.open(pic / "a_PIC_001.png") as output:
        assert output.getpixel((0, 0)) == (10, 20, 30, 255)


def test_auto_width_without_words_does_not_infer_from_pictures(tmp_path):
    _write_png(tmp_path / "QT" / "PIC" / "a_PIC_001.png", 7)
    assert normalize_project_crop_widths(tmp_path, {
        "entry_width_mode": "auto",
    })["target_width"] == 0


def test_cropped_width_settings_are_additive_for_existing_v7_projects():
    defaults = normalize_crop_settings_payload(None, AppSettings())
    old = {
        "version": defaults["version"],
        "coordinate_space": defaults["coordinate_space"],
        "general_top_y": 123,
        "entry_left_padding_x": 14,
    }
    upgraded = normalize_crop_settings_payload(old, AppSettings())
    assert upgraded["general_top_y"] == 123
    assert upgraded["entry_left_padding_x"] == 14
    assert upgraded["entry_width_mode"] == "auto"
    assert upgraded["entry_transparent_background"] is False
    assert upgraded["illustration_transparent_background"] is False
    assert upgraded["illustration_pad_to_entry_width"] is True
