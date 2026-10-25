"""Round 21: six CJK OCR headword implementations and historical entrypoints."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

from picture_capture import paddle_headwords_core as core
from picture_capture.models import AppSettings
from picture_capture.ocr import cjk_prefix_parsing, cjk_single_lemma_parsing


def _settings():
    return AppSettings(ocr_language="chi_sim")


def test_round21_exact_owners_without_moving_runtime_regex_globals():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(pkg.glob("*.py"))) == 10
    owners = {
        "cjk_prefix_parsing.py": {
            "starts_with_unconfigured_headword_symbol",
            "parse_cjk_marker_pinyin_headword",
            "parse_chinese_bracketed_headword",
        },
        "cjk_single_lemma_parsing.py": {
            "parse_cjk_single_with_pinyin",
            "make_chinese_visual_headword",
            "parse_chinese_single_character_headword",
        },
    }
    for file, expected in owners.items():
        path = pkg / "ocr" / file
        assert path.is_file()
        assert not (pkg / file).exists()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert {
            n.name for n in tree.body if isinstance(n, ast.FunctionDef)
        } == expected
        assert not any(
            isinstance(n, (ast.Assign, ast.AnnAssign))
            for n in tree.body
        )
    # The implementation and runtime regex state physically moved into OCR;
    # the historical root import remains one live module-identity bridge.
    compatibility = (pkg / "paddle_headwords_core.py").read_text(encoding="utf-8")
    assert "_sys.modules[__name__] = _canonical" in compatibility
    source = (pkg / "ocr/headword_core_runtime.py").read_text(encoding="utf-8")
    for constant in (
        "_CJK_SINGLE_PINYIN_RE =", "_CJK_IDEOGRAPH_RE =",
        "_CJK_RADICAL_SECTION_RE =", "_BRACKET_CLOSER_BY_OPENER =",
    ):
        assert constant in source


def test_bracketed_closed_open_and_japanese_reading_prefix():
    settings = _settings()
    closed = core._parse_chinese_bracketed_headword("【案件】说明", settings)
    assert closed is not None
    assert closed.normalized == "案件"
    assert closed.definition_text == "说明"
    assert closed.parser_stage == "chinese_bracketed_headword"
    assert type(closed) is core.HeadwordParse

    opened = core._parse_chinese_bracketed_headword("【", settings)
    assert opened is not None
    assert opened.normalized == "【"
    assert "accepted_unclosed_chinese_headword_bracket" in opened.ocr_repairs

    japanese = core._parse_chinese_bracketed_headword(
        "あい【愛】ことば", AppSettings(ocr_language="jpn"),
        enforce_chinese_language=False, allow_japanese_reading_prefix=True,
        allowed_openers=("【",),
    )
    assert japanese is not None and japanese.normalized == "愛"
    assert japanese.parser_trace[0] == "japanese_reading_prefix:あい"
    assert core._parse_chinese_bracketed_headword(
        "【案件】", settings, allowed_openers=("〔",),
    ) is None


def test_configured_symbol_gate_and_marker_parser_patch_callbacks(monkeypatch):
    settings = _settings()
    settings.profile_symbol_inventory_version = 1
    inventory = lambda _settings, _profile: {
        "enabled": True, "entry_markers": ("○",), "bracket_openers": ("【",),
    }
    monkeypatch.setattr(core, "_configured_symbol_inventory", inventory)
    profile = SimpleNamespace()
    assert not core._starts_with_unconfigured_headword_symbol("○中国", settings, profile)
    assert not core._starts_with_unconfigured_headword_symbol("【中国】", settings, profile)
    assert core._starts_with_unconfigured_headword_symbol("◆中国", settings, profile)
    marker = core._parse_cjk_marker_pinyin_headword("○中国 zhōng", settings, profile)
    assert marker is not None
    assert marker.normalized == "中国"
    assert marker.parser_stage == "cjk_marker_pinyin"
    assert type(marker) is core.HeadwordParse
    assert core._parse_cjk_marker_pinyin_headword("◆中国", settings, profile) is None


def test_single_character_and_pinyin_variants_keep_visual_gate():
    settings = _settings()
    parsed = core._parse_cjk_single_with_pinyin("案* ān", settings)
    assert parsed is not None and parsed.normalized == "案"
    assert parsed.parser_stage == "cjk_single_with_pinyin"
    assert "pinyin:ān" in parsed.parser_trace
    assert type(parsed) is core.HeadwordParse
    pure = core._parse_chinese_single_character_headword("案", settings)
    assert pure is not None and pure.normalized == "案"
    assert pure.parser_stage == "chinese_single_character"
    assert core._parse_chinese_single_character_headword("一部", settings) is None
    assert core._parse_cjk_single_with_pinyin("plain text", settings) is None


def test_original_signatures_and_live_single_visual_constructor(monkeypatch):
    old = core._make_chinese_visual_headword
    called = []

    def spy(*args, **kwargs):
        called.append((args, kwargs))
        return old(*args, **kwargs)

    monkeypatch.setattr(core, "_make_chinese_visual_headword", spy)
    assert core._parse_cjk_single_with_pinyin("案* ān", _settings()) is not None
    assert called and called[0][1]["stage"] == "cjk_single_with_pinyin"
    # Restore the historical callable before asserting its persisted module identity.
    monkeypatch.setattr(core, "_make_chinese_visual_headword", old)
    for name in (
        "_starts_with_unconfigured_headword_symbol",
        "_parse_cjk_marker_pinyin_headword",
        "_parse_cjk_single_with_pinyin",
        "_parse_chinese_bracketed_headword",
        "_make_chinese_visual_headword",
        "_parse_chinese_single_character_headword",
    ):
        assert getattr(core, name).__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(core._parse_chinese_bracketed_headword).parameters) == [
        "text", "settings", "enforce_chinese_language",
        "allow_japanese_reading_prefix", "allowed_openers",
    ]
    assert cjk_prefix_parsing.parse_chinese_bracketed_headword.__module__.endswith(".cjk_prefix_parsing")
    assert cjk_single_lemma_parsing.parse_cjk_single_with_pinyin.__module__.endswith(".cjk_single_lemma_parsing")
