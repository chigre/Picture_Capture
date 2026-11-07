"""OCR line headword parser; full implementation with runtime callback binding.

Keep previous core/public signatures, nested script-selectors and parser models
unmoved. Legacy regex, grammatical parsing and OCR repairs remain unmodified.
"""
from __future__ import annotations
import re
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import AppSettings
    from ..profile.dictionary import DictionaryProfile
    from .headword_models import HeadwordParse


def parse_headword_text_impl(
    text: str,
    settings: AppSettings,
    patterns: tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]] | None = None,
    profile: DictionaryProfile | None = None,
    *,
    deps: dict[str, Any],
) -> HeadwordParse | None:
    """Extract and normalize a lemma from one merged OCR line.

    The parser deliberately hardens itself against a project carrying an older
    user regex.  If that regex swallows the grammatical comma/terminal period,
    punctuation is moved back into the tail before structural parsing.  This is
    what recovers the large family of `lemma, da adj.` misses seen on pp.55-70.
    """
    _BUNDLED_PROFILE = deps["_BUNDLED_PROFILE"]
    _configured_symbol_inventory = deps["_configured_symbol_inventory"]
    _parse_chinese_bracketed_headword = deps["_parse_chinese_bracketed_headword"]
    _is_chinese_ocr = deps["_is_chinese_ocr"]
    _parse_cjk_single_with_pinyin = deps["_parse_cjk_single_with_pinyin"]
    _parse_cjk_marker_pinyin_headword = deps["_parse_cjk_marker_pinyin_headword"]
    _is_japanese_ocr = deps["_is_japanese_ocr"]
    _parse_chinese_single_character_headword = deps["_parse_chinese_single_character_headword"]
    _starts_with_unconfigured_headword_symbol = deps["_starts_with_unconfigured_headword_symbol"]
    _compile_patterns = deps["_compile_patterns"]
    _repair_headword_ocr = deps["_repair_headword_ocr"]
    _parallel_marker_extension = deps["_parallel_marker_extension"]
    normalize_headword = deps["normalize_headword"]
    _parse_structured_tail = deps["_parse_structured_tail"]
    _parse_bug_types = deps["_parse_bug_types"]
    HeadwordParse = deps["HeadwordParse"]
    active_profile = profile or _BUNDLED_PROFILE
    parser_controls = int(
        getattr(settings, "profile_parser_controls_version", 0) or 0
    ) >= 1
    allow_numbered = (
        bool(getattr(settings, "profile_allow_numbered_prefix", False))
        if parser_controls else active_profile.uses_parser("numbered_headword_prefix")
    )
    allow_marker = (
        bool(getattr(settings, "profile_allow_marker_prefix", False))
        if parser_controls else active_profile.uses_parser("cjk_marker_pinyin")
    )
    allow_bracketed = (
        bool(getattr(settings, "profile_cjk_allow_bracketed_headword", True))
        if parser_controls else active_profile.uses_parser("cjk_bracketed")
    )
    allow_single = (
        bool(getattr(settings, "profile_cjk_allow_single_headword", True))
        if parser_controls else active_profile.uses_parser("cjk_single_visual")
    )
    allow_ordinary = (
        bool(getattr(settings, "profile_allow_ordinary_left_edge", True))
        if parser_controls else True
    )

    numbered_prefix_matched = False
    if allow_numbered:
        prefix_pattern = active_profile.prefix_regex or r"^\s*\d{1,4}(?:\s*[.．]\s*|\s+)"
        try:
            prefix = re.match(prefix_pattern, text, flags=re.UNICODE)
        except re.error:
            prefix = None
        if prefix is not None:
            numbered_prefix_matched = True
            text = text[prefix.end():]
            text = re.sub(r"^\s*[.．]\s*", "", text, count=1)
            bracket_inventory = _configured_symbol_inventory(
                settings, active_profile
            )
            bracketed = _parse_chinese_bracketed_headword(
                text,
                settings,
                enforce_chinese_language=False,
                allowed_openers=tuple(bracket_inventory["bracket_openers"]),
            )
            if bracketed is not None:
                return bracketed
        elif not parser_controls and active_profile.prefix_required:
            return None

    # Direct parser calls made by older code/tests remain language-driven. The
    # full OCR pipeline now passes an explicit profile and, after Wizard setup,
    # the user-facing structure checkboxes become authoritative.
    legacy_language_driven_cjk = (
        not parser_controls and profile is None and _is_chinese_ocr(settings)
    )
    features = set(active_profile.headword_features)
    if allow_single and "pinyin_after_headword" in features:
        cjk_pinyin = _parse_cjk_single_with_pinyin(text, settings)
        if cjk_pinyin is not None:
            return cjk_pinyin
    if allow_marker:
        cjk_marker = _parse_cjk_marker_pinyin_headword(text, settings, active_profile)
        if cjk_marker is not None:
            return cjk_marker
    if legacy_language_driven_cjk or (
        allow_bracketed
        and (parser_controls or "bracketed_compound" in features)
    ):
        explicit_cjk_profile = bool(
            profile is not None and active_profile.family == "cjk_visual"
        )
        bracket_inventory = _configured_symbol_inventory(
            settings, active_profile
        )
        chinese = _parse_chinese_bracketed_headword(
            text,
            settings,
            enforce_chinese_language=not explicit_cjk_profile,
            allow_japanese_reading_prefix=(
                explicit_cjk_profile and _is_japanese_ocr(settings)
            ),
            allowed_openers=tuple(bracket_inventory["bracket_openers"]),
        )
        if chinese is not None:
            return chinese
    if legacy_language_driven_cjk or (
        allow_single
        and (parser_controls or "large_single_character" in features)
    ):
        chinese_single = _parse_chinese_single_character_headword(text, settings)
        if chinese_single is not None:
            return chinese_single

    # A Project Profile with an explicit symbol inventory is exact: a row
    # starting with a known-but-unconfigured headword symbol must not silently
    # fall through to the generic lemma parser after that symbol is skipped.
    if _starts_with_unconfigured_headword_symbol(text, settings, active_profile):
        return None

    # The generic lemma parser is the "普通左缘短词" structure. A numbered
    # prefix is also allowed to continue through it because the prefix itself
    # already supplied the strong structural cue.
    if parser_controls and not allow_ordinary and not numbered_prefix_matched:
        return None
    compile_profile = None if legacy_language_driven_cjk and profile is None else active_profile
    headword_pattern, _special_pattern, pos_pattern = patterns or _compile_patterns(settings, compile_profile)
    parse_text, repairs = _repair_headword_ocr(text)
    match = headword_pattern.search(parse_text)
    if not match:
        return None

    group_index = 1 if match.lastindex else 0
    group_start, group_end = match.span(group_index)
    corrected_raw = match.group(group_index).strip()
    if not corrected_raw:
        return None
    raw = text[group_start:group_end].strip()

    # An overly permissive legacy regex may interpret sentence punctuation as a
    # syllable dot and swallow the following grammatical label, e.g.
    # ``mail. Pron.`` or ``hólica. adj.``. Cut at that boundary before any other
    # parsing. Real ASCII syllable dots in this dictionary do not have a space
    # before a POS/pronunciation label.
    grammar_boundary = re.search(
        r"\.\s+(?=(?:s\.?\b|adj\.?\b|adv\.?\b|[vy]\.\b|prep\.?\b|"
        r"conj\.?\b|pron\.?\b|interj\.?\b|art\.?\b|num\.?\b|loc\.?\b|"
        r"superlat\.?\b))",
        corrected_raw, flags=re.UNICODE | re.IGNORECASE,
    )
    boundary_tail = ""
    if grammar_boundary:
        cut = grammar_boundary.start()
        absolute_cut = group_start + cut
        corrected_raw = corrected_raw[:cut].rstrip()
        raw = text[group_start:absolute_cut].strip()
        group_end = absolute_cut
        boundary_tail = parse_text[absolute_cut:match.span(group_index)[1]]
        repairs = tuple(list(repairs) + ["split_sentence_dot_before_grammar_label"])

    # Legacy/custom regexes may absorb punctuation that belongs to the grammar
    # tail. Reassign it before POS/gender parsing. A trailing period then becomes
    # a continuation-fragment signal, which also removes false positives such as
    # ``mail. Pron. [...]`` / ``hólica. adj./s. 2``.
    reassigned = ""
    while corrected_raw and corrected_raw[-1] in ",.;:!?…":
        punct = corrected_raw[-1]
        corrected_raw = corrected_raw[:-1].rstrip()
        if raw.endswith(punct):
            raw = raw[:-1].rstrip()
        group_end -= 1
        reassigned = punct + reassigned
        repairs = tuple(list(repairs) + [f"reassigned_trailing_punctuation:{punct}"])
        # A single punctuation mark is enough in these dictionary heads.
        break

    tail = reassigned + boundary_tail + parse_text[match.span(group_index)[1]:]

    # OCR can glue the verb label directly to the lemma: ``a·guan·tarv.``.
    # Splitting only a terminal 'v' before '. + sense/definition' is narrow and
    # avoids damaging ordinary Spanish words ending in s.
    if re.match(r"^\.\s*(?:\d|[A-ZÁÉÍÓÚÜÑ])", tail, flags=re.UNICODE) and re.search(
        r"[^\W\d_]v$", corrected_raw, flags=re.I | re.UNICODE
    ):
        corrected_raw = corrected_raw[:-1]
        if raw and raw[-1].casefold() == "v":
            raw = raw[:-1]
        group_end -= 1
        tail = " v" + tail
        repairs = tuple(list(repairs) + ["split_attached_pos:v"])

    # OCR occasionally replaces the final syllable dot with a space, e.g.
    # ``ai·re ar v.``.  Only join canonical infinitive endings immediately before
    # a verb label; this does not collide with comma-led gender variants.
    suffix_match = re.match(r"^\s+(ar|er|ir|se)\s+(?=v\.\b|v\.\s)", tail, flags=re.I | re.UNICODE)
    if suffix_match and re.search(r"[·•∙‧.:+\-]", corrected_raw):
        suffix = suffix_match.group(1)
        corrected_raw += suffix
        raw = f"{raw} {suffix}"
        tail = tail[suffix_match.end(1):]
        group_end += suffix_match.end(1)
        repairs = tuple(list(repairs) + [f"joined_detached_lemma_suffix:{suffix}"])

    # Parallel-expression entries may contain one additional bold token before
    # ||/ll. Extend the lemma only under this very specific structural pattern.
    extra, consumed, parallel_descriptor, parallel_label = _parallel_marker_extension(tail)
    if extra:
        corrected_raw = f"{corrected_raw} {extra.strip()}"
        raw = f"{raw} {extra.strip()}"
        tail = tail[consumed:]
        group_end += consumed
        repairs = tuple(list(repairs) + [f"joined_parallel_headword:{extra.strip()}"])

    normalized = normalize_headword(corrected_raw, settings.paddle_remove_syllable_separators)
    if settings.lowercase_ocr:
        normalized = normalized.lower()

    stripped_tail = tail.lstrip()
    continuation_reason = ""
    if stripped_tail.startswith((".", ";", ":", "!", "?", "…")):
        continuation_reason = "terminal_punctuation_immediately_after_candidate"

    grammar = _parse_structured_tail(
        tail, pos_pattern, settings.paddle_pos_search_chars,
        parallel_descriptor=parallel_descriptor, parallel_label=parallel_label,
        allow_numeric_prefix=active_profile.uses_parser("numbered_pos"),
    )
    # Keep the legacy POS-noise repair label because existing diagnostics/tests
    # consume it. The structured parser exposes the same event in parser_trace.
    for trace_item in grammar.trace:
        if trace_item.startswith("pos_noise:"):
            repairs = tuple(list(repairs) + [f"ignored_pre_pos_noise:{trace_item.split(':', 1)[1]}"])
            break

    inflection_text = " ".join(grammar.inflections).strip()
    bugs = _parse_bug_types(repairs, grammar, continuation_reason)

    return HeadwordParse(
        raw=raw,
        normalized=normalized,
        has_pos=bool(grammar.pos_text),
        pos_text=grammar.pos_text,
        has_inflection=bool(grammar.inflections),
        inflection_text=inflection_text,
        has_descriptor=bool(grammar.descriptor_text),
        descriptor_text=grammar.descriptor_text,
        match_end=max(group_start + 1, group_end),
        looks_like_continuation=bool(continuation_reason),
        continuation_reason=continuation_reason,
        corrected_raw=corrected_raw,
        parse_text=parse_text,
        ocr_repairs=repairs,
        variants=grammar.variants,
        plural_text=inflection_text,
        usage_text=grammar.usage_text,
        definition_text=grammar.definition_text,
        parser_stage=grammar.stage,
        parser_trace=grammar.trace,
        bug_types=bugs,
    )

def looks_like_marker_noise_lemma(parsed: HeadwordParse | None, *, regex_module: Any) -> bool:
    """Reject only very narrow square/bullet OCR artifacts used as fake lemmas.

    Examples observed on these pages include ``Ml adj./s.`` where the printed
    square marker was OCRed as two letters.  Real short acronym entries normally
    carry a descriptor such as ``Sigla de`` and therefore are not covered here.
    """
    re = regex_module
    if not parsed or parsed.has_descriptor or parsed.has_inflection:
        return False
    compact = re.sub(r"[^A-Za-z]", "", parsed.raw).casefold()
    return compact in {"ml", "ll", "il", "ii", "l"}
