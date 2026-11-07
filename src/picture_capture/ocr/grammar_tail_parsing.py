from __future__ import annotations

"""Memory-only grammar-tail parsing and narrow dictionary OCR recovery.

The historic Paddle headword core injects live POS finder, morphology-strip,
cursor, usage-label inventory and GrammarTailParse constructor. This module
does not alter final candidate decisions, persistence, or model identities.
"""

from collections.abc import Callable, Collection
from typing import Any
import re
from .headword_models import GrammarTailParse


def leading_inflection_cue(tail: str, *, re_module: Any = re) -> tuple[bool, str]:
    """Recognize leading morphology notes, including cropped/unclosed notes."""
    leading = tail.lstrip()
    if not re_module.match(r"^\((?:pl|f|m|tb|masc|fem)\.?\b", leading, flags=re_module.I | re_module.UNICODE):
        return False, ""
    # Diagnostics only: keep a bounded readable prefix.  The cue remains valid
    # even if the closing ')' lies beyond the OCR band.
    text = leading[:140].strip()
    return True, text


def parallel_marker_extension(
    tail: str, *, re_module: Any = re,
) -> tuple[str, int, bool, str]:
    """Return (extra_headword, consumed_chars, has_parallel_descriptor, label).

    Some entries have no POS and are introduced by a parallel-expression marker:
    ``air mail || Correo aéreo``, ``ajillo || al ~`` or OCR variants where ``||``
    becomes ``ll``.  For the two-word cases, include the second bold token in the
    lemma; for a marker immediately after the lemma, only provide a structural cue.
    """
    letter = r"[^\W\d_]"
    token = rf"-?{letter}+(?:[·•∙‧.:+\-]{letter}+)*-?"
    # Clear double bar: safe enough to treat as a dictionary parallel marker.
    m = re_module.match(rf"^\s+(?P<extra>{token})\s+(?P<mark>\|\|)\s*", tail, flags=re_module.UNICODE)
    if m:
        return m.group("extra"), m.end("extra"), True, "parallel_gloss"
    if re_module.match(r"^\s*\|\|\s*", tail):
        return "", 0, True, "parallel_gloss"

    # OCR often renders the two vertical bars as ll / |l / l|.  Require a nearby
    # tilde placeholder or a hyphenated cross-reference so ordinary 'll' text is
    # not promoted to a structural cue.
    m = re_module.match(
        rf"^\s+(?P<extra>{token})\s+(?P<mark>ll|\|l|l\|)\s+(?P<after>[^;:]{{0,18}}(?:~|-[^\s;:]+))",
        tail, flags=re_module.UNICODE | re_module.IGNORECASE,
    )
    if m:
        return m.group("extra"), m.end("extra"), True, "parallel_gloss_ocr"
    if re_module.match(r"^\s*(?:ll|\|l|l\|)\s+[^;:]{0,18}(?:~|-[^\s;:]+)", tail, flags=re_module.I | re_module.UNICODE):
        return "", 0, True, "parallel_gloss_ocr"
    return "", 0, False, ""


def consume_leading_space(text: str, cursor: int) -> int:
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    return cursor


def parse_structured_tail(
    tail: str,
    pos_pattern: re.Pattern[str],
    search_limit: int,
    *,
    parallel_descriptor: bool = False,
    parallel_label: str = "",
    allow_numeric_prefix: bool = False,
    consume_space_fn: Callable[[str, int], int],
    find_pos_fn: Callable[..., Any],
    strip_fn: Callable[[str], str],
    usage_abbreviations: Collection[str],
    grammar_cls: type,
    re_module: Any = re,
) -> GrammarTailParse:
    """Parse the grammar tail as an ordered state machine.

    Stages are intentionally narrow and deterministic:
    variants -> morphology/inflection -> pronunciation -> POS -> usage -> definition.
    This turns the parser into an inspectable grammar pipeline while retaining
    small regexes only for individual token classes.
    """
    cursor = 0
    variants: list[str] = []
    inflections: list[str] = []
    trace: list[str] = ["lemma:ok"]
    stage = "variants"
    letter = r"[^\W\d_]"
    # Gender/alternate form such as `, da`, `, so·ra`, `, ria`.
    variant_re = re_module.compile(
        rf"\s*,\s*(?P<v>-?{letter}+(?:\s*[·•∙‧.:+\-]\s*{letter}+)*\.?)",
        flags=re_module.UNICODE | re_module.IGNORECASE,
    )
    # Morphology notes; closing ')' may be absent because the OCR candidate band
    # ended before it. We therefore accept a bounded open form as a recovery.
    closed_inflection_re = re_module.compile(
        r"\s*(?P<i>\((?:pl|f|m|tb|masc|fem)\.?[^)]{0,120}\))",
        flags=re_module.UNICODE | re_module.IGNORECASE,
    )
    open_inflection_re = re_module.compile(
        r"\s*(?P<i>\((?:pl|f|m|tb|masc|fem)\.?[^)]{0,120})$",
        flags=re_module.UNICODE | re_module.IGNORECASE,
    )

    # Variant/inflection order varies across dictionary entries, so iterate.
    for _ in range(6):
        cursor = consume_space_fn(tail, cursor)
        rest = tail[cursor:]
        vm = variant_re.match(rest)
        if vm:
            value = vm.group("v").strip()
            variants.append(value)
            cursor += vm.end()
            trace.append(f"variant:{value}")
            continue
        im = closed_inflection_re.match(rest)
        if im:
            value = im.group("i").strip()
            inflections.append(value)
            cursor += im.end()
            trace.append(f"inflection:{value}")
            continue
        om = open_inflection_re.match(rest)
        if om:
            value = om.group("i").strip()
            inflections.append(value)
            cursor += om.end()
            trace.append(f"inflection_open:{value}")
            continue
        break

    # Pronunciation is grammar metadata, not definition prose.  Consume common
    # bracket/slash IPA forms before looking for POS; tolerate a missing closing
    # delimiter at a cropped OCR-band edge.
    cursor = consume_space_fn(tail, cursor)
    pos_ahead = r"(?=\s+(?:n|v|adj|adv|prep|conj|pron|interj|art|num)\.)"
    pronunciation_re = re_module.compile(
        rf"(?:\[[^\]]{{1,180}}(?:\]|{pos_ahead})|/[^/]{{1,180}}(?:/|{pos_ahead}))",
        flags=re_module.UNICODE | re_module.IGNORECASE,
    )
    pronunciation_match = pronunciation_re.match(tail[cursor:])
    if pronunciation_match:
        pronunciation = pronunciation_match.group(0).strip()
        cursor += pronunciation_match.end()
        trace.append(f"pronunciation:{pronunciation}")

    # Consume typography/section markers that may separate pronunciation and POS.
    cursor = consume_space_fn(tail, cursor)
    marker_match = re_module.match(
        r"[|{}<>«»“”‘’\".,;:·•∙‧◆◇■□►▶*†‡§¶_+\-\s]*(?:I{1,4}|IV|V)?\s*",
        tail[cursor:], flags=re_module.UNICODE,
    )
    if marker_match and marker_match.end() > 0:
        consumed_marker = marker_match.group(0)
        if consumed_marker.strip():
            trace.append(f"marker:{consumed_marker.strip()}")
        cursor += marker_match.end()

    stage = "pos"
    pos_text = ""
    pos_noise = ""
    # Prefer a POS beginning near the current grammar cursor. `_find_pos_cue`
    # already has the narrow glyph-noise recovery used by the existing parser.
    pos_match, pos_noise = find_pos_fn(
        tail[cursor:], pos_pattern, search_limit, allow_numeric_prefix=allow_numeric_prefix,
    )
    if pos_match is not None:
        prefix_len = pos_match.start()
        # If _find_pos_cue tolerated a tiny OCR glyph noise, absorb it here.
        cursor += pos_match.end()
        pos_text = pos_match.group(0).strip()
        trace.append(f"pos:{pos_text}")
        if pos_noise:
            trace.append(f"pos_noise:{pos_noise}")
    else:
        trace.append("pos:none")

    # Descriptor entries can legitimately omit a conventional POS.
    descriptor_text = ""
    descriptor_start = cursor if pos_text else consume_space_fn(tail, cursor)
    descriptor_source = strip_fn(tail[descriptor_start:descriptor_start + max(100, search_limit)])
    descriptor_match = re_module.match(
        r"(elemento\s+compositivo|forma\s+prefija|forma\s+sufija|"
        r"prefijo(?:\s+que)?|sufijo(?:\s+que)?|sigla\s+de|abreviatura\s+de|"
        r"acr[oó]nimo\s+de|contracci[oó]n\s+de)",
        descriptor_source,
        flags=re_module.UNICODE | re_module.IGNORECASE,
    )
    if descriptor_match:
        descriptor_text = descriptor_match.group(1).strip()
        trace.append(f"descriptor:{descriptor_text}")
    elif parallel_descriptor:
        descriptor_text = parallel_label
        trace.append(f"descriptor:{parallel_label}")

    # Usage/register abbreviations occur immediately after POS and before sense 1
    # or normal definition prose. They are optional metadata, not an acceptance
    # requirement. Parse a short run so diagnostics can expose them.
    stage = "usage"
    usage_parts: list[str] = []
    usage_cursor = cursor
    for _ in range(5):
        usage_cursor = consume_space_fn(tail, usage_cursor)
        m = re_module.match(r"(?P<u>[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,12})\.\s*", tail[usage_cursor:], flags=re_module.UNICODE)
        if not m:
            break
        token = m.group("u")
        if token.casefold().rstrip(".") not in usage_abbreviations:
            break
        usage_parts.append(token + ".")
        usage_cursor += m.end()
    if usage_parts:
        cursor = usage_cursor
        trace.append("usage:" + " ".join(usage_parts))
    usage_text = " ".join(usage_parts)

    stage = "definition"
    definition = tail[cursor:].strip()
    if definition:
        trace.append("definition:present")
    else:
        trace.append("definition:empty")
    return grammar_cls(
        variants=tuple(variants),
        inflections=tuple(inflections),
        pos_text=pos_text,
        usage_text=usage_text,
        descriptor_text=descriptor_text,
        definition_text=definition,
        consumed=cursor,
        stage=stage,
        trace=tuple(trace),
    )


def parse_bug_types(
    repairs: tuple[str, ...], grammar: GrammarTailParse, continuation_reason: str,
) -> tuple[str, ...]:
    bugs: list[str] = []
    for repair in repairs:
        if repair.startswith("reassigned_trailing_punctuation:,"):
            bugs.append("COMMA_SWALLOWED")
        if repair.startswith("joined_detached_lemma_suffix") or repair.startswith("split_attached_pos"):
            bugs.append("SPLIT_HEADWORD")
        if repair.startswith("ignored_pre_pos_noise"):
            bugs.append("POS_GLYPH_NOISE")
        if "6->o" in repair or "0->o" in repair or "1->i" in repair or "l->i" in repair:
            bugs.append("OCR_CHARACTER_REPAIR")
    if continuation_reason:
        bugs.append("CONTINUATION_FRAGMENT")
    # preserve order, remove duplicates
    return tuple(dict.fromkeys(bugs))
