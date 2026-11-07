"""OCR grammar cue and profile-dependent regex compilation implementations.

Current regexp module, settings constructor, and modifier-stripper are passed at
call time by the historical core; no public patch seam is frozen at import.
"""
from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import AppSettings
    from ..profile.dictionary import DictionaryProfile


def compile_patterns(
    settings: AppSettings,
    profile: DictionaryProfile | None = None,
    *, regex_module: Any, settings_class: Any,
) -> tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]]:
    re = regex_module
    AppSettings = settings_class
    try:
        headword_regex = settings.paddle_headword_regex
        if (
            profile is not None and profile.uses_parser("latin")
            and headword_regex == AppSettings().paddle_headword_regex
        ):
            # Shared settings remain script-neutral for Arabic/Kana/custom
            # profiles. Latin profiles narrow only their own structural parser.
            latin_letter = r"[A-Za-z\u00C0-\u024F\u1E00-\u1EFF]"
            headword_regex = headword_regex.replace(r"[^\W\d_]", latin_letter)
        headword_pattern = re.compile(headword_regex, re.UNICODE | re.IGNORECASE)
        special_pattern = re.compile(settings.paddle_special_symbol_regex, re.UNICODE)
        pos_pattern = re.compile(
            profile.pos_regex() if profile is not None else settings.paddle_pos_regex,
            re.UNICODE | re.IGNORECASE,
        )
    except re.error as exc:
        raise ValueError(f"PaddleOCR 词头/词性正则表达式无效：{exc}") from exc
    return headword_pattern, special_pattern, pos_pattern


def strip_entry_modifiers(prefix: str, *, regex_module: Any) -> str:
    """Remove morphology/marker material allowed between lemma and a cue.

    This is intentionally grammar-oriented rather than lexicon-oriented.  It
    accepts the recurring dictionary shapes seen on pp.55-70: gender variants
    (`, da`, `, so·ra`), parenthetical forms, square markers and Roman section
    markers.  It also tolerates a truncated parenthesis at the OCR band edge.
    """
    re = regex_module
    value = prefix
    letter = r"[^\W\d_]"
    alt = rf"-?{letter}+(?:\s*[·•∙‧.:+\-]\s*{letter}+)*\.?"
    # Alternate forms and parenthetical morphology may occur in either order.
    for _ in range(4):
        before = value
        value = re.sub(
            rf"^\s*,\s*{alt}\s*",
            "", value, count=1, flags=re.UNICODE | re.IGNORECASE,
        )
        value = re.sub(
            r"^\s*\((?:pl|f|m|tb|masc|fem)\.?[^)]{0,100}\)\s*",
            "", value, count=1, flags=re.UNICODE | re.IGNORECASE,
        )
        if value == before:
            break
    # If OCR/cropping cut the closing parenthesis, regard the remainder as a
    # morphology note only when it begins with a known dictionary marker.
    value = re.sub(
        r"^\s*\((?:pl|f|m|tb|masc|fem)\.?[^)]{0,100}$",
        "", value, count=1, flags=re.UNICODE | re.IGNORECASE,
    )
    # Remove typography/section markers that commonly sit immediately before POS.
    value = re.sub(r"^[\s|/\[\]{}<>«»“”‘’\".,;:·•∙‧◆◇■□►▶*†‡§¶_+\-]+", "", value)
    value = re.sub(r"^(?:I{1,4}|IV|V)\b\s*", "", value, flags=re.IGNORECASE)
    return value


def find_pos_cue(
    tail: str, pos_pattern: re.Pattern[str], limit: int, *, allow_numeric_prefix: bool = False,
    regex_module: Any, strip_fn: Any,
) -> tuple[re.Match[str] | None, str]:
    """Find a POS label structurally attached to the headword.

    Returns ``(match, ignored_noise)``.  ``ignored_noise`` is a very short OCR
    artifact between lemma/gender form and POS (e.g. ``E`` in ``agua Es.f.``
    or ``Ml`` in ``agujeta Mls.f.``).  The allow-list is deliberately narrow so
    definition prose such as ``de s.m.`` is not mistaken for a grammatical cue.
    ``Pron. [..]`` is explicitly excluded because these pages use it for
    pronunciation, not the pronoun part of speech.
    """
    re = regex_module
    _strip_entry_modifiers = strip_fn
    snippet = tail[:max(8, limit)]
    noise_allow = {"e", "h", "l", "i", "li", "il", "ll", "ml", "m", "ii"}
    for match in pos_pattern.finditer(snippet):
        matched_text = match.group(0)
        # A tolerated missing period must still begin at a token boundary.
        # Otherwise bare ``s`` can be spuriously recovered from ordinary prose
        # such as ``es el agente`` by the narrow pre-POS noise heuristic.
        if (
            match.start() > 0
            and re.match(r"[^\W\d_]", snippet[match.start() - 1], flags=re.UNICODE)
            and "." not in matched_text
        ):
            continue
        # Dictionary pronunciation notes such as ``Pron. [érbag]`` are not POS.
        if matched_text.casefold().startswith("pron") and re.match(
            r"\s*\[", snippet[match.end():], flags=re.UNICODE
        ):
            continue
        lexical_end = match.start() + len(matched_text.rstrip())
        if lexical_end < len(snippet):
            next_char = snippet[lexical_end]
            if re.match(r"[^\W\d_]", next_char, flags=re.UNICODE):
                continue

        prefix = snippet[:match.start()]
        cleaned = _strip_entry_modifiers(prefix)
        cleaned = re.sub(r'[\s|/\[\]{}<>«»“”‘’".,;:·•∙‧◆◇■□►▶*†‡§¶_+\-]+', "", cleaned)
        cleaned = cleaned.replace("'", "")
        cleaned = re.sub(r"^(?:I{1,4}|IV|V)$", "", cleaned, flags=re.IGNORECASE)
        if allow_numeric_prefix:
            # Some classic Spanish dictionaries place a conjugation/index code
            # between lemma and POS, e.g. ``abalanzar 9 tr.`` or ``18,8 intr.``.
            cleaned = re.sub(r"^\d+(?:[,.]\d+)*(?:[-–/]\d+)*$", "", cleaned)
        if not re.search(r"[\w]", cleaned, flags=re.UNICODE):
            return match, ""
        # Only a tiny set of square-marker/glyph OCR artifacts may be ignored.
        # This fixes ``agua Es.f.``, ``aguar li v.``, ``agudizar lv.`` etc.
        folded = cleaned.casefold()
        if len(cleaned) <= 2 and folded in noise_allow and match.start() <= 12:
            return match, cleaned
        return None, ""
    return None, ""
