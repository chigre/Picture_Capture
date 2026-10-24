"""CJK symbol-boundary and bracketed lemma parsers for OCR records.

No regex/profile/model globals are initialized here. Historical public core
functions provide every live parsing dependency at call time.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import AppSettings
    from ..profile.dictionary import DictionaryProfile
    from ..paddle_headwords_core import HeadwordParse


def starts_with_unconfigured_headword_symbol(
    text: str,
    settings: AppSettings,
    profile: DictionaryProfile,
, *, inventory_fn: Any, symbol_families: Any, unicode_module: Any) -> bool:
    """Reject known symbol-led rows that are outside an explicitly saved set."""
    _configured_symbol_inventory = inventory_fn
    _SYMBOL_FAMILY_BY_LITERAL = symbol_families
    unicodedata = unicode_module
    if int(getattr(settings, "profile_symbol_inventory_version", 0) or 0) < 1:
        return False
    inventory = _configured_symbol_inventory(settings, profile)
    if not inventory.get("enabled", True):
        return False
    stripped = unicodedata.normalize("NFKC", str(text or "")).lstrip()
    if not stripped:
        return False
    configured = tuple(inventory["entry_markers"]) + tuple(inventory["bracket_openers"])
    if any(stripped.startswith(symbol) for symbol in configured if symbol):
        return False
    known = tuple(
        sorted(
            set(_SYMBOL_FAMILY_BY_LITERAL)
            | {"〓", "※", "*", "†", "‡", "§", "¶"},
            key=len,
            reverse=True,
        )
    )
    return any(stripped.startswith(symbol) for symbol in known)


def parse_cjk_marker_pinyin_headword(
    text: str, settings: AppSettings, profile: DictionaryProfile,
, *, is_chinese_fn: Any, repair_fn: Any, inventory_fn: Any,
    headword_cls: Any, regex_module: Any, unicode_module: Any,
) -> HeadwordParse | None:
    """Parse marker-led Chinese heads used by Chinese-foreign dictionaries.

    CNIT-like pages use a strong entry marker (○/●/〓) at the column left,
    followed by the Chinese lemma and usually pinyin/romanization.  The marker
    is intentionally mandatory here; geometry later provides the second guard.
    """
    _is_chinese_ocr = is_chinese_fn
    _repair_headword_ocr = repair_fn
    _configured_symbol_inventory = inventory_fn
    HeadwordParse = headword_cls
    re = regex_module
    unicodedata = unicode_module
    if not _is_chinese_ocr(settings):
        return None
    parse_text, repairs = _repair_headword_ocr(text)
    inventory = _configured_symbol_inventory(settings, profile)
    markers = tuple(
        sorted(
            dict.fromkeys(inventory["entry_markers"]),
            key=len,
            reverse=True,
        )
    )
    if not markers:
        return None
    marker_pattern = "|".join(re.escape(m) for m in markers)
    match = re.match(
        rf"^\s*(?P<marker>{marker_pattern})\s*(?P<lemma>[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff][\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaffA-Za-z0-9·-]{{0,23}})",
        parse_text,
        flags=re.UNICODE,
    )
    if not match:
        return None
    raw = match.group("lemma")
    normalized = unicodedata.normalize("NFKC", raw).strip()
    return HeadwordParse(
        raw=raw, normalized=normalized, has_pos=False, pos_text="",
        has_inflection=False, inflection_text="", has_descriptor=True,
        descriptor_text="cjk_marker_pinyin", match_end=max(1, match.end("lemma")),
        looks_like_continuation=False, continuation_reason="", corrected_raw=raw,
        parse_text=parse_text, ocr_repairs=tuple(repairs), variants=(), plural_text="",
        usage_text="", definition_text=parse_text[match.end("lemma"):].strip(),
        parser_stage="cjk_marker_pinyin",
        parser_trace=(f"entry_marker:{match.group('marker')}", "cjk_marker_pinyin"),
        bug_types=(),
    )


def parse_chinese_bracketed_headword(
    text: str,
    settings: AppSettings,
    *,
    enforce_chinese_language: bool = True,
    allow_japanese_reading_prefix: bool = False,
    allowed_openers: tuple[str, ...] | None = None,
, *, is_chinese_fn: Any, repair_fn: Any, headword_cls: Any,
    bracket_closers: Any, regex_module: Any, unicode_module: Any,
) -> HeadwordParse | None:
    """Parse complete or line-wrapped Chinese bracket headwords.

    Supported examples include ``【一刀】``, ``〔一刀〕``, ``[一刀]`` and the
    first physical line of a long wrapped entry such as ``【很長的詞頭……``.
    Some scans/OCR segmentations can even leave the first OCR row as only the
    opening marker ``【``; at the column left edge that marker is still a strong
    dictionary-entry boundary and must be allowed to produce a separator line.

    The parser itself only recognizes the structural marker.  The later
    candidate filter still requires the row to be in the column entry zone
    (left-aligned, below the header, not an internal relation label), which is
    the main protection against ordinary brackets inside definitions.
    """
    _is_chinese_ocr = is_chinese_fn
    _repair_headword_ocr = repair_fn
    HeadwordParse = headword_cls
    _BRACKET_CLOSER_BY_OPENER = bracket_closers
    re = regex_module
    unicodedata = unicode_module
    if enforce_chinese_language and not _is_chinese_ocr(settings):
        return None
    parse_text, repairs = _repair_headword_ocr(text)

    # Chinese profiles require a configured bracket at the physical line
    # start. Japanese profiles may prepend a short kana reading such as
    # "あい【愛】"; that prefix is entry metadata, not part of the lemma.
    openers = tuple(
        sorted(
            dict.fromkeys(
                allowed_openers
                or ("【", "〔", "［", "[", "「", "『", "〈", "《")
            ),
            key=len,
            reverse=True,
        )
    )
    if not openers:
        return None
    opener_pattern = "|".join(re.escape(value) for value in openers)
    reading_prefix = ""
    if allow_japanese_reading_prefix:
        opener = re.match(
            rf"^\s*(?:(?P<reading>[\u3040-\u30ff\u31f0-\u31ffー・･]{{1,12}})\s*)?"
            rf"(?P<opening>{opener_pattern})\s*(?P<remainder>.*)$",
            parse_text,
            flags=re.UNICODE,
        )
        if opener:
            reading_prefix = str(opener.group("reading") or "")
    else:
        opener = re.match(
            rf"^\s*(?P<opening>{opener_pattern})\s*(?P<remainder>.*)$",
            parse_text,
            flags=re.UNICODE,
        )
    if not opener:
        return None

    opening = opener.group("opening")
    remainder = opener.group("remainder").rstrip()
    configured_closer = _BRACKET_CLOSER_BY_OPENER.get(opening)
    close_match = (
        re.search(re.escape(configured_closer), remainder, flags=re.UNICODE)
        if configured_closer
        else re.search(r"[】〕］\]」』〉》]", remainder, flags=re.UNICODE)
    )
    is_closed = close_match is not None

    if is_closed:
        assert close_match is not None
        raw_inner = remainder[:close_match.start()].strip()
        # Be generous for long phrase/idiom entries.  The closing marker gives
        # us a reliable boundary, so a wider limit is safe here.
        if not raw_inner or len(raw_inner) > 64:
            return None
        match_end = opener.start("remainder") + close_match.end()
        definition_text = remainder[close_match.end():].lstrip()
        descriptor = "chinese_bracketed_headword"
        parser_stage = "chinese_bracketed_headword"
        raw_value = raw_inner
    else:
        # A missing closer is expected when the printed headword wraps to the
        # next line.  Do not swallow arbitrary amounts of body text: only the
        # current OCR row is used, with a conservative maximum length.  A lone
        # opening bracket is also accepted as an entry-start marker.
        raw_inner = remainder.strip()
        if len(raw_inner) > 48:
            raw_inner = raw_inner[:48].rstrip()
        descriptor = "chinese_open_bracket_headword"
        parser_stage = "chinese_open_bracket_headword"
        match_end = len(parse_text)
        definition_text = ""
        raw_value = raw_inner if raw_inner else opening
        repairs = list(repairs) + ["accepted_unclosed_chinese_headword_bracket"]

    # Remove OCR-inserted spaces between CJK characters but preserve meaningful
    # spaces in mixed-script entries.  For a marker-only row keep the opening
    # bracket as the temporary lemma so the row remains selectable/reviewable.
    normalized = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", raw_inner)
    normalized = unicodedata.normalize("NFKC", normalized).strip()
    if not normalized:
        normalized = opening

    return HeadwordParse(
        raw=raw_value,
        normalized=normalized,
        has_pos=False,
        pos_text="",
        has_inflection=False,
        inflection_text="",
        has_descriptor=True,
        descriptor_text=descriptor,
        match_end=max(1, match_end),
        looks_like_continuation=False,
        continuation_reason="",
        corrected_raw=raw_value,
        parse_text=parse_text,
        ocr_repairs=tuple(repairs),
        variants=(),
        plural_text="",
        usage_text="",
        definition_text=definition_text,
        parser_stage=parser_stage,
        parser_trace=(
            (f"japanese_reading_prefix:{reading_prefix}", parser_stage)
            if reading_prefix else (parser_stage,)
        ),
        bug_types=(),
    )
