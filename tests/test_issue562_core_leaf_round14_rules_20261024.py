"""Issue #562 round 14: project OCR filter language and priority."""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from picture_capture import paddle_headwords as facade
from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import user_filter_rules
from picture_capture.ocr.headword_models import HeadwordFilterRule

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def evaluation(rules, *, raw="casa", normalized="casa", line="casa adj.", pos="adj."):
    return core.evaluate_headword_filter_rules(
        rules, raw_lemma=raw, normalized_lemma=normalized,
        line_text=line, pos_text=pos,
    )


def test_import_identity_signatures_and_root_inventory():
    assert len(list(ROOT.glob("*.py"))) == 7
    assert (ROOT / "ocr/user_filter_rules.py").is_file()
    assert not (ROOT / "user_filter_rules.py").exists()
    for fn, args in (
        (core.parse_headword_filter_rules, ["text", "source"]),
        (core.load_headword_filter_rules, ["path"]),
        (core._rule_matches, ["rule", "raw_lemma", "normalized_lemma", "line_text", "pos_text"]),
        (core.evaluate_headword_filter_rules, ["rules", "raw_lemma", "normalized_lemma", "line_text", "pos_text"]),
    ):
        assert fn.__module__ == "picture_capture.paddle_headwords_core"
        assert list(inspect.signature(fn).parameters) == args
    assert core.HeadwordFilterRule is HeadwordFilterRule
    assert HeadwordFilterRule.__module__ == "picture_capture.paddle_headwords_core"


def test_rule_parser_compiles_aliases_regex_and_tracks_source():
    source = "# comment\nlemma_exact: casa\naccept_lemma_regex: ^ca[sz]a$\npos_exclude_exact: adj.\n"
    rules = core.parse_headword_filter_rules(source, "project/profile")
    assert len(rules) == 3
    assert all(type(r) is HeadwordFilterRule for r in rules)
    assert [r.line_number for r in rules] == [2, 3, 4]
    assert rules[0].kind == "reject_lemma_exact"
    assert rules[1].regex is not None
    assert rules[0].display == "reject_lemma_exact: casa"
    assert rules[0].source == "project/profile"
    assert evaluation(rules) == user_filter_rules.evaluate_headword_filter_rules(
        rules, raw_lemma="casa", normalized_lemma="casa",
        line_text="casa adj.", pos_text="adj.",
        match_fn=core._rule_matches,
    )
    out = evaluation(rules)
    assert out["rejected"] and not out["accepted"]
    assert out["pos_excluded"]
    assert out["reject_rule"] and out["accept_rule"]


def test_invalid_rule_has_stable_validation_and_utf8_bom(tmp_path):
    for text in ("junk", "missing_kind: abc", "reject_lemma_exact:", "reject_lemma_regex: ("):
        with pytest.raises(ValueError):
            core.parse_headword_filter_rules(text)
    assert core.load_headword_filter_rules(None) == []
    path = tmp_path / "headword_filter_rules.txt"
    path.write_text("# ignored\naccept_line_contains: 字義\n", encoding="utf-8-sig")
    rules = core.load_headword_filter_rules(path)
    assert len(rules) == 1 and rules[0].source == str(path)
    assert evaluation(rules, line="詞 字義")["accepted"]


def test_live_rule_aliases_and_matching_seams(monkeypatch):
    original_aliases = core._RULE_ALIASES
    monkeypatch.setattr(facade, "_RULE_ALIASES", {"mine": "reject_lemma_exact"})
    rules = core.parse_headword_filter_rules("mine: casa")
    assert rules[0].kind == "reject_lemma_exact"
    monkeypatch.setattr(facade, "_RULE_ALIASES", original_aliases)
    original_match = core._rule_matches
    seen = []
    def matcher(rule, **kw):
        seen.append(rule.kind)
        return rule.kind == "accept_lemma_exact"
    monkeypatch.setattr(facade, "_rule_matches", matcher)
    assert evaluation(core.parse_headword_filter_rules("accept_lemma_exact: xyz"))["accepted"]
    assert seen == ["accept_lemma_exact"]
    monkeypatch.setattr(facade, "_rule_matches", original_match)


def test_loader_resolves_current_public_parser(monkeypatch, tmp_path):
    path = tmp_path / "rules.txt"
    path.write_text("reject_lemma_exact: casa", encoding="utf-8")
    original = core.parse_headword_filter_rules
    seen = []
    def patched(text, source=""):
        seen.append((text, source))
        return original(text, source)
    monkeypatch.setattr(facade, "parse_headword_filter_rules", patched)
    assert core.load_headword_filter_rules(path)[0].kind == "reject_lemma_exact"
    assert seen == [("reject_lemma_exact: casa", str(path))]
    monkeypatch.setattr(facade, "parse_headword_filter_rules", original)
