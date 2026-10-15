from picture_capture.ref_box_ocr import extract_ref_quoted_text
from picture_capture.models import AppSettings
from picture_capture.ui.settings import schema


def test_ref_quote_extraction():
    cases = {
        "参见“词条”结束": "词条",
        "参见‘同义词’结束": "同义词",
        "前缀“词条": "词条",
        "词条”后缀": "词条",
        "前缀‘词条": "词条",
        "词条’后缀": "词条",
        "无引号文本": "无引号文本",
        "前缀“词条”后缀": "词条",
    }
    for raw, expected in cases.items():
        assert extract_ref_quoted_text(raw) == expected


def test_ref_quote_preference_in_settings():
    assert AppSettings().ref_ocr_quote_extraction is True
    assert any(name == "ref_ocr_quote_extraction" for _, name in schema.REF_BOX_CHECKS)
