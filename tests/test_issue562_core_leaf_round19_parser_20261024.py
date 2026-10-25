"""Round 19: complete OCR lemma parser extraction, original core/patch contracts."""
from __future__ import annotations

import inspect
from pathlib import Path

from picture_capture import paddle_headwords_core as core
from picture_capture.models import AppSettings
from picture_capture.ocr import lemma_parser
from picture_capture.profile.dictionary import load_dictionary_profile


def test_lemma_parser_owner_and_old_public_signature():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert (pkg / "ocr" / "lemma_parser.py").is_file()
    assert not (pkg / "lemma_parser.py").exists()
    assert len(list(pkg.glob("*.py"))) == 7
    assert core.parse_headword_text.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(core.parse_headword_text).parameters) == [
        "text", "settings", "patterns", "profile",
    ]


def test_parser_retains_latin_arabic_and_numbered_kana_paths():
    latin = load_dictionary_profile(preset="latin_pos_classic", language="eng")
    for line in ("ab·a·cus ['æbəkəs] n. frame", "a·ban·don /ə'bændən/ v.t. leave"):
        parsed = core.parse_headword_text(line, AppSettings(ocr_language="eng"), profile=latin)
        assert parsed is not None and parsed.has_pos
        assert type(parsed) is core.HeadwordParse
        assert parsed.__class__.__module__ == "picture_capture.paddle_headwords_core"
    assert core.parse_headword_text(
        "中文正文", AppSettings(ocr_language="eng"), profile=latin,
    ) is None

    arabic = load_dictionary_profile(preset="arabic_rtl_bilingual_2col", language="ara")
    parsed = core.parse_headword_text("كتاب", AppSettings(ocr_language="ara"), profile=arabic)
    assert parsed is not None and parsed.normalized == "كتاب"
    japanese = load_dictionary_profile(preset="jpn_numbered_headword_2col", language="jpn")
    parsed = core.parse_headword_text("10. かな", AppSettings(ocr_language="jpn"), profile=japanese)
    assert parsed is not None and parsed.normalized == "かな"


def test_parser_uses_current_core_compiler_and_ocr_repair(monkeypatch):
    latin = load_dictionary_profile(preset="latin_pos_classic", language="eng")
    original_compile = core._compile_patterns
    original_repair = core._repair_headword_ocr
    seen = []

    def compile_spy(*args, **kwargs):
        seen.append("compiled")
        return original_compile(*args, **kwargs)

    def repair_spy(*args, **kwargs):
        seen.append("repaired")
        return original_repair(*args, **kwargs)

    monkeypatch.setattr(core, "_compile_patterns", compile_spy)
    monkeypatch.setattr(core, "_repair_headword_ocr", repair_spy)
    parsed = core.parse_headword_text(
        "ab·a·cus ['æbəkəs] n. frame",
        AppSettings(ocr_language="eng"), profile=latin,
    )
    assert parsed is not None
    assert "compiled" in seen and "repaired" in seen


def test_parser_leaf_matches_forwarded_dependencies(monkeypatch):
    latin = load_dictionary_profile(preset="latin_pos_classic", language="eng")
    settings = AppSettings(ocr_language="eng")
    seen = []

    def spy(text, actual_settings, patterns=None, profile=None, *, deps):
        seen.append(deps)
        return "from-leaf"

    monkeypatch.setattr(lemma_parser, "parse_headword_text_impl", spy)
    assert core.parse_headword_text("test", settings, profile=latin) == "from-leaf"
    assert seen and seen[0]["HeadwordParse"] is core.HeadwordParse
    assert seen[0]["_compile_patterns"] is core._compile_patterns
    assert seen[0]["_parse_structured_tail"] is core._parse_structured_tail
