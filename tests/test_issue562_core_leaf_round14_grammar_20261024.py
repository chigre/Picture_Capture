"""Issue #562 round 14: OCR grammar-tail state machine stays patchable."""
from __future__ import annotations

import inspect
from pathlib import Path
import re

from picture_capture import paddle_headwords as facade
from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import grammar_tail_parsing
from picture_capture.ocr.headword_models import GrammarTailParse

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def parse_direct(tail, pos, search_limit=60, **kwargs):
    return grammar_tail_parsing.parse_structured_tail(
        tail, pos, search_limit,
        consume_space_fn=core._consume_leading_space,
        find_pos_fn=core._find_pos_cue,
        strip_fn=core._strip_entry_modifiers,
        usage_abbreviations=core._USAGE_ABBREVIATIONS,
        grammar_cls=core.GrammarTailParse,
        re_module=core.re,
        **kwargs,
    )


def test_leaf_root_inventory_and_historical_grammar_model_identity():
    assert len(list(ROOT.glob("*.py"))) == 7
    assert (ROOT / "ocr/grammar_tail_parsing.py").is_file()
    assert not (ROOT / "grammar_tail_parsing.py").exists()
    for fn in (
        core._leading_inflection_cue,
        core._parallel_marker_extension,
        core._consume_leading_space,
        core._parse_structured_tail,
        core._parse_bug_types,
    ):
        assert fn.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(core._parse_structured_tail).parameters) == [
        "tail", "pos_pattern", "search_limit",
        "parallel_descriptor", "parallel_label", "allow_numeric_prefix",
    ]
    assert GrammarTailParse.__module__ == "picture_capture.paddle_headwords_core"
    assert core.GrammarTailParse is GrammarTailParse


def test_morphology_cue_and_parallel_bar_match_historical_behavior():
    assert core._leading_inflection_cue("(pl. cosas)") == (True, "(pl. cosas)")
    assert core._leading_inflection_cue(" ordinary") == (False, "")
    assert core._leading_inflection_cue("(pl. cosas)") == (
        grammar_tail_parsing.leading_inflection_cue("(pl. cosas)")
    )
    for tail in (" mail || Correo", " || definition", " mail ll al ~"):
        assert core._parallel_marker_extension(tail) == (
            grammar_tail_parsing.parallel_marker_extension(tail)
        )
    extra, consumed, flag, label = core._parallel_marker_extension(" mail || Correo")
    assert (extra, flag, label) == ("mail", True, "parallel_gloss")
    assert consumed > 0
    assert core._consume_leading_space("  word", 0) == 2


def test_structured_tail_is_identical_and_keeps_original_class():
    pos = re.compile(r"(?:adj[.]|s[.]f[.])", re.IGNORECASE)
    for tail, options in (
        ("adj. Amer. definition", {}),
        (", da (pl. otras) adj. definition", {}),
        ("(pl. otras) adj. definition", {}),
        ("adj. definition", {"parallel_descriptor": True, "parallel_label": "parallel_gloss"}),
    ):
        actual = core._parse_structured_tail(tail, pos, 64, **options)
        expected = parse_direct(tail, pos, 64, **options)
        assert type(actual) is GrammarTailParse
        assert actual == expected
        assert actual.parser_stage if hasattr(actual, "parser_stage") else True
    assert core._parse_structured_tail("adj. word", pos, 64).pos_text == "adj."


def test_structured_tail_uses_live_find_pos_and_usage_inventory(monkeypatch):
    original_find = core._find_pos_cue
    calls = []
    def blocked(text, pattern, search_limit, **kwargs):
        calls.append((text, search_limit))
        return None, ""
    monkeypatch.setattr(facade, "_find_pos_cue", blocked)
    p = core._parse_structured_tail("adj. Amer. sense", re.compile(r"adj[.]"), 55)
    assert p.pos_text == ""
    assert calls and calls[0][1] == 55
    monkeypatch.setattr(facade, "_find_pos_cue", original_find)
    original_usage = core._USAGE_ABBREVIATIONS
    monkeypatch.setattr(facade, "_USAGE_ABBREVIATIONS", {"amer"})
    p = core._parse_structured_tail("adj. Amer. sense", re.compile(r"adj[.]"), 55)
    assert p.usage_text == "Amer."
    monkeypatch.setattr(facade, "_USAGE_ABBREVIATIONS", original_usage)


def test_bug_tags_are_deduplicated_and_preserve_order():
    grammar = GrammarTailParse()
    got = core._parse_bug_types(
        ("reassigned_trailing_punctuation:,",
         "joined_detached_lemma_suffix",
         "ignored_pre_pos_noise",
         "ocr_6->o",
         "ocr_6->o"),
        grammar, "fragment",
    )
    assert got == (
        "COMMA_SWALLOWED", "SPLIT_HEADWORD",
        "POS_GLYPH_NOISE", "OCR_CHARACTER_REPAIR", "CONTINUATION_FRAGMENT",
    )
    assert got == grammar_tail_parsing.parse_bug_types(
        ("reassigned_trailing_punctuation:,",
         "joined_detached_lemma_suffix",
         "ignored_pre_pos_noise",
         "ocr_6->o",
         "ocr_6->o"),
        grammar, "fragment",
    )
