from picture_capture.crop_preview_labels import format_crop_preview_entry_label
from picture_capture.models import AppSettings


def test_inline_entry_crop_label():
    assert format_crop_preview_entry_label("word", "page_001.png") == "word  |  page_001.png"
    assert format_crop_preview_entry_label("", "page_001.png") == "page_001.png"
    assert format_crop_preview_entry_label("multi\nline", "page_001.png") == "multi line  |  page_001.png"


def test_crop_preview_font_settings_roundtrip(tmp_path):
    settings = AppSettings()
    assert settings.crop_preview_font_size == 12
    settings.crop_preview_font_family = "Arial"
    settings.crop_preview_font_size = 18
    settings.crop_preview_font_bold = True
    settings.crop_preview_font_italic = True
    path = tmp_path / "settings.json"
    settings.to_json(path)
    saved = AppSettings.from_json(path)
    assert (saved.crop_preview_font_family, saved.crop_preview_font_size,
            saved.crop_preview_font_bold, saved.crop_preview_font_italic) == (
                "Arial", 18, True, True)
