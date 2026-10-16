import pytest
from types import SimpleNamespace

from picture_capture.models import AppSettings
from picture_capture.ref_box_ocr import extract_ref_text
from picture_capture.ui.settings import schema
from picture_capture.ui.settings.lifecycle import validate_ref_box_controls


def test_default_ref_regex_handles_paired_and_partial_quotes():
    pattern = AppSettings().ref_ocr_extract_regex
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
        assert extract_ref_text(raw, pattern) == expected


def test_ref_regex_is_fully_customizable_and_match_contract():
    assert extract_ref_text("参见: apple, today", r"参见:\s*([a-z]+)") == "apple"
    assert extract_ref_text("REF 42", r"REF\s+\d+") == "REF 42"
    assert extract_ref_text("no match", r"参见:(\w+)") == "no match"
    assert extract_ref_text("raw content", "") == "raw content"
    assert extract_ref_text("text", r"(missing)?") == "text"


def test_regex_settings_field_and_validation():
    assert "ref_ocr_extract_regex" in schema.REF_OCR_EXTRACTION_FIELDS
    assert any(name == "ref_ocr_extract_regex" for _, name, _cast in schema.FIELDS)
    validate_ref_box_controls({
        "ref_ocr_extract_regex": SimpleNamespace(get=lambda: r"(apple|梨子)")
    })
    with pytest.raises(ValueError, match="正则"):
        validate_ref_box_controls({
            "ref_ocr_extract_regex": SimpleNamespace(get=lambda: "(")
        })
