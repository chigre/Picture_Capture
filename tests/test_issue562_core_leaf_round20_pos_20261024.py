"""Round 20: POS regex and cue policy characterization after extracting the core."""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from picture_capture import paddle_headwords_core as core
from picture_capture.models import AppSettings
from picture_capture.ocr import pos_cue_policy
from picture_capture.profile.dictionary import load_dictionary_profile


def test_historical_module_signatures_and_owner():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(root.glob("*.py"))) == 10
    assert (root / "ocr" / "pos_cue_policy.py").is_file()
    assert not (root / "pos_cue_policy.py").exists()
    assert core._compile_patterns.__module__ == "picture_capture.paddle_headwords_core"
    assert core._strip_entry_modifiers.__module__ == "picture_capture.paddle_headwords_core"
    assert core._find_pos_cue.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(core._compile_patterns).parameters) == ["settings", "profile"]
    assert list(inspect.signature(core._strip_entry_modifiers).parameters) == ["prefix"]
    assert list(inspect.signature(core._find_pos_cue).parameters) == [
        "tail", "pos_pattern", "limit", "allow_numeric_prefix",
    ]


def test_profile_specific_regex_and_invalid_regex_mapping():
    settings = AppSettings(ocr_language="eng")
    latin = load_dictionary_profile(preset="latin_pos_classic", language="eng")
    actual = core._compile_patterns(settings, latin)
    expected = pos_cue_policy.compile_patterns(
        settings, latin, regex_module=re, settings_class=AppSettings,
    )
    assert [p.pattern for p in actual] == [p.pattern for p in expected]
    assert all(isinstance(p, re.Pattern) for p in actual)
    settings.paddle_headword_regex = "("
    with pytest.raises(ValueError, match="PaddleOCR"):
        core._compile_patterns(settings, latin)


def test_pos_grammar_noise_pronunciation_and_numeric_gate():
    pos = re.compile(r"s\.f\.|intr\.|pron\.", flags=re.I)
    for text, allow, expected_noise in [
        ("Es.f.", False, "E"),
        ("III s.f.", False, ""),
        ("18,8 intr.", True, ""),
    ]:
        match, noise = core._find_pos_cue(
            text, pos, 40, allow_numeric_prefix=allow,
        )
        assert match is not None
        assert noise == expected_noise
    assert core._find_pos_cue("18,8 intr.", pos, 40)[0] is None
    assert core._find_pos_cue("de s.f.", pos, 40)[0] is None
    assert core._find_pos_cue("Pron. [érbag]", pos, 40)[0] is None


def test_morphology_strip_and_live_patchpoint(monkeypatch):
    assert core._strip_entry_modifiers(", da") == ""
    assert core._strip_entry_modifiers("(pl. forms)") == ""
    assert core._strip_entry_modifiers("III") == ""
    old = core._strip_entry_modifiers
    called = []

    def substitute(value):
        called.append(value)
        return ""

    monkeypatch.setattr(core, "_strip_entry_modifiers", substitute)
    pos = re.compile(r"s\.f\.")
    matched, ignored_noise = core._find_pos_cue("irrelevant s.f.", pos, 60)
    assert matched is not None
    assert ignored_noise == ""
    assert called == ["irrelevant "]
    monkeypatch.setattr(core, "_strip_entry_modifiers", old)


def test_round20_leaves_grammar_tail_and_bundled_profile_in_core():
    """Guard against extracting adjacent globals and five wrappers by mistake."""
    import ast
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    core_source = (root / "ocr" / "headword_core_runtime.py").read_text(encoding="utf-8")
    leaf_source = (root / "ocr" / "pos_cue_policy.py").read_text(encoding="utf-8")
    core_ast = ast.parse(core_source)
    leaf_ast = ast.parse(leaf_source)
    core_defs = {n.name for n in core_ast.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    leaf_defs = {n.name for n in leaf_ast.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert leaf_defs == {"compile_patterns", "strip_entry_modifiers", "find_pos_cue"}
    assert {
        "_leading_inflection_cue", "_parallel_marker_extension",
        "_consume_leading_space", "_parse_structured_tail", "_parse_bug_types",
    } <= core_defs
    assert "_BUNDLED_PROFILE = load_dictionary_profile(" in core_source
    assert "_BUNDLED_PROFILE =" not in leaf_source
    assert core._BUNDLED_PROFILE is not None
    assert core._BUNDLED_PROFILE.metadata_labels
    assert core._parse_structured_tail.__module__ == "picture_capture.paddle_headwords_core"
