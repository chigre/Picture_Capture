"""Issue #562: ordinary thresholding and OCR script validation core bridges."""
from __future__ import annotations

import inspect
from typing import get_type_hints
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from picture_capture import processing as processing_public, processing_core
from picture_capture import paddle_headwords as headwords_public, paddle_headwords_core
from picture_capture.ordinary import ink_threshold
from picture_capture.ocr import headword_script

PKG = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_real_package_owners_and_historical_core_definitions():
    assert (PKG / "ordinary/ink_threshold.py").is_file()
    assert (PKG / "ocr/headword_script.py").is_file()
    assert not (PKG / "ink_threshold.py").exists()
    assert not (PKG / "headword_script.py").exists()
    assert len(list(PKG.glob("*.py"))) == 5
    for module, name, path in (
        (processing_core, "_left_edge_otsu_threshold", "processing_core"),
        (processing_core, "_left_edge_ink_mask", "processing_core"),
        (paddle_headwords_core, "_ocr_language_parts", "paddle_headwords_core"),
        (paddle_headwords_core, "_leading_script_family", "paddle_headwords_core"),
        (paddle_headwords_core, "_headword_script_compatibility", "paddle_headwords_core"),
    ):
        func = getattr(module, name)
        assert func.__module__ == "picture_capture." + path
    assert list(inspect.signature(processing_core._left_edge_ink_mask).parameters) == ["gray", "settings"]
    assert get_type_hints(ink_threshold.ink_mask)["return"] is np.ndarray


def test_otsu_and_fixed_adaptive_masks_match_new_owner():
    gray = np.array([[0, 10, 30, 80], [140, 175, 235, 255]], dtype=np.uint8)
    assert processing_core._left_edge_otsu_threshold(gray) == ink_threshold.otsu_threshold(gray)
    assert processing_core._left_edge_otsu_threshold(np.empty((0, 0), dtype=np.uint8)) == 127
    for mode in ("auto", "fixed", "adaptive"):
        settings = SimpleNamespace(analysis_threshold_mode=mode, darkness_threshold=450)
        actual = processing_core._left_edge_ink_mask(gray, settings)
        expected = ink_threshold.ink_mask(gray, settings)
        assert np.array_equal(actual, expected)
        assert actual.dtype == np.bool_


def test_threshold_bridge_reads_public_monkeypatch_at_call_time(monkeypatch):
    settings = SimpleNamespace(analysis_threshold_mode="auto", darkness_threshold=600)
    gray = np.array([[1, 150, 201]], dtype=np.uint8)
    original = processing_core._left_edge_otsu_threshold
    monkeypatch.setattr(processing_public, "_left_edge_otsu_threshold", lambda _gray: 200)
    assert processing_core._left_edge_ink_mask(gray, settings).tolist() == [[True, True, False]]
    monkeypatch.setattr(processing_public, "_left_edge_otsu_threshold", original)


def test_script_families_and_semantic_language_precedence():
    for text, family in (
        ("", ""), ("  -・漢字", "kana"), ("字", "han"),
        ("カナ", "kana"), ("한글", "hangul"), ("café", "other"),
        ("  - 漢字", "han"),
    ):
        assert paddle_headwords_core._leading_script_family(text) == headword_script._leading_script_family(text)
        assert paddle_headwords_core._leading_script_family(text) == family
    settings = SimpleNamespace(ocr_language="spa+eng", paddle_language="ch")
    assert paddle_headwords_core._ocr_language_parts(settings) == {"spa", "eng"}
    settings.ocr_language = ""
    assert paddle_headwords_core._ocr_language_parts(settings) == {"ch"}


def test_script_guard_decisions_and_facade_patch(monkeypatch):
    def config(lang):
        return SimpleNamespace(ocr_language=lang, paddle_language="",
            profile_headword_script_guard_version=1,
            profile_headword_script_guard_enabled=True)
    kanji = SimpleNamespace(normalized="漢字")
    kana = SimpleNamespace(normalized="かな")
    assert paddle_headwords_core._headword_script_compatibility(config("spa"), kanji) == (False, "han")
    assert paddle_headwords_core._headword_script_compatibility(config("jpn"), kanji) == (True, "han")
    assert paddle_headwords_core._headword_script_compatibility(config("jpn"), kana) == (True, "kana")
    assert paddle_headwords_core._headword_script_compatibility(config("spa"), kana) == (False, "kana")
    original = paddle_headwords_core._ocr_language_parts
    monkeypatch.setattr(headwords_public, "_ocr_language_parts", lambda settings: {"jpn"})
    assert paddle_headwords_core._headword_script_compatibility(config("spa"), kana) == (True, "kana")
    monkeypatch.setattr(headwords_public, "_ocr_language_parts", original)
