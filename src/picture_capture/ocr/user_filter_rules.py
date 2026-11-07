from __future__ import annotations

"""User-editable OCR headword rules. Core passes current aliases/constructors,
parser and match function. Rule class identity and reject-over-accept priority
remain unchanged; no rules file format is changed.
"""

from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from typing import Any
import re
from .headword_models import HeadwordFilterRule


def parse_headword_filter_rules(
    text: str, source: str = "", *,
    aliases: Mapping[str, str], kinds: Collection[str],
    rule_cls: type, re_module: Any = re,
) -> list[HeadwordFilterRule]:
    """Parse one-rule-per-line user rules and validate regexes up front."""
    rules: list[HeadwordFilterRule] = []
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(
                f"词头规则第 {line_number} 行缺少 ':'：{raw_line.strip()}"
            )
        raw_kind, value = stripped.split(":", 1)
        kind = aliases.get(raw_kind.strip().lower(), raw_kind.strip().lower())
        value = value.strip()
        if kind not in kinds:
            raise ValueError(
                f"词头规则第 {line_number} 行类型不支持：{raw_kind.strip()}"
            )
        if not value:
            raise ValueError(f"词头规则第 {line_number} 行内容为空")
        compiled = None
        if kind.endswith("_regex"):
            try:
                compiled = re_module.compile(value, re_module.UNICODE | re_module.IGNORECASE)
            except re_module.error as exc:
                raise ValueError(
                    f"词头规则第 {line_number} 行正则无效：{exc}"
                ) from exc
        rules.append(rule_cls(
            kind=kind, value=value, line_number=line_number, source=source, regex=compiled,
        ))
    return rules


def load_headword_filter_rules(
    path: Path | None, *, parse_fn: Callable[..., list[HeadwordFilterRule]],
) -> list[HeadwordFilterRule]:
    if path is None or not path.exists():
        return []
    return parse_fn(path.read_text(encoding="utf-8-sig"), str(path))


def rule_matches(
    rule: HeadwordFilterRule, *, raw_lemma: str, normalized_lemma: str,
    line_text: str, pos_text: str,
) -> bool:
    kind = rule.kind
    if "lemma" in kind:
        targets = (raw_lemma.strip(), normalized_lemma.strip())
        if kind.endswith("_exact"):
            wanted = rule.value.casefold()
            return any(target.casefold() == wanted for target in targets)
        assert rule.regex is not None
        return any(bool(rule.regex.search(target)) for target in targets)
    if "line" in kind:
        if kind.endswith("_contains"):
            return rule.value.casefold() in line_text.casefold()
        assert rule.regex is not None
        return bool(rule.regex.search(line_text))
    if kind.startswith("pos_exclude"):
        if kind.endswith("_exact"):
            return pos_text.strip().casefold() == rule.value.casefold()
        assert rule.regex is not None
        return bool(rule.regex.search(pos_text.strip()))
    return False


def evaluate_headword_filter_rules(
    rules: list[HeadwordFilterRule], *, raw_lemma: str, normalized_lemma: str,
    line_text: str, pos_text: str, match_fn: Callable[..., bool],
) -> dict[str, Any]:
    """Return reject/accept/POS-exclusion decisions with matched-rule details.

    Precedence is deterministic: explicit reject > explicit accept.  POS exclusion
    only removes the POS cue and then lets ordinary structural/visual scoring run.
    """
    result: dict[str, Any] = {
        "rejected": False, "accepted": False, "pos_excluded": False,
        "reject_rule": "", "accept_rule": "", "pos_exclude_rule": "",
    }
    for rule in rules:
        if not match_fn(
            rule, raw_lemma=raw_lemma, normalized_lemma=normalized_lemma,
            line_text=line_text, pos_text=pos_text,
        ):
            continue
        if rule.kind.startswith("reject_") and not result["reject_rule"]:
            result["rejected"] = True
            result["reject_rule"] = rule.display
        elif rule.kind.startswith("accept_") and not result["accept_rule"]:
            result["accepted"] = True
            result["accept_rule"] = rule.display
        elif rule.kind.startswith("pos_exclude") and not result["pos_exclude_rule"]:
            result["pos_excluded"] = True
            result["pos_exclude_rule"] = rule.display
    # A blacklist rule always wins over a force-accept rule.
    if result["rejected"]:
        result["accepted"] = False
    return result
