"""Issue #562: physical Profile language policy, live public API contracts."""
from __future__ import annotations

import inspect

from picture_capture import app
from picture_capture.profile import language_policy, setup, wizard_catalog


def test_project_language_vocabulary_is_physically_owned_by_profile() -> None:
    assert app.PROJECT_LANGUAGE_CODES is language_policy.PROJECT_LANGUAGE_CODES
    assert app.OCR_TO_PROJECT_LANGUAGE is language_policy.OCR_TO_PROJECT_LANGUAGE
    assert app.project_language_from_ocr.__module__ == "picture_capture.app"
    assert ".split(\"+\")" in inspect.getsource(language_policy.project_language_from_ocr)
    assert ".split(\"+\")" not in inspect.getsource(app.project_language_from_ocr)
    assert "zh" in app.PROJECT_LANGUAGE_CODES


def test_project_language_normalization_and_legacy_aliases(monkeypatch) -> None:
    assert app.project_language_from_ocr(" ENG + chi_sim ") == "en"
    assert app.project_language_from_ocr("chi_tra+eng") == "zh"
    assert app.project_language_from_ocr("xx+eng") == "xx"
    assert app.project_language_from_ocr("zzz") == ""
    assert app.project_language_from_ocr("") == ""
    assert app.project_language_from_ocr(None) == ""
    monkeypatch.setattr(app, "OCR_TO_PROJECT_LANGUAGE", {"eng": "zz"})
    assert app.project_language_from_ocr("eng+fra") == "zz"
    assert language_policy.project_language_from_ocr("eng") == "en"


def test_wizard_language_label_policy_and_live_monkeypatch(monkeypatch) -> None:
    assert setup._ocr_language_code("英语 (eng)") == "eng"
    assert setup._ocr_language_code("  chi_sim  ") == "chi_sim"
    assert setup._ocr_language_code("") == "eng"
    assert setup._ocr_language_code(None) == "eng"
    assert setup._label_for_value({"A": "a", "B": "a"}, "a", "?") == "A"
    assert setup._label_for_value({"A": "a"}, "b", "?") == "?"
    assert "for label, mapped in mapping.items()" in inspect.getsource(wizard_catalog.label_for_value)
    assert "for label, mapped in mapping.items()" not in inspect.getsource(setup._label_for_value)
    monkeypatch.setattr(setup, "OCR_LANGUAGE_LABEL_TO_VALUE", {"测试语言": "test"})
    assert setup._ocr_language_code("测试语言") == "test"
    assert wizard_catalog.ocr_language_code("英语 (eng)") == "eng"
