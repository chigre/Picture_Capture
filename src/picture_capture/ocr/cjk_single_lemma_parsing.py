"""Single-Han CJK visual lemma and following-pinyin parsing.

Only implementation functions move; the core retains compiled regular
expressions, HeadwordParse's historical class identity and patchable helpers.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import AppSettings
    from ..paddle_headwords_core import HeadwordParse


def parse_cjk_single_with_pinyin(text: str, settings: AppSettings, *, is_chinese_fn: Any, repair_fn: Any,
    single_pinyin_re: Any, visual_headword_fn: Any,
) -> HeadwordParse | None:
    """Recognize a single CJK head followed by optional star and pinyin."""
    _is_chinese_ocr = is_chinese_fn
    _repair_headword_ocr = repair_fn
    _CJK_SINGLE_PINYIN_RE = single_pinyin_re
    _make_chinese_visual_headword = visual_headword_fn
    if not _is_chinese_ocr(settings):
        return None
    parse_text, repairs = _repair_headword_ocr(text)
    match = _CJK_SINGLE_PINYIN_RE.match(parse_text)
    if not match:
        return None
    result = _make_chinese_visual_headword(
        match.group("head"), parse_text, tuple(repairs), stage="cjk_single_with_pinyin",
    )
    result.descriptor_text = "cjk_single_with_pinyin"
    result.definition_text = parse_text[match.end():].strip()
    result.parser_trace = ("feature:pinyin_after_headword", f"pinyin:{match.group('pinyin')}")
    return result


def make_chinese_visual_headword(raw: str, parse_text: str, repairs: tuple[str, ...], *, stage: str, unicode_module: Any, headword_cls: Any) -> HeadwordParse:
    unicodedata = unicode_module
    HeadwordParse = headword_cls
    normalized = unicodedata.normalize("NFKC", raw).strip()
    return HeadwordParse(
        raw=raw,
        normalized=normalized,
        has_pos=False,
        pos_text="",
        has_inflection=False,
        inflection_text="",
        has_descriptor=True,
        descriptor_text="chinese_single_character_visual",
        match_end=max(1, len(raw)),
        looks_like_continuation=False,
        continuation_reason="",
        corrected_raw=raw,
        parse_text=parse_text,
        ocr_repairs=repairs,
        variants=(),
        plural_text="",
        usage_text="",
        definition_text="",
        parser_stage=stage,
        parser_trace=(stage,),
        bug_types=(),
    )


def parse_chinese_single_character_headword(text: str, settings: AppSettings, *, is_chinese_fn: Any, repair_fn: Any,
    is_ideograph_fn: Any, visual_headword_fn: Any, radical_section_re: Any,
    regex_module: Any, unicode_module: Any,
) -> HeadwordParse | None:
    """Parse an unbracketed one-character Chinese dictionary head.

    Character dictionaries commonly mix two entry families on the same page:
    large single-character heads (e.g. 系 / 刑 / 正) and ordinary-size
    bracketed compounds (e.g. 【並世】).  The single-character parse is only a
    *visual candidate*; geometry/size gates in ``filter_headword_records`` must
    still confirm that the glyph is significantly larger than body text.
    Consequently an ordinary body line that happens to contain one Han
    character does not become an entry merely because it can be parsed.
    """
    _is_chinese_ocr = is_chinese_fn
    _repair_headword_ocr = repair_fn
    _is_single_cjk_ideograph = is_ideograph_fn
    _make_chinese_visual_headword = visual_headword_fn
    _CJK_RADICAL_SECTION_RE = radical_section_re
    re = regex_module
    unicodedata = unicode_module
    if not _is_chinese_ocr(settings):
        return None
    parse_text, repairs = _repair_headword_ocr(text)
    compact = unicodedata.normalize("NFKC", parse_text).strip()
    if _is_single_cjk_ideograph(compact):
        return _make_chinese_visual_headword(compact, parse_text, tuple(repairs), stage="chinese_single_character")

    # Some OCR engines merge a large display character with one or two nearby
    # variant glyphs into the same short line.  Keep only the first display
    # character, but never reinterpret common radical-section labels such as
    # 一部 / 丨部 as entries.  The later visual prominence test is mandatory.
    no_space = re.sub(r"\s+", "", compact)
    if _CJK_RADICAL_SECTION_RE.fullmatch(no_space):
        return None
    chars = list(no_space)
    if 2 <= len(chars) <= 3 and all(_is_single_cjk_ideograph(ch) for ch in chars):
        return _make_chinese_visual_headword(chars[0], parse_text, tuple(repairs), stage="chinese_single_character_with_variant")
    return None
