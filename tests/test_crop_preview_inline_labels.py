from picture_capture.crop_preview_labels import format_crop_preview_entry_label
from picture_capture.models import AppSettings
from picture_capture.crop_preview_display_settings import effective_crop_preview_font_size
from picture_capture.overlay_layout_helpers import effective_main_overlay_font_size


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
    settings.crop_preview_follow_zoom = False
    path = tmp_path / "settings.json"
    settings.to_json(path)
    saved = AppSettings.from_json(path)
    assert (saved.crop_preview_font_family, saved.crop_preview_font_size,
            saved.crop_preview_font_bold, saved.crop_preview_font_italic,
            saved.crop_preview_follow_zoom) == (
                "Arial", 18, True, True, False)


def test_preview_and_main_editor_same_size_at_all_zoom_levels():
    settings = AppSettings(main_entry_font_size=16, crop_preview_font_size=16)
    for width, scale in ((2800, 0.5), (2800, 0.25), (1400, 1.0),
                         (1400, 2.0), (600, 0.25), (2800, 8.0)):
        assert effective_crop_preview_font_size(width, scale, settings) == (
            effective_main_overlay_font_size(width, scale, settings)
        )


def test_preview_zoom_toggle_is_independent_of_main_editor():
    settings = AppSettings(main_entry_font_size=16, crop_preview_font_size=16)
    settings.crop_preview_follow_zoom = False
    assert effective_crop_preview_font_size(2800, 0.5, settings) == 16
    assert effective_crop_preview_font_size(2800, 0.1, settings) == 16
    settings.main_entry_follow_zoom = True
    assert effective_main_overlay_font_size(2800, 0.1, settings) == 5
