"""Issue #562: OCR language selectors retain historical model priorities."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture import paddle_headwords as paddle_public
from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import language_resolution

PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def settings(lang, model=""):
    return SimpleNamespace(ocr_language=lang, paddle_language=model)


def test_historical_paths_and_no_root_compat_shims():
    assert (PKG / "ocr/language_resolution.py").is_file()
    assert not (PKG / "language_resolution.py").exists()
    assert len(list(PKG.glob("*.py"))) == 5
    for fn in (core._is_chinese_ocr, core._is_japanese_ocr, core._paddle_language):
        assert fn.__module__ == "picture_capture.paddle_headwords_core"
        assert list(inspect.signature(fn).parameters) == ["settings"]


def test_semantic_and_paddle_language_cases():
    cases = (
        ("spa+eng", "", False, False, "es"),
        ("chi_tra+eng", "", True, False, "chinese_cht"),
        ("jpn+eng", "", False, True, "en"),
        ("spa+eng", "japan", False, True, "japan"),
        ("spa", "ch", True, False, "ch"),
        ("eng", " en ", False, False, "en"),
        ("xx+eng", "", False, False, "en"),
        ("xx", "", False, False, "xx"),
        ("jpn_vert", "", False, True, "jpn_vert"),
        ("chi_sim", "", True, False, "ch"),
    )
    for lang, model, chinese, japanese, paddle in cases:
        s = settings(lang, model)
        assert core._is_chinese_ocr(s) == language_resolution.is_chinese_ocr(s) == chinese
        assert core._is_japanese_ocr(s) == language_resolution.is_japanese_ocr(s) == japanese
        assert core._paddle_language(s) == language_resolution.paddle_language(s) == paddle


def test_public_facade_language_patch_is_live(monkeypatch):
    original = core._paddle_language
    monkeypatch.setattr(paddle_public, "_paddle_language", lambda s: "patched")
    assert core._paddle_language(settings("spa")) == "patched"
    monkeypatch.setattr(paddle_public, "_paddle_language", original)
    original_chinese = core._is_chinese_ocr
    monkeypatch.setattr(paddle_public, "_is_chinese_ocr", lambda s: True)
    assert core._is_chinese_ocr(settings("spa")) is True
    monkeypatch.setattr(paddle_public, "_is_chinese_ocr", original_chinese)
