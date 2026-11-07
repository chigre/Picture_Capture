from __future__ import annotations

"""Length-preserving OCR lemma repair without engine or cache initialization."""

from typing import Any
import re


def repair_headword_ocr(
    text: str, *, re_module: Any = re,
) -> tuple[str, tuple[str, ...]]:
    """Conservatively repair OCR confusions inside the initial lemma.

    The repair keeps string length unchanged so the exact OCR spelling can still
    be sliced for diagnostics.  Besides internal 0/6->o and 1->i confusions, a
    final suspicious digit may be repaired when it is immediately followed by a
    clear dictionary POS label (e.g. ``a-ho.g0 s.m.`` -> ``a-ho.go s.m.``).
    Definition numbering remains untouched.
    """
    chars = list(text)
    repairs: list[str] = []
    separators = set("·•∙‧.:-+'’")

    def is_letter(ch: str) -> bool:
        return bool(ch and re_module.match(r"[^\W\d_]", ch, flags=re_module.UNICODE))

    hard_stop = len(chars)
    for i, ch in enumerate(chars):
        if ch.isspace():
            prev = chars[i - 1] if i else ""
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
            if prev not in separators and nxt not in separators:
                hard_stop = i
                break

    mapping = {"0": "o", "6": "o", "1": "i"}
    for i in range(1, max(1, hard_stop - 1)):
        ch = chars[i]
        replacement = mapping.get(ch)
        if not replacement:
            continue
        prev = chars[i - 1]
        nxt = chars[i + 1]
        left_ok = is_letter(prev) or prev in separators
        right_ok = is_letter(nxt) or nxt in separators
        if left_ok and right_ok:
            chars[i] = replacement
            repairs.append(f"{ch}->{replacement}@{i}")

    # Terminal digit confusion: only when the remaining text begins with a
    # strong POS cue, so entry sense numbers such as "... 1 Que" are untouched.
    last = hard_stop - 1
    if 0 < last < len(chars) and chars[last] in mapping:
        tail = text[hard_stop:]
        if re_module.match(
            r"\s+(?:s\.|adj\.?|adv\.?|[vy]\.|prep\.?|pron\.?|interj\.?|art\.?|num\.?|loc\.?|superlat\.?)",
            tail,
            flags=re_module.UNICODE | re_module.IGNORECASE,
        ):
            prev = chars[last - 1]
            if is_letter(prev) or prev in separators:
                old = chars[last]
                chars[last] = mapping[old]
                repairs.append(f"{old}->{mapping[old]}@{last}(terminal)")

    return "".join(chars), tuple(repairs)

