"""REF OCR label presentation, independent from source bounding box."""
from picture_capture.models import AppSettings
from picture_capture.ref_text_label_layout import ref_text_label_rect
from picture_capture.ui.settings import schema


def test_label_prefers_right_of_original_ref():
    x, y, w, h = ref_text_label_rect(
        (60, 40, 80, 20), (400, 200),
        text="苹果", scale=1.0, font_size=16, gap=6, padding=4,
    )
    assert x >= 60 + 80
    assert 0 <= y < 200
    assert x + w <= 400
    assert y + h <= 200


def test_label_avoids_right_edge_by_moving_left():
    x, y, w, h = ref_text_label_rect(
        (340, 40, 50, 20), (400, 200),
        text="梨子苹果", scale=1.0, font_size=16, gap=6, padding=4,
    )
    assert x + w <= 340
    assert x >= 0
    assert y + h <= 200


def test_label_stays_inside_page_with_multiline_and_zoom():
    for zoom in (0.35, 1, 2):
        x, y, w, h = ref_text_label_rect(
            (55, 175, 160, 22), (300, 200),
            text="apple banana orange\n长词条别名一二三",
            scale=zoom, font_size=16,
        )
        assert x >= 0 and y >= 0 and w > 0 and h > 0
        assert x + w <= round(300 * zoom)
        assert y + h <= round(200 * zoom)


def test_label_style_and_visibility_are_owned_by_label_settings():
    settings = AppSettings()
    assert settings.ref_box_fill_opacity == 0.0
    assert settings.ref_box_filled_opacity == 0.0
    assert settings.ref_text_label_background_opacity == 95.0
    assert settings.ref_box_show_text is True
    label_fields = set(schema.REF_TEXT_LABEL_FIELDS)
    assert {"ref_box_text_color", "ref_box_font_family",
            "ref_box_font_size", "ref_text_label_background_color",
            "ref_text_label_gap", "ref_text_label_padding"} <= label_fields
    assert "ref_box_text_color" not in schema.REF_BOX_STYLE_FIELDS
    assert ("显示 REF 文本标签", "ref_box_show_text") in schema.REF_TEXT_LABEL_CHECKS
