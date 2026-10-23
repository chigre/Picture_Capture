from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, TYPE_CHECKING
import difflib
import gc
import hashlib
import json
import math
import os
import re
import subprocess  # legacy paddle_headwords public test/monkeypatch hook
import threading
import unicodedata

import numpy as np
from PIL import Image, ImageOps

from .models import AppSettings, Entry, resolved_tesseract_language
from .ocr import review_finalization as _review_finalization
from .ocr import pairing_arbitration as _ocr_pairing
from .ocr import visual_evidence as _visual_evidence
from .ocr import cjk_recovery as _cjk_recovery
from .ocr import candidate_filter as _headword_filter
from .ocr import page_detection as _page_detection
from .ocr import paddle_results as _paddle_results
from .ocr import headword_script as _headword_script
from .ocr import lemma_repairs as _lemma_repairs
from .ocr import line_grouping as _line_grouping
from .ocr import alphabetical_warnings as _alphabetical_warnings
from .ocr import band_preprocessing as _band_preprocessing
from .ocr import headword_normalization as _headword_normalization
from .ocr.headword_models import (
    GrammarTailParse,
    HeadwordFilterRule,
    HeadwordParse,
    OCRLine,
    OCRRecord,
)

from .ocr.paddle_cache_storage import (
    atomic_write_json_impl as _cache_atomic_write_json_impl,
    atomic_write_text_impl as _cache_atomic_write_text_impl,
    compact_cached_candidate_impl as _cache_compact_cached_candidate_impl,
    compact_ocr_cache_file_impl as _cache_compact_ocr_cache_file_impl,
    compact_ocr_cache_payload_impl as _cache_compact_ocr_cache_payload_impl,
    regenerable_sidecars_impl as _cache_regenerable_sidecars_impl,
)

from .quality.paddle_diagnostic_formatting import (
    candidate_reason_impl as _diag_candidate_reason_impl,
    candidate_tsv_row_impl as _diag_candidate_tsv_row_impl,
    comparison_text_impl as _diag_comparison_text_impl,
    diagnostic_text_impl as _diag_diagnostic_text_impl,
    engines_long_text_impl as _diag_engines_long_text_impl,
    fusion_text_impl as _diag_fusion_text_impl,
    issues_text_impl as _diag_issues_text_impl,
    tsv_clean_impl as _diag_tsv_clean_impl,
)
from .runtime.environment import resolve_paddle_device
from .preprocess.page_pixels import normalize_page_rgb
from .persistence.page_sections import PageSection, normalize_page_sections, section_index_for_v
from .profile.dictionary import (
    PROFILE_FILENAME,
    DictionaryProfile,
    effective_project_profile_id,
    leading_relation_label,
    load_dictionary_profile,
    starts_with_internal_article_symbol,
)
from .ocr.engines import find_tesseract, run_google_lens, tesseract_status
from .visual.marker_templates import (
    match_visual_marker_template,
    split_configured_symbols,
    visual_marker_samples_from_settings,
)

if TYPE_CHECKING:
    from .processing import Geometry


_ENGINE_CACHE: dict[tuple[str, str, str, bool], Any] = {}
_ENGINE_CACHE_LOCK = threading.RLock()
_SYLLABLE_SEPARATORS = "·•∙‧.:+"
_RAW_OCR_THRESHOLD = 0.20

# User-editable headword rules live in the project root.  The file is deliberately
# independent of picture_capture_settings.json so rules can be versioned, copied
# between projects, or edited in a plain text editor.  The settings dialog exposes
# the same text using a one-rule-per-line editor.
HEADWORD_FILTER_RULES_FILENAME = "headword_filter_rules.txt"
DEFAULT_HEADWORD_FILTER_RULES = r"""# 词头过滤/强制接受规则：每行一条；空行和 # 注释会被忽略。
#
# 常用拒绝规则（以下均为示例，默认不启用）：
# reject_lemma_exact: sa
# reject_lemma_exact: blación
# reject_lemma_regex: ^[a-záéíóúüñ]{1,2}\.$
# reject_line_contains: □ Conjug.
# reject_line_regex: ^\S+\.\s+.*Conjug\.
#
# 常用强制接受规则（仍要求 OCR 能提取 lemma，且候选位于栏左缘/正文区）：
# accept_lemma_exact: aglomeración
# accept_lemma_regex: ^-a.*
# accept_line_contains: Elemento compositivo
# accept_line_regex: ^-a[·.].*Elemento\s+compositivo
#
# 排除某个错误词性提示（用于 OCR 把非词性文本误当 POS 的特殊情况）：
# pos_exclude_exact: Conjug.
# pos_exclude_regex: ^Conjug\.?$
#
# 兼容简写：lemma_exact/lemma_regex/line_contains/line_regex 等同于 reject_*。
"""

_RULE_ALIASES = {
    "lemma_exact": "reject_lemma_exact",
    "lemma_regex": "reject_lemma_regex",
    "line_contains": "reject_line_contains",
    "line_regex": "reject_line_regex",
    "pos_exclude": "pos_exclude_exact",
}
_RULE_KINDS = {
    "reject_lemma_exact", "reject_lemma_regex",
    "reject_line_contains", "reject_line_regex",
    "accept_lemma_exact", "accept_lemma_regex",
    "accept_line_contains", "accept_line_regex",
    "pos_exclude_exact", "pos_exclude_regex",
}


def parse_headword_filter_rules(text: str, source: str = "") -> list[HeadwordFilterRule]:
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
        kind = _RULE_ALIASES.get(raw_kind.strip().lower(), raw_kind.strip().lower())
        value = value.strip()
        if kind not in _RULE_KINDS:
            raise ValueError(
                f"词头规则第 {line_number} 行类型不支持：{raw_kind.strip()}"
            )
        if not value:
            raise ValueError(f"词头规则第 {line_number} 行内容为空")
        compiled = None
        if kind.endswith("_regex"):
            try:
                compiled = re.compile(value, re.UNICODE | re.IGNORECASE)
            except re.error as exc:
                raise ValueError(
                    f"词头规则第 {line_number} 行正则无效：{exc}"
                ) from exc
        rules.append(HeadwordFilterRule(
            kind=kind, value=value, line_number=line_number, source=source, regex=compiled,
        ))
    return rules


def load_headword_filter_rules(path: Path | None) -> list[HeadwordFilterRule]:
    if path is None or not path.exists():
        return []
    return parse_headword_filter_rules(path.read_text(encoding="utf-8-sig"), str(path))


def _rule_matches(
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
    line_text: str, pos_text: str,
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
        if not _rule_matches(
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




def _ocr_language_parts(settings: AppSettings) -> set[str]:
    return _headword_script._ocr_language_parts(settings)


def _leading_script_family(text: str) -> str:
    return _headword_script._leading_script_family(text, unicode_data=unicodedata)


def _headword_script_compatibility(
    settings: AppSettings, parsed: HeadwordParse | None,
) -> tuple[bool, str]:
    return _headword_script._headword_script_compatibility(
        settings, parsed,
        script_family_fn=_leading_script_family,
        language_parts_fn=_ocr_language_parts,
    )

def _is_chinese_ocr(settings: AppSettings) -> bool:
    """Return True when the active OCR language is Simplified/Traditional Chinese."""
    lang = (settings.ocr_language or "").lower()
    paddle_lang = (settings.paddle_language or "").lower()
    parts = {part.strip() for part in lang.split("+") if part.strip()}
    return bool(
        parts.intersection({"chi_sim", "chi_tra", "ch", "chinese_cht"})
        or paddle_lang in {"ch", "chi_sim", "chi_tra", "chinese_cht"}
    )


def _is_japanese_ocr(settings: AppSettings) -> bool:
    """Return True when the active OCR language is Japanese."""
    lang = (settings.ocr_language or "").lower()
    paddle_lang = (settings.paddle_language or "").lower()
    parts = {part.strip() for part in lang.split("+") if part.strip()}
    return bool(parts.intersection({"jpn", "jpn_vert", "japan"}) or paddle_lang == "japan")


_SYMBOL_FAMILY_BY_LITERAL = {
    "○": "circle_open", "◯": "circle_open", "◦": "circle_open",
    "●": "circle_filled", "•": "circle_filled", "◉": "circle_filled",
    "◇": "diamond_open", "◆": "diamond_filled",
    "□": "square_open", "■": "square_filled",
    "△": "triangle_open", "▽": "triangle_open", "▷": "triangle_open", "◁": "triangle_open",
    "▲": "triangle_filled", "▼": "triangle_filled", "▶": "triangle_filled", "►": "triangle_filled", "◀": "triangle_filled",
    "【": "bracket_open", "〔": "bracket_open", "［": "bracket_open", "[": "bracket_open",
    "「": "bracket_open", "『": "bracket_open", "〈": "bracket_open", "《": "bracket_open",
}

_BRACKET_CLOSER_BY_OPENER = {
    "【": "】", "〔": "〕", "［": "］", "[": "]",
    "「": "」", "『": "』", "〈": "〉", "《": "》",
}


def _split_configured_symbols(value: str | None) -> tuple[str, ...]:
    return split_configured_symbols(value)


def _configured_symbol_inventory(
    settings: AppSettings, profile: DictionaryProfile,
) -> dict[str, Any]:
    """Resolve dictionary-specific symbol roles with Project Profile overrides.

    Standalone entry markers (○/●/◆...) and bracket openers are separate roles.
    The historical profile_symbol_inventory_enabled switch now controls only
    the standalone-marker inventory. Bracket openers remain active whenever
    the user enabled the explicit bracket-headword structure; otherwise a
    configured bracket opener/template can be silently disabled merely because
    the dictionary has no standalone marker prefix.
    """
    base = dict(profile.symbol_inventory or {})
    has_role_aware_inventory = bool(profile.symbol_inventory is not None)
    entry = tuple(str(x) for x in base.get("entry_markers", []) if str(x))
    if not entry and not has_role_aware_inventory:
        entry = tuple(str(x) for x in profile.entry_leading_symbols if str(x))
    bracket = tuple(str(x) for x in base.get("bracket_openers", []) if str(x))

    parser_controls = int(
        getattr(settings, "profile_parser_controls_version", 0) or 0
    ) >= 1
    marker_role_enabled = (
        bool(getattr(settings, "profile_allow_marker_prefix", False))
        if parser_controls else profile.uses_parser("cjk_marker_pinyin")
    )
    bracket_role_enabled = (
        bool(getattr(settings, "profile_cjk_allow_bracketed_headword", True))
        if parser_controls else profile.uses_parser("cjk_bracketed")
    )

    saved = int(getattr(settings, "profile_symbol_inventory_version", 0) or 0) >= 1
    if saved:
        marker_inventory_enabled = bool(
            getattr(settings, "profile_symbol_inventory_enabled", True)
        )
        entry = (
            _split_configured_symbols(
                getattr(settings, "profile_entry_marker_symbols", "")
            )
            if marker_inventory_enabled and marker_role_enabled else ()
        )
        # Bracket structure has its own explicit checkbox and must not be
        # disabled by the standalone-marker switch.
        bracket = (
            _split_configured_symbols(
                getattr(settings, "profile_bracket_open_symbols", "")
            )
            if bracket_role_enabled else ()
        )
        visual_rescue = bool(
            getattr(settings, "profile_symbol_visual_rescue_enabled", True)
        )
        lane_required = bool(
            getattr(settings, "profile_symbol_lane_required", True)
        )
        lane_tolerance = max(
            20, min(
                120,
                int(getattr(settings, "profile_symbol_lane_tolerance_percent", 50) or 50),
            )
        )
    else:
        marker_inventory_enabled = bool(base.get("enabled", True))
        visual_rescue = bool(base.get("visual_rescue", True))
        lane_required = bool(base.get("lane_expected", False))
        lane_tolerance = max(
            20, min(120, int(base.get("lane_tolerance_percent") or 50))
        )
        if not marker_role_enabled:
            entry = ()
        if not bracket_role_enabled:
            bracket = ()
        if (
            not entry
            and parser_controls
            and marker_role_enabled
            and marker_inventory_enabled
        ):
            entry = ("○", "●", "◦", "•", "〓", "◆", "◇", "►", "▶")

    template_mode = str(
        getattr(settings, "profile_symbol_template_mode", "combined") or "combined"
    )
    if template_mode not in {"off", "combined", "template_first"}:
        template_mode = "combined"
    group_mode = str(
        getattr(settings, "profile_symbol_template_group_mode", "role") or "role"
    )
    if group_mode not in {"role", "literal"}:
        group_mode = "role"
    template_threshold = max(
        0.35,
        min(
            0.95,
            float(getattr(settings, "profile_symbol_template_threshold", 0.68) or 0.68),
        ),
    )
    templates = (
        visual_marker_samples_from_settings(settings)
        if int(getattr(settings, "profile_symbol_template_version", 0) or 0) >= 1
        and template_mode != "off"
        else []
    )
    templates = [
        sample for sample in templates
        if (
            str(sample.get("role") or "") == "bracket_open"
            and bracket_role_enabled
        ) or (
            str(sample.get("role") or "") == "entry_marker"
            and marker_inventory_enabled
            and marker_role_enabled
        )
    ]

    effective_enabled = bool(
        (marker_inventory_enabled and marker_role_enabled and entry)
        or (bracket_role_enabled and bracket)
        or templates
    )
    families = {
        _SYMBOL_FAMILY_BY_LITERAL[symbol]
        for symbol in entry + bracket
        if symbol in _SYMBOL_FAMILY_BY_LITERAL
    }
    for family in (str(x) for x in base.get("visual_families", []) if str(x)):
        if family == "bracket_open" and bracket_role_enabled:
            families.add(family)
        elif (
            family != "bracket_open"
            and marker_inventory_enabled
            and marker_role_enabled
        ):
            families.add(family)

    return {
        "enabled": effective_enabled,
        "standalone_inventory_enabled": marker_inventory_enabled,
        "marker_role_enabled": marker_role_enabled,
        "bracket_role_enabled": bracket_role_enabled,
        "entry_markers": entry,
        "bracket_openers": bracket,
        "visual_rescue": visual_rescue,
        "lane_required": lane_required,
        "lane_tolerance_percent": lane_tolerance,
        "visual_families": tuple(sorted(families)),
        "visual_templates": templates,
        "visual_template_mode": template_mode,
        "visual_template_group_mode": group_mode,
        "visual_template_threshold": template_threshold,
    }

def _starts_with_unconfigured_headword_symbol(
    text: str,
    settings: AppSettings,
    profile: DictionaryProfile,
) -> bool:
    """Reject known symbol-led rows that are outside an explicitly saved set."""
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


def _parse_cjk_marker_pinyin_headword(
    text: str, settings: AppSettings, profile: DictionaryProfile,
) -> HeadwordParse | None:
    """Parse marker-led Chinese heads used by Chinese-foreign dictionaries.

    CNIT-like pages use a strong entry marker (○/●/〓) at the column left,
    followed by the Chinese lemma and usually pinyin/romanization.  The marker
    is intentionally mandatory here; geometry later provides the second guard.
    """
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


_CJK_SINGLE_PINYIN_RE = re.compile(
    r"^\s*(?P<head>[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff])\s*[＊*]?\s*"
    r"(?P<pinyin>[A-Za-z\u00C0-\u024F\u1E00-\u1EFF]+"
    r"(?:[ '\-’]+[A-Za-z\u00C0-\u024F\u1E00-\u1EFF]+)*)\b",
    flags=re.UNICODE,
)


def _parse_cjk_single_with_pinyin(text: str, settings: AppSettings) -> HeadwordParse | None:
    """Recognize a single CJK head followed by optional star and pinyin."""
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


def _parse_chinese_bracketed_headword(
    text: str,
    settings: AppSettings,
    *,
    enforce_chinese_language: bool = True,
    allow_japanese_reading_prefix: bool = False,
    allowed_openers: tuple[str, ...] | None = None,
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



_CJK_IDEOGRAPH_RE = re.compile(
    r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]$",
    flags=re.UNICODE,
)
_CJK_RADICAL_SECTION_RE = re.compile(
    r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]部$",
    flags=re.UNICODE,
)


def _is_single_cjk_ideograph(text: str) -> bool:
    return bool(_CJK_IDEOGRAPH_RE.fullmatch(unicodedata.normalize("NFKC", text).strip()))


def _make_chinese_visual_headword(raw: str, parse_text: str, repairs: tuple[str, ...], *, stage: str) -> HeadwordParse:
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


def _parse_chinese_single_character_headword(text: str, settings: AppSettings) -> HeadwordParse | None:
    """Parse an unbracketed one-character Chinese dictionary head.

    Character dictionaries commonly mix two entry families on the same page:
    large single-character heads (e.g. 系 / 刑 / 正) and ordinary-size
    bracketed compounds (e.g. 【並世】).  The single-character parse is only a
    *visual candidate*; geometry/size gates in ``filter_headword_records`` must
    still confirm that the glyph is significantly larger than body text.
    Consequently an ordinary body line that happens to contain one Han
    character does not become an entry merely because it can be parsed.
    """
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

def _paddle_language(settings: AppSettings) -> str:
    if settings.paddle_language.strip():
        return settings.paddle_language.strip()
    mapping = {
        "eng": "en", "ita": "it", "spa": "es", "fra": "fr",
        "por": "pt", "deu": "de", "chi_sim": "ch", "chi_tra": "chinese_cht",
    }
    # Tesseract accepts composite packs such as spa+eng; Paddle expects one
    # language/model family. Prefer the first recognized component.
    parts = [part.strip() for part in settings.ocr_language.split("+") if part.strip()]
    for part in parts:
        if part in mapping:
            return mapping[part]
    return mapping.get(settings.ocr_language, settings.ocr_language)


def clear_paddle_engine_cache(*, keep_key: tuple[str, str, str, bool] | None = None) -> None:
    """Drop cached Paddle engines that are no longer the active configuration.

    Local references held by an in-flight OCR call remain valid, so cache
    eviction cannot invalidate a page currently being recognized.  We avoid
    device-specific forced memory flushes here because those can interfere
    with an engine still executing in another worker/thread.
    """
    with _ENGINE_CACHE_LOCK:
        stale = [key for key in _ENGINE_CACHE if key != keep_key]
        for key in stale:
            _ENGINE_CACHE.pop(key, None)
    if stale:
        gc.collect()


def get_paddle_engine(settings: AppSettings) -> Any:
    """Lazily create and reuse one active PaddleOCR 3.x general OCR pipeline."""
    language = _paddle_language(settings)
    orientation = bool(settings.paddle_use_textline_orientation)
    device = resolve_paddle_device()
    key = (language, device, settings.paddle_ocr_version, orientation)
    with _ENGINE_CACHE_LOCK:
        cached = _ENGINE_CACHE.get(key)
    if cached is not None:
        return cached
    # Layout analysis and full OCR use separate Paddle pipelines. Once formal
    # OCR starts, the detection-only model is no longer needed and may otherwise
    # pin a second large CPU/GPU allocation for the rest of the session.
    from .layout.detection import clear_text_detection_cache
    clear_text_detection_cache()
    # Avoid the PaddlePaddle 3.3.x CPU PIR/oneDNN incompatibility also for
    # ordinary OCR, not only the separate layout detector.
    os.environ["FLAGS_enable_pir_api"] = "0"
    from .runtime.windows_gpu import configure_windows_nvidia_dlls
    configure_windows_nvidia_dlls()
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError(
            "尚未安装 PaddleOCR。请运行当前平台的 OCR 安装脚本，或在受支持平台执行：uv sync --extra ocr-cpu"
        ) from exc
    try:
        kwargs = dict(
            lang=language,
            ocr_version=settings.paddle_ocr_version,
            device=device,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=orientation,
            enable_mkldnn=False,
        )
        try:
            engine = PaddleOCR(**kwargs)
        except TypeError:
            # Compatibility with older PaddleOCR 3.x builds that do not expose
            # enable_mkldnn on PaddleOCR itself.
            kwargs.pop("enable_mkldnn", None)
            engine = PaddleOCR(**kwargs)
    except Exception as exc:
        raise RuntimeError(
            f"PaddleOCR 初始化失败（语言={language}，设备={device}，"
            f"版本={settings.paddle_ocr_version}）：{exc}"
        ) from exc
    # Only one configuration needs to remain strongly referenced by the cache.
    # An older engine that is still in use elsewhere stays alive through that
    # caller's local reference and is collected only after the call finishes.
    clear_paddle_engine_cache(keep_key=key)
    with _ENGINE_CACHE_LOCK:
        existing = _ENGINE_CACHE.get(key)
        if existing is not None:
            return existing
        _ENGINE_CACHE[key] = engine
    return engine


def unwrap_column_band(
    image: Image.Image,
    geometry: "Geometry",
    column: int,
    settings: AppSettings,
    source_width: int | None = None,
    *,
    source_rgb: np.ndarray | None = None,
) -> tuple[Image.Image, int, int]:
    """Straighten a band following the possibly curved left edge of a column.

    Returns ``(band, source_top, source_left_margin)``. Every band row maps to
    the same source-image Y coordinate, so OCR Y boxes only need an offset when
    converted back to PDIC markers.
    """
    if source_rgb is None:
        source = np.asarray(normalize_page_rgb(image))
    else:
        source = np.asarray(source_rgb)
        if source.ndim != 3 or source.shape[2] < 3:
            raise ValueError("source_rgb 必须是 H×W×3 的 RGB 数组")
        if source.shape[0] != image.height or source.shape[1] != image.width:
            raise ValueError("source_rgb 尺寸必须与当前原始页面一致，禁止跨页复用")
        if source.shape[2] != 3:
            source = source[:, :, :3]
    band_ratio = max(
        1.0, min(100.0, float(getattr(settings, "paddle_band_width_ratio", 100.0)))
    ) / 100.0
    left_margin = max(0, int(settings.paddle_band_left_margin))
    if source_width is not None:
        # Explicit callers (notably separator refinement) request an exact
        # source width and intentionally bypass the user-facing percentage.
        band_width = max(24, int(source_width))
    else:
        # paddle_band_width_ratio is a percentage of the actual detected
        # column width, not of the historical fixed paddle_band_width.
        # Keep the left safety margin separate from that percentage: 100%
        # means the complete column content plus the configured pixels to its left.
        #
        # The old 600px reference made 60% become 360px on every scan, which
        # silently clipped long CJK headwords and changed meaning with DPI.
        configured_column_width = max(
            1, int(getattr(settings, "column_width", 0) or 0)
        )
        geometry_interval_width = (
            int(geometry.column_widths[column])
            if 0 <= column < len(geometry.column_widths)
            else configured_column_width
        )
        # Geometry's last interval may extend from the final column start all
        # the way to the page edge, so it is only an upper bound here.  The
        # effective per-page settings.column_width is the actual dictionary
        # column width resolved by Profile/layout analysis.
        column_width = max(
            1, min(configured_column_width, max(1, geometry_interval_width))
        )
        content_width = max(1, round(column_width * band_ratio))
        band_width = max(24, content_width + left_margin)
    top = max(0, geometry.top)
    canonical_size = geometry.transform.canonical_size(image.size)
    bottom = min(canonical_size[1], geometry.bottom)
    if geometry.transform.kind != "identity":
        canonical_left = max(0, geometry.column_starts[column] - left_margin)
        canonical_right = min(canonical_size[0], canonical_left + band_width)
        source_box = geometry.transform.canonical_box_to_source(
            (canonical_left, top, canonical_right, bottom), image.size
        )
        return normalize_page_rgb(image).crop(source_box), top, left_margin
    band = np.full((max(1, bottom - top), band_width, 3), 255, dtype=np.uint8)
    for band_y, source_y in enumerate(range(top, bottom)):
        source_x = geometry.x_at(column, source_y) - left_margin
        src_left = max(0, source_x)
        src_right = min(image.width, source_x + band_width)
        if src_right <= src_left:
            continue
        dst_left = src_left - source_x
        dst_right = dst_left + (src_right - src_left)
        band[band_y, dst_left:dst_right] = source[source_y, src_left:src_right]
    return Image.fromarray(band, "RGB"), top, left_margin


def _json_payload(result: Any) -> dict[str, Any]:
    """Historical patch point for PaddleOCR 3.x result decoding."""
    return _paddle_results._json_payload(result)


def extract_ocr_records(result: Any) -> list[OCRRecord]:
    """Decode via the current core callbacks, preserving legacy monkeypatches."""
    return _paddle_results.extract_ocr_records(
        result, payload_reader=_json_payload, record_type=OCRRecord, np_module=np,
    )

def run_paddle_band(band: Image.Image, settings: AppSettings, engine: Any | None = None) -> list[OCRRecord]:
    engine = engine or get_paddle_engine(settings)
    prepared, input_scale = prepare_ocr_band(
        band,
        max_long_side=getattr(settings, "paddle_max_input_side", 2800),
        mode=getattr(settings, "paddle_preprocessing", "original"),
    )
    try:
        results = list(engine.predict(
            np.asarray(prepared),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=bool(settings.paddle_use_textline_orientation),
            # Keep low-confidence fragments in the raw cache. Syllabified bold
            # headwords are sometimes harder to recognize than the following
            # POS/definition; candidate confidence is evaluated after same-line
            # fragments have been merged.
            text_rec_score_thresh=_RAW_OCR_THRESHOLD,
        ))
    except Exception as exc:
        raise RuntimeError(f"PaddleOCR 推理失败：{exc}") from exc
    if not results:
        return []
    records = extract_ocr_records(results[0])
    if input_scale == 1.0:
        return records
    inverse = 1.0 / input_scale
    return [
        OCRRecord(row.text, row.confidence, tuple(round(value * inverse) for value in row.box))
        for row in records
    ]


def prepare_ocr_band(
    band: Image.Image, *, max_long_side: int = 2800, mode: str = "original",
) -> tuple[Image.Image, float]:
    """Historical OCR band preprocessing with current image/Otsu callbacks."""
    return _band_preprocessing.prepare_ocr_band(
        band, max_long_side=max_long_side, mode=mode,
        normalize_rgb_fn=normalize_page_rgb, otsu_fn=_otsu_threshold,
        image_ops=ImageOps, image_cls=Image, np_module=np,
    )

def _records_to_canonical_band(
    records: list[OCRRecord], source_band_size: tuple[int, int], transform_kind: str
) -> list[OCRRecord]:
    """Map OCR boxes to analysis space without transforming OCR input pixels."""
    from .geometry.layout_transform import LayoutTransform

    transform = LayoutTransform(transform_kind)
    return [
        OCRRecord(
            record.text,
            record.confidence,
            transform.source_box_to_canonical(
                record.box, source_band_size
            ),
            recovery=record.recovery,
            recovery_source_text=record.recovery_source_text,
            parent_box=(
                transform.source_box_to_canonical(
                    record.parent_box, source_band_size
                )
                if record.parent_box is not None else None
            ),
        )
        for record in records
    ]


def recognize_paddle_text(
    image: Image.Image,
    settings: AppSettings,
    engine: Any | None = None,
) -> str:
    """Recognize one already-cropped line and return text in reading order."""
    records = run_paddle_band(normalize_page_rgb(image), settings, engine=engine)
    return " ".join(record.text for record in records if record.text).strip()



def _tesseract_executable(executable: str) -> str | None:
    return find_tesseract(executable)


def run_tesseract_band_records(
    band: Image.Image,
    settings: AppSettings,
    psm_override: int | None = None,
) -> tuple[list[OCRRecord], str]:
    """Legacy public adapter; execution lives in an independent OCR module."""
    from .ocr.tesseract_runner import run_tesseract_band_records_impl
    return run_tesseract_band_records_impl(
        band, settings, psm_override,
        resolve_fn=_tesseract_executable, group_fn=group_ocr_records,
    )


def _repair_headword_ocr(text: str) -> tuple[str, tuple[str, ...]]:
    """Stable historical helper; lemma repair implementation is OCR-owned."""
    return _lemma_repairs.repair_headword_ocr(text, re_module=re)

def _vertical_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    return _line_grouping.vertical_overlap(a, b)


def group_ocr_records(records: list[OCRRecord], y_ratio: float = 0.55) -> list[OCRLine]:
    """Historical OCR clustering entrypoint with live overlap and model hooks."""
    return _line_grouping.group_ocr_records(
        records, y_ratio, overlap_fn=_vertical_overlap,
        line_type=OCRLine, np_module=np,
    )


def _merge_ocr_lines(lines: list[OCRLine]) -> OCRLine:
    """Historical logical line join with the original OCRLine identity."""
    return _line_grouping.merge_ocr_lines(lines, line_type=OCRLine, np_module=np)

def _repair_split_headword_lines(
    lines: list[OCRLine],
    settings: AppSettings,
    left_limit: int,
    patterns: tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]],
) -> list[OCRLine]:
    """Actively absorb right-side OCR fragments for a left-edge lemma.

    OCR engines sometimes assign the bold lemma and ``, da adj.`` / ``v.`` to
    separate line boxes because their baselines/heights differ.  Normal line
    clustering can therefore miss a valid POS cue.  We only perform this rescue
    for a line beginning at the column left edge, only absorb fragments to its
    right, and only keep the merge if it creates a structural dictionary cue.
    """
    if not lines:
        return []
    heights = [max(1, line.box[3] - line.box[1]) for line in lines]
    median_h = max(1.0, float(np.median(heights)))
    used: set[int] = set()
    output: list[OCRLine] = []

    def structural(parsed: HeadwordParse | None) -> bool:
        return bool(parsed and (parsed.has_pos or parsed.has_inflection or parsed.has_descriptor))

    for i, line in enumerate(lines):
        if i in used:
            continue
        parsed = parse_headword_text(line.text, settings, patterns)
        if line.box[0] > left_limit or structural(parsed):
            output.append(line)
            continue
        # A plausible split fragment should sit to the right on essentially the
        # same physical row. Nearby lines starting again at the left margin are
        # almost certainly separate dictionary/body rows and are never absorbed.
        current = line
        selected: list[int] = []
        candidates: list[tuple[int, OCRLine]] = []
        for j, other in enumerate(lines):
            if j == i or j in used:
                continue
            if other.box[0] <= left_limit:
                continue
            if other.box[0] < current.box[0]:
                continue
            h = max(current.box[3] - current.box[1], other.box[3] - other.box[1], 1)
            cy1 = (current.box[1] + current.box[3]) / 2.0
            cy2 = (other.box[1] + other.box[3]) / 2.0
            same_row = _vertical_overlap(current.box, other.box) >= 0.18 or abs(cy1 - cy2) <= 0.55 * h
            gap = other.box[0] - current.box[2]
            if same_row and -0.5 * median_h <= gap <= 7.0 * median_h:
                candidates.append((j, other))
        for j, other in sorted(candidates, key=lambda pair: pair[1].box[0])[:4]:
            trial = _merge_ocr_lines([current, other])
            trial_parsed = parse_headword_text(trial.text, settings, patterns)
            # We may need more than one fragment (lemma | gender | POS), so keep
            # extending while fragments are adjacent; commit only after structure
            # appears.
            current = trial
            selected.append(j)
            if structural(trial_parsed):
                used.update(selected)
                parsed = trial_parsed
                current.logical_repairs = tuple(dict.fromkeys(current.logical_repairs + ("RIGHT_FRAGMENT_ABSORBED",)))
                break
        if structural(parsed):
            output.append(current)
        else:
            output.append(line)
    return sorted(output, key=lambda item: (item.box[1], item.box[0]))


def _repair_wrapped_headword_structure(
    lines: list[OCRLine],
    settings: AppSettings,
    left_limit: int,
    patterns: tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]],
) -> list[OCRLine]:
    """Attach a POS label that wrapped onto the next printed line.

    Long forms such as ``agroalimentación (pl. ...)`` can consume the whole
    first line and leave ``s.f.`` at the beginning of the next one.  The marker
    belongs at the first line's Y, so this function augments only the logical
    text used for parsing while keeping the original first-line geometry.
    """
    if not lines:
        return []
    _headword_pattern, _special_pattern, pos_pattern = patterns
    heights = [max(1, line.box[3] - line.box[1]) for line in lines]
    median_h = max(1.0, float(np.median(heights)))
    output: list[OCRLine] = []
    for i, line in enumerate(lines):
        parsed = parse_headword_text(line.text, settings, patterns)
        if (
            i + 1 >= len(lines) or line.box[0] > left_limit or not parsed
            or parsed.has_pos or parsed.looks_like_continuation
        ):
            output.append(line)
            continue
        nxt = lines[i + 1]
        vertical_gap = nxt.box[1] - line.box[3]
        # Printed lines may have slightly overlapping OCR boxes; allow only the
        # immediately adjacent row and a modest indentation.
        if vertical_gap > 0.80 * median_h or nxt.box[0] > left_limit + 1.25 * median_h:
            output.append(line)
            continue
        pos_match, noise = _find_pos_cue(nxt.text, pos_pattern, min(48, settings.paddle_pos_search_chars))
        if pos_match is None:
            output.append(line)
            continue
        # A genuine wrapped POS must occur at the beginning, apart from a tiny
        # square-marker OCR artifact accepted by _find_pos_cue.
        prefix = nxt.text[:pos_match.start()]
        if _strip_entry_modifiers(prefix).strip() and not noise:
            output.append(line)
            continue
        pos_text = pos_match.group(0).strip()
        synthetic = f"{line.text.rstrip()} {pos_text}"
        output.append(OCRLine(
            text=synthetic, confidence=min(line.confidence, nxt.confidence),
            box=line.box, records=line.records,
            logical_repairs=tuple(dict.fromkeys(line.logical_repairs + ("MULTILINE_POS",))),
        ))
    return output



def _repair_multiline_headword_state_machine(
    lines: list[OCRLine],
    settings: AppSettings,
    left_limit: int,
    patterns: tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]],
    max_follow_lines: int = 2,
) -> list[OCRLine]:
    """General v2.0 multi-line grammar recovery.

    The earlier repair handled only `lemma ...` + immediate `POS`.  This state
    machine can inspect up to two following printed lines and stops as soon as a
    structured parse is recovered. Geometry remains anchored to the first line,
    so the separator is never moved to the continuation row.
    """
    if not lines:
        return []
    _headword_pattern, _special_pattern, pos_pattern = patterns
    median_h = max(1.0, float(np.median([max(1, l.box[3] - l.box[1]) for l in lines])))
    out: list[OCRLine] = []
    for i, line in enumerate(lines):
        parsed = parse_headword_text(line.text, settings, patterns)
        if (
            line.box[0] > left_limit or not parsed or parsed.has_pos or parsed.has_descriptor
            or parsed.looks_like_continuation
        ):
            out.append(line)
            continue
        # Only trigger for a plausible incomplete dictionary head: morphology
        # note, grammatical comma, cropped opening parenthesis, or a long bold
        # display form that consumed most of the OCR band.
        unmatched_slash = line.text.count("/") % 2 == 1
        open_pronunciation = bool(
            ("[" in line.text and "]" not in line.text) or unmatched_slash
        )
        incomplete_shape = bool(
            parsed.has_inflection
            or re.search(r",\s*[^,;:]{0,24}$", line.text, flags=re.UNICODE)
            or ("(" in line.text and ")" not in line.text)
            or open_pronunciation
            or len(parsed.normalized.strip("-")) >= 11
        )
        if not incomplete_shape:
            out.append(line)
            continue

        synthetic = line.text.rstrip()
        joined_records = list(line.records)
        joined_conf = line.confidence
        recovered: OCRLine | None = None
        prev = line
        for step in range(1, max_follow_lines + 1):
            j = i + step
            if j >= len(lines):
                break
            nxt = lines[j]
            gap = nxt.box[1] - prev.box[3]
            if gap > 0.95 * median_h or nxt.box[0] > left_limit + 1.75 * median_h:
                break
            pronunciation_still_open = bool(
                ("[" in synthetic and "]" not in synthetic)
                or synthetic.count("/") % 2 == 1
            )
            # Do not absorb a clearly new headword row.
            nxt_parsed = parse_headword_text(nxt.text, settings, patterns)
            if (
                not pronunciation_still_open and nxt.box[0] <= left_limit
                and nxt_parsed and (nxt_parsed.has_pos or nxt_parsed.has_descriptor)
            ):
                break
            # The continuation should begin with POS/grammar material or be a
            # short continuation of an open morphology note.
            pm, noise = _find_pos_cue(nxt.text, pos_pattern, min(64, settings.paddle_pos_search_chars))
            starts_grammar = bool(pm is not None and (pm.start() <= 3 or noise))
            if not starts_grammar and not (
                ("(" in synthetic and ")" not in synthetic) or pronunciation_still_open
            ):
                break
            synthetic = synthetic + " " + nxt.text.strip()
            joined_records.extend(nxt.records)
            joined_conf = min(joined_conf, nxt.confidence)
            trial = parse_headword_text(synthetic, settings, patterns)
            if trial and trial.normalized.casefold() == parsed.normalized.casefold() and (
                trial.has_pos or trial.has_descriptor or trial.has_inflection
            ):
                recovered = OCRLine(
                    text=synthetic,
                    confidence=joined_conf,
                    box=line.box,
                    records=joined_records,
                    logical_repairs=tuple(dict.fromkeys(
                        line.logical_repairs + (f"MULTILINE_STATE_JOIN:{step}",)
                    )),
                )
                if trial.has_pos or trial.has_descriptor:
                    break
            prev = nxt
        out.append(recovered or line)
    return out


def normalize_headword(text: str, remove_syllable_separators: bool = True) -> str:
    """Historical patchable OCR entrypoint; implementation is package-owned."""
    return _headword_normalization.normalize_headword(
        text, remove_syllable_separators,
        syllable_separators=_SYLLABLE_SEPARATORS,
        re_module=re,
    )

def _compile_patterns(
    settings: AppSettings,
    profile: DictionaryProfile | None = None,
) -> tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]]:
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


def _strip_entry_modifiers(prefix: str) -> str:
    """Remove morphology/marker material allowed between lemma and a cue.

    This is intentionally grammar-oriented rather than lexicon-oriented.  It
    accepts the recurring dictionary shapes seen on pp.55-70: gender variants
    (`, da`, `, so·ra`), parenthetical forms, square markers and Roman section
    markers.  It also tolerates a truncated parenthesis at the OCR band edge.
    """
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


def _find_pos_cue(
    tail: str, pos_pattern: re.Pattern[str], limit: int, *, allow_numeric_prefix: bool = False,
) -> tuple[re.Match[str] | None, str]:
    """Find a POS label structurally attached to the headword.

    Returns ``(match, ignored_noise)``.  ``ignored_noise`` is a very short OCR
    artifact between lemma/gender form and POS (e.g. ``E`` in ``agua Es.f.``
    or ``Ml`` in ``agujeta Mls.f.``).  The allow-list is deliberately narrow so
    definition prose such as ``de s.m.`` is not mistaken for a grammatical cue.
    ``Pron. [..]`` is explicitly excluded because these pages use it for
    pronunciation, not the pronoun part of speech.
    """
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


def _leading_inflection_cue(tail: str) -> tuple[bool, str]:
    """Recognize leading morphology notes, including cropped/unclosed notes."""
    leading = tail.lstrip()
    if not re.match(r"^\((?:pl|f|m|tb|masc|fem)\.?\b", leading, flags=re.I | re.UNICODE):
        return False, ""
    # Diagnostics only: keep a bounded readable prefix.  The cue remains valid
    # even if the closing ')' lies beyond the OCR band.
    text = leading[:140].strip()
    return True, text


def _parallel_marker_extension(
    tail: str,
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
    m = re.match(rf"^\s+(?P<extra>{token})\s+(?P<mark>\|\|)\s*", tail, flags=re.UNICODE)
    if m:
        return m.group("extra"), m.end("extra"), True, "parallel_gloss"
    if re.match(r"^\s*\|\|\s*", tail):
        return "", 0, True, "parallel_gloss"

    # OCR often renders the two vertical bars as ll / |l / l|.  Require a nearby
    # tilde placeholder or a hyphenated cross-reference so ordinary 'll' text is
    # not promoted to a structural cue.
    m = re.match(
        rf"^\s+(?P<extra>{token})\s+(?P<mark>ll|\|l|l\|)\s+(?P<after>[^;:]{{0,18}}(?:~|-[^\s;:]+))",
        tail, flags=re.UNICODE | re.IGNORECASE,
    )
    if m:
        return m.group("extra"), m.end("extra"), True, "parallel_gloss_ocr"
    if re.match(r"^\s*(?:ll|\|l|l\|)\s+[^;:]{0,18}(?:~|-[^\s;:]+)", tail, flags=re.I | re.UNICODE):
        return "", 0, True, "parallel_gloss_ocr"
    return "", 0, False, ""



_BUNDLED_PROFILE = load_dictionary_profile(preset="latin_structured_symbols", language="spa")
_USAGE_ABBREVIATIONS = {
    label.casefold().rstrip(".")
    for label in _BUNDLED_PROFILE.metadata_labels
} | {
    # Common accent-loss OCR variants.
    "amer", "naut", "quim", "mus", "fis",
}


def _consume_leading_space(text: str, cursor: int) -> int:
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    return cursor


def _parse_structured_tail(
    tail: str,
    pos_pattern: re.Pattern[str],
    search_limit: int,
    *,
    parallel_descriptor: bool = False,
    parallel_label: str = "",
    allow_numeric_prefix: bool = False,
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
    variant_re = re.compile(
        rf"\s*,\s*(?P<v>-?{letter}+(?:\s*[·•∙‧.:+\-]\s*{letter}+)*\.?)",
        flags=re.UNICODE | re.IGNORECASE,
    )
    # Morphology notes; closing ')' may be absent because the OCR candidate band
    # ended before it. We therefore accept a bounded open form as a recovery.
    closed_inflection_re = re.compile(
        r"\s*(?P<i>\((?:pl|f|m|tb|masc|fem)\.?[^)]{0,120}\))",
        flags=re.UNICODE | re.IGNORECASE,
    )
    open_inflection_re = re.compile(
        r"\s*(?P<i>\((?:pl|f|m|tb|masc|fem)\.?[^)]{0,120})$",
        flags=re.UNICODE | re.IGNORECASE,
    )

    # Variant/inflection order varies across dictionary entries, so iterate.
    for _ in range(6):
        cursor = _consume_leading_space(tail, cursor)
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
    cursor = _consume_leading_space(tail, cursor)
    pos_ahead = r"(?=\s+(?:n|v|adj|adv|prep|conj|pron|interj|art|num)\.)"
    pronunciation_re = re.compile(
        rf"(?:\[[^\]]{{1,180}}(?:\]|{pos_ahead})|/[^/]{{1,180}}(?:/|{pos_ahead}))",
        flags=re.UNICODE | re.IGNORECASE,
    )
    pronunciation_match = pronunciation_re.match(tail[cursor:])
    if pronunciation_match:
        pronunciation = pronunciation_match.group(0).strip()
        cursor += pronunciation_match.end()
        trace.append(f"pronunciation:{pronunciation}")

    # Consume typography/section markers that may separate pronunciation and POS.
    cursor = _consume_leading_space(tail, cursor)
    marker_match = re.match(
        r"[|{}<>«»“”‘’\".,;:·•∙‧◆◇■□►▶*†‡§¶_+\-\s]*(?:I{1,4}|IV|V)?\s*",
        tail[cursor:], flags=re.UNICODE,
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
    pos_match, pos_noise = _find_pos_cue(
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
    descriptor_start = cursor if pos_text else _consume_leading_space(tail, cursor)
    descriptor_source = _strip_entry_modifiers(tail[descriptor_start:descriptor_start + max(100, search_limit)])
    descriptor_match = re.match(
        r"(elemento\s+compositivo|forma\s+prefija|forma\s+sufija|"
        r"prefijo(?:\s+que)?|sufijo(?:\s+que)?|sigla\s+de|abreviatura\s+de|"
        r"acr[oó]nimo\s+de|contracci[oó]n\s+de)",
        descriptor_source,
        flags=re.UNICODE | re.IGNORECASE,
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
        usage_cursor = _consume_leading_space(tail, usage_cursor)
        m = re.match(r"(?P<u>[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,12})\.\s*", tail[usage_cursor:], flags=re.UNICODE)
        if not m:
            break
        token = m.group("u")
        if token.casefold().rstrip(".") not in _USAGE_ABBREVIATIONS:
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
    return GrammarTailParse(
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


def _parse_bug_types(
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


def parse_headword_text(
    text: str,
    settings: AppSettings,
    patterns: tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]] | None = None,
    profile: DictionaryProfile | None = None,
) -> HeadwordParse | None:
    """Extract and normalize a lemma from one merged OCR line.

    The parser deliberately hardens itself against a project carrying an older
    user regex.  If that regex swallows the grammatical comma/terminal period,
    punctuation is moved back into the tail before structural parsing.  This is
    what recovers the large family of `lemma, da adj.` misses seen on pp.55-70.
    """
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


def _looks_like_marker_noise_lemma(parsed: HeadwordParse | None) -> bool:
    """Reject only very narrow square/bullet OCR artifacts used as fake lemmas.

    Examples observed on these pages include ``Ml adj./s.`` where the printed
    square marker was OCRed as two letters.  Real short acronym entries normally
    carry a descriptor such as ``Sigla de`` and therefore are not covered here.
    """
    if not parsed or parsed.has_descriptor or parsed.has_inflection:
        return False
    compact = re.sub(r"[^A-Za-z]", "", parsed.raw).casefold()
    return compact in {"ml", "ll", "il", "ii", "l"}

def _ink_ratio(gray: np.ndarray, box: tuple[int, int, int, int]) -> float:
    x0, y0, x1, y1 = box
    y0, y1 = max(0, y0), min(gray.shape[0], y1)
    x0, x1 = max(0, x0), min(gray.shape[1], x1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return float((gray[y0:y1, x0:x1] < 180).mean())


def _leading_box(line: OCRLine, matched_chars: int) -> tuple[int, int, int, int]:
    """Approximate the lemma's visual box for a local ink/boldness estimate."""
    x0, y0, x1, y1 = line.box
    if not line.text or x1 <= x0:
        return line.box
    fraction = min(1.0, max(0.16, matched_chars / max(1, len(line.text))))
    right = min(x1, x0 + max(3, round((x1 - x0) * fraction * 1.12)))
    return x0, y0, right, y1


def _true_runs(values: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(values):
        if value and start is None:
            start = index
        elif not value and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(values)))
    return runs


def _otsu_threshold(gray: np.ndarray) -> int:
    """Historical black/white threshold; implementation owned by OCR band leaf."""
    return _band_preprocessing.otsu_threshold(gray, np_module=np)

def _separator_analysis_x_bounds(
    width: int,
    settings: AppSettings,
    pixel_scale: float = 1.0,
) -> tuple[int, int]:
    """Return the left-local X ROI used for separator/boundary analysis.

    Dictionary headwords usually live at the left of a column while definitions
    can run across its full width.  Analysing the whole column lets long text on
    the preceding definition line contaminate a local Y boundary.  The user can
    therefore limit refinement to a percentage of the left side of the column.
    """
    width = max(1, int(width))
    margin = max(0, round(max(0, settings.paddle_separator_column_margin) * pixel_scale))
    margin = min(margin, max(0, width // 4))
    ratio = max(10.0, min(100.0, float(getattr(settings, "paddle_separator_roi_width_ratio", 60.0)))) / 100.0
    usable = max(1, width - margin * 2)
    x0 = margin
    x1 = min(width - margin, x0 + max(16, round(usable * ratio)))
    if x1 - x0 < 16:
        x0, x1 = 0, width
    return int(x0), int(x1)


def detect_image_separator_candidates(
    gray: np.ndarray,
    reference_line_height: int,
    settings: AppSettings,
    pixel_scale: float = 1.0,
    lower_bound: int = 0,
) -> list[dict[str, Any]]:
    """Detect image-only entry-boundary candidates from blank-to-ink transitions.

    These candidates deliberately contain no OCR text.  They are an independent
    visual source that is later paired *mutually* with OCR lines.  Dense pages
    with no stable whitespace simply emit few/no candidates and fall back to the
    OCR geometry path.
    """
    if gray.size == 0 or gray.ndim < 2:
        return []
    height, width = gray.shape[:2]
    if height < 4 or width < 12:
        return []
    lower = max(0, min(height - 1, int(lower_bound)))
    x0, x1 = _separator_analysis_x_bounds(width, settings, pixel_scale)
    roi = gray[lower:, x0:x1]
    if roi.size == 0 or roi.shape[0] < 4 or roi.shape[1] < 8:
        return []

    threshold = _otsu_threshold(roi)
    ink = roi <= threshold
    # Remove only narrow persistent vertical rules; they otherwise make every
    # row appear non-blank.
    if ink.shape[0] >= 3 and ink.shape[1] >= 3:
        persistent = ink.mean(axis=0) >= 0.72
        if persistent.any():
            narrow = np.zeros_like(persistent, dtype=bool)
            max_rule_width = max(2, round(ink.shape[1] * 0.025))
            for a, b in _true_runs(persistent):
                if b - a <= max_rule_width:
                    narrow[a:b] = True
            if narrow.any():
                ink = ink.copy(); ink[:, narrow] = False

    row_ink = ink.mean(axis=1).astype(np.float64)
    if row_ink.size >= 3:
        padded = np.pad(row_ink, (1, 1), mode="edge")
        smooth = np.convolve(padded, np.ones(3, dtype=np.float64) / 3.0, mode="valid")
    else:
        smooth = row_ink.copy()

    line_h = max(3, int(round(reference_line_height)))
    quantization = 1.0 / max(1, ink.shape[1] * 3)
    positive = smooth[smooth > 0]
    low_positive = float(np.percentile(positive, 20)) if positive.size else 0.0
    blank_threshold = max(quantization * 2.5, min(0.010, low_positive * 0.45 if low_positive else 0.0025))
    blank_mask = smooth <= blank_threshold
    ink_threshold = max(blank_threshold * 1.8, quantization * 5.0)
    ink_mask = smooth > ink_threshold
    min_blank = max(3, round(line_h * 0.12))
    min_ink = max(2, round(line_h * 0.07))
    configured_safety = max(0, int(getattr(settings, "paddle_separator_safety_px", 2)))
    safety = max(0, round(configured_safety * max(0.5, float(pixel_scale))))

    result: list[dict[str, Any]] = []
    for run_start, run_end in _true_runs(blank_mask):
        if run_end - run_start < min_blank:
            continue
        # The visual boundary is useful only when the blank band is followed by
        # a sustained ink onset soon below it.
        onset: int | None = None
        j = run_end
        max_j = min(len(smooth) - 1, run_end + max(4, round(line_h * 0.32)))
        while j <= max_j:
            e = min(len(smooth), j + min_ink)
            if e - j >= min_ink and (bool(np.all(~blank_mask[j:e])) or bool(np.all(ink_mask[j:e]))):
                onset = j; break
            j += 1
        if onset is None:
            continue
        onset_y = lower + onset
        blank_bottom = lower + run_end - 1
        boundary_y = int(min(blank_bottom, onset_y - safety))
        boundary_y = max(lower, min(height - 1, boundary_y))
        blank_len = run_end - run_start
        strength = min(1.0, blank_len / max(1.0, line_h * 0.35))
        result.append({
            "y": boundary_y,
            "ink_onset_y": int(onset_y),
            "blank_start_y": int(lower + run_start),
            "blank_end_y": int(blank_bottom),
            "blank_rows": int(blank_len),
            "strength": round(float(strength), 4),
            "analysis_x0": int(x0),
            "analysis_x1": int(x1),
            "threshold": int(threshold),
        })
    return result


def match_ocr_lines_to_image_boundaries(
    lines: list[OCRLine],
    boundaries: list[dict[str, Any]],
    reference_line_height: int,
) -> dict[int, dict[str, Any]]:
    """Mutually pair OCR lines and image boundaries using vertical geometry.

    A match is accepted only when the OCR line chooses the boundary and the
    boundary independently chooses the same OCR line.  This prevents a large
    whitespace region from being attached to the wrong neighbouring line.
    """
    if not lines or not boundaries:
        return {}
    line_h = max(3, int(round(reference_line_height)))
    max_delta = max(6, round(line_h * 0.75))

    def distance(line: OCRLine, boundary: dict[str, Any]) -> float:
        onset = int(boundary.get("ink_onset_y", boundary.get("y", 0)))
        y0, y1 = int(line.box[1]), int(line.box[3])
        # OCR boxes may begin slightly high or include accents.  Distance to the
        # vertical box interval is more stable than top-only distance.
        if y0 <= onset <= y1:
            interval = 0.0
        else:
            interval = float(min(abs(onset - y0), abs(onset - y1)))
        top_delta = abs(onset - y0)
        return interval * 0.65 + top_delta * 0.35

    line_choice: dict[int, int] = {}
    for i, line in enumerate(lines):
        ranked = sorted((distance(line, b), j) for j, b in enumerate(boundaries))
        if ranked and ranked[0][0] <= max_delta:
            line_choice[i] = ranked[0][1]
    boundary_choice: dict[int, int] = {}
    for j, boundary in enumerate(boundaries):
        ranked = sorted((distance(line, boundary), i) for i, line in enumerate(lines))
        if ranked and ranked[0][0] <= max_delta:
            boundary_choice[j] = ranked[0][1]

    matches: dict[int, dict[str, Any]] = {}
    for i, j in line_choice.items():
        if boundary_choice.get(j) != i:
            continue
        item = dict(boundaries[j])
        item["match_method"] = "mutual_nearest_y"
        item["ocr_line_index"] = int(i)
        item["delta_to_box_top"] = int(item.get("ink_onset_y", item["y"])) - int(lines[i].box[1])
        matches[i] = item
    return matches


def _visual_evidence_deps() -> _visual_evidence.VisualEvidenceDeps:
    """Snapshot current monkeypatchable visual evidence operations for each call."""
    return _visual_evidence.VisualEvidenceDeps(
        _binary_rle_components=_binary_rle_components,
        _visual_marker_shape_metrics=_visual_marker_shape_metrics,
        _visual_family_symbol=_visual_family_symbol,
        _classify_visual_symbol_component=_classify_visual_symbol_component,
        _trusted_visual_marker_lanes=_trusted_visual_marker_lanes,
        _apply_trusted_visual_marker_lanes=_apply_trusted_visual_marker_lanes,
        _detect_visual_entry_markers=_detect_visual_entry_markers,
        _match_visual_entry_markers_to_lines=_match_visual_entry_markers_to_lines,
        _parse_cjk_visual_marker_line=_parse_cjk_visual_marker_line,
        _parse_visual_configured_symbol_line=_parse_visual_configured_symbol_line,
        _leading_cjk_ideograph=_leading_cjk_ideograph,
        _cjk_visual_projection_runs=_cjk_visual_projection_runs,
        _cjk_right_context_metrics=_cjk_right_context_metrics,
        _cjk_right_context_features=_cjk_right_context_features,
        _cjk_candidate_right_context_metrics=_cjk_candidate_right_context_metrics,
        _cjk_candidate_right_context_features=_cjk_candidate_right_context_features,
        _cjk_word_for_visual_run=_cjk_word_for_visual_run,
        _otsu_threshold=_otsu_threshold,
        _is_chinese_ocr=_is_chinese_ocr,
        _repair_headword_ocr=_repair_headword_ocr,
        _parse_chinese_bracketed_headword=_parse_chinese_bracketed_headword,
        _is_japanese_ocr=_is_japanese_ocr,
        _is_single_cjk_ideograph=_is_single_cjk_ideograph,
        _true_runs=_true_runs,
        parse_headword_text=parse_headword_text,
        _parse_cjk_single_with_pinyin=_parse_cjk_single_with_pinyin,
        match_visual_marker_template=match_visual_marker_template,
        _SYMBOL_FAMILY_BY_LITERAL=_SYMBOL_FAMILY_BY_LITERAL,
        _BRACKET_CLOSER_BY_OPENER=_BRACKET_CLOSER_BY_OPENER,
    )


def _binary_rle_components(
    mask: np.ndarray,
) -> list[tuple[int, int, int, int, int]]:
    """Dependency-free 8-connected components for visual marker analysis."""
    return _visual_evidence._binary_rle_components(_visual_evidence_deps(), mask)


def _visual_marker_shape_metrics(mask: np.ndarray) -> dict[str, float]:
    """Geometry descriptors shared by configured visual symbol families."""
    return _visual_evidence._visual_marker_shape_metrics(_visual_evidence_deps(), mask)


def _visual_family_symbol(
    inventory: dict[str, Any], family: str,
) -> tuple[str, str] | None:
    """Return (literal, role) for one configured visual family."""
    return _visual_evidence._visual_family_symbol(_visual_evidence_deps(), inventory, family)


def _classify_visual_symbol_component(
    mask: np.ndarray,
    line_h: float,
    inventory: dict[str, Any],
) -> tuple[str, str, str, dict[str, float]] | None:
    """Classify a connected component only into configured symbol families."""
    return _visual_evidence._classify_visual_symbol_component(_visual_evidence_deps(), mask, line_h, inventory)


def _trusted_visual_marker_lanes(
    lines: list[OCRLine],
    inventory: dict[str, Any],
    median_height: float,
) -> dict[str, dict[str, Any]]:
    """Derive stable marker lanes from OCR rows with explicit printed symbols.

    Bracket-like CJK radicals are common enough that candidate symbols must not
    define their own bracket lane.  When OCR explicitly sees the configured
    opener (for example 【) on at least two rows, those rows provide an
    independent X anchor for visual rescue.  Generic bracket shapes are then
    allowed only near this trusted lane.
    """
    return _visual_evidence._trusted_visual_marker_lanes(_visual_evidence_deps(), lines, inventory, median_height)


def _apply_trusted_visual_marker_lanes(
    candidates: list[dict[str, Any]],
    trusted_lanes: dict[str, dict[str, Any]] | None,
    *,
    template_threshold: float,
) -> list[dict[str, Any]]:
    """Filter ambiguous visual brackets against independent lane evidence.

    Generic bracket geometry is intentionally disabled when no trusted bracket
    lane exists: Chinese body glyphs contain too many bracket-like connected
    components.  A dictionary template may still rescue such a page, but when
    it is the sole evidence it must clear a conservative 0.70 floor.
    """
    return _visual_evidence._apply_trusted_visual_marker_lanes(_visual_evidence_deps(), candidates, trusted_lanes, template_threshold=template_threshold)


def _detect_visual_entry_markers(
    gray: np.ndarray,
    median_height: float,
    left_limit: int,
    *,
    lower_bound: int = 0,
    inventory: dict[str, Any] | None = None,
    trusted_lanes: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Detect configured entry/bracket symbols directly from page pixels.

    The detector is dictionary-specific: only visual families implied by the
    active symbol inventory are considered. Unknown/custom literals remain OCR-
    only rather than being guessed from generic shapes.
    """
    return _visual_evidence._detect_visual_entry_markers(_visual_evidence_deps(), gray, median_height, left_limit, lower_bound=lower_bound, inventory=inventory, trusted_lanes=trusted_lanes)


def _match_visual_entry_markers_to_lines(
    lines: list[OCRLine],
    markers: list[dict[str, Any]],
    median_height: float,
) -> dict[int, dict[str, Any]]:
    """Pair visual ○/● markers with OCR rows on the same physical line."""
    return _visual_evidence._match_visual_entry_markers_to_lines(_visual_evidence_deps(), lines, markers, median_height)


def _parse_cjk_visual_marker_line(
    text: str,
    marker_symbol: str,
    settings: AppSettings,
    profile: DictionaryProfile,
) -> HeadwordParse | None:
    """Recover a marker-led CJK head when OCR omitted/misread the visual marker.

    The visual template itself supplies the entry-boundary evidence, so this
    rescue path does not require OCR to recover the configured Unicode marker.
    """
    return _visual_evidence._parse_cjk_visual_marker_line(_visual_evidence_deps(), text, marker_symbol, settings, profile)


def _parse_visual_configured_symbol_line(
    text: str,
    visual_symbol: dict[str, Any],
    settings: AppSettings,
    profile: DictionaryProfile,
) -> HeadwordParse | None:
    """Recover a configured fixed-symbol head when OCR lost the symbol itself."""
    return _visual_evidence._parse_visual_configured_symbol_line(_visual_evidence_deps(), text, visual_symbol, settings, profile)


def _leading_cjk_ideograph(text: str) -> str:
    """Return a CJK glyph only when it is the actual leading token.

    This helper is used only inside visually localized oversized-CJK rescue.
    Besides pinyin/variant tails it accepts a compact sense-number suffix such
    as 案1 / 暗2 (circled digits normalize to ASCII digits under NFKC). The
    image-level oversized-run gate remains mandatory.
    """
    return _visual_evidence._leading_cjk_ideograph(_visual_evidence_deps(), text)


def _cjk_visual_projection_runs(
    gray: np.ndarray,
    header_cutoff: int,
    settings: AppSettings,
    pixel_scale: float,
    *,
    relaxed: bool = False,
) -> tuple[int, list[tuple[int, int]]]:
    """Locate oversized single-character rows from image geometry alone.

    Chinese character dictionaries often print single-character entries at
    roughly twice the body-text height while compound entries use ordinary-size
    bracketed lines.  OCR segmentation can merge the large glyph with nearby
    pronunciation/variant text, so a left-strip row projection is a more stable
    way to recover the entry Y position.  This detector does *not* decide the
    word; it only supplies visual runs that must still be associated with OCR.
    """
    return _visual_evidence._cjk_visual_projection_runs(_visual_evidence_deps(), gray, header_cutoff, settings, pixel_scale, relaxed=relaxed)


def _cjk_right_context_metrics(
    gray: np.ndarray,
    run: tuple[int, int],
    zone_width: int,
    settings: AppSettings,
    *,
    header_cutoff: int = 0,
) -> dict[str, Any]:
    """Measure whitespace/sparsity immediately to the right of a large CJK run.

    Many dictionary designs give an oversized head character a locally sparse
    right side: pronunciation may occupy the upper part, while the lower/right
    area remains much emptier than ordinary body text.  The sampled width scales
    with the detected run height rather than fixed pixels so the cue survives DPI
    changes.  This is supporting evidence, never a standalone headword decision.
    """
    return _visual_evidence._cjk_right_context_metrics(_visual_evidence_deps(), gray, run, zone_width, settings, header_cutoff=header_cutoff)


def _cjk_right_context_features(metrics: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten right-context diagnostics into JSON-safe candidate features."""
    return _visual_evidence._cjk_right_context_features(_visual_evidence_deps(), metrics)


def _cjk_candidate_right_context_metrics(
    gray: np.ndarray,
    box: tuple[int, int, int, int],
    median_height: float,
    settings: AppSettings,
    *,
    header_cutoff: int = 0,
) -> dict[str, Any]:
    """Right-side layout evidence centered on an OCR single-Han candidate.

    This is the second path for large-head detection: it does not require the
    left-strip projection to have produced an oversized run first.  OCR can crop
    a real display glyph to body height, so estimate a plausible display-height
    window from the page-local median and inspect the area immediately to the
    right of the candidate itself.
    """
    return _visual_evidence._cjk_candidate_right_context_metrics(_visual_evidence_deps(), gray, box, median_height, settings, header_cutoff=header_cutoff)


def _cjk_candidate_right_context_features(
    metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Candidate-local right-context diagnostics with a non-colliding prefix."""
    return _visual_evidence._cjk_candidate_right_context_features(_visual_evidence_deps(), metrics)


def _cjk_word_for_visual_run(
    records: list[OCRRecord],
    run: tuple[int, int],
    zone_width: int,
    settings: AppSettings,
    profile: DictionaryProfile | None = None,
    right_context: dict[str, Any] | None = None,
) -> tuple[str, float, OCRRecord | None]:
    """Pick an OCR token that physically represents one oversized CJK glyph.

    The active Project Profile is passed through so a short ``漢字 + pinyin``
    OCR record can use the same structural parser as the ordinary OCR channel.
    This matters when OCR crops the large glyph vertically: strong profile
    structure may safely relax the visual-box gate, while unparsed fallback
    candidates remain deliberately strict.
    """
    return _visual_evidence._cjk_word_for_visual_run(_visual_evidence_deps(), records, run, zone_width, settings, profile=profile, right_context=right_context)



def _cjk_recovery_deps() -> _cjk_recovery.CjkRecoveryDeps:
    """Use current core symbols for OCR-recovery patch and cache compatibility."""
    return _cjk_recovery.CjkRecoveryDeps(
        _robust_record_line_height=_robust_record_line_height,
        _single_cjk_from_local_records=_single_cjk_from_local_records,
        _recover_oversized_cjk_ocr_records=_recover_oversized_cjk_ocr_records,
        _record_already_represents_oversized_run=_record_already_represents_oversized_run,
        _recover_image_first_oversized_cjk_records=_recover_image_first_oversized_cjk_records,
        _suppress_raw_records_shadowed_by_verified_cjk_recovery=_suppress_raw_records_shadowed_by_verified_cjk_recovery,
        refine_separator_y=refine_separator_y,
        refine_separator_y_adaptive=refine_separator_y_adaptive,
        refine_first_content_y=refine_first_content_y,
        parse_headword_text=parse_headword_text,
        _is_single_cjk_ideograph=_is_single_cjk_ideograph,
        _leading_cjk_ideograph=_leading_cjk_ideograph,
        _is_chinese_ocr=_is_chinese_ocr,
        _header_cutoff=_header_cutoff,
        _cjk_visual_projection_runs=_cjk_visual_projection_runs,
        get_paddle_engine=get_paddle_engine,
        run_paddle_band=run_paddle_band,
        _separator_analysis_x_bounds=_separator_analysis_x_bounds,
        _otsu_threshold=_otsu_threshold,
        _true_runs=_true_runs,
        normalize_page_rgb=normalize_page_rgb,
        _VERIFIED_OVERSIZED_CJK_RECOVERIES=_VERIFIED_OVERSIZED_CJK_RECOVERIES,
    )


def _robust_record_line_height(
    records: list[OCRRecord],
    settings: AppSettings,
) -> float:
    """Estimate ordinary OCR-line height while ignoring giant merged boxes."""
    return _cjk_recovery._robust_record_line_height(_cjk_recovery_deps(), records, settings)


def _single_cjk_from_local_records(
    records: list[OCRRecord],
    settings: AppSettings,
    profile: DictionaryProfile,
    *,
    max_left_x: int | None = None,
) -> tuple[str, float, str]:
    """Return the best single-Han head from a tightly cropped local OCR pass."""
    return _cjk_recovery._single_cjk_from_local_records(_cjk_recovery_deps(), records, settings, profile, max_left_x=max_left_x)


def _recover_oversized_cjk_ocr_records(
    records: list[OCRRecord],
    band: Image.Image,
    settings: AppSettings,
    profile: DictionaryProfile,
    *,
    engine: Any | None = None,
    pixel_scale: float = 1.0,
) -> tuple[list[OCRRecord], list[dict[str, Any]]]:
    """Split one pathological multi-entry OCR box into physical CJK heads.

    This path is intentionally narrow. It runs only when a left-edge OCR box is
    far taller than normal text *and* the page pixels show at least two separate
    oversized-glyph runs inside that same box. Each physical run then receives
    a small local Paddle pass, so a head entirely omitted from the giant-box
    transcription can still be recovered.
    """
    return _cjk_recovery._recover_oversized_cjk_ocr_records(_cjk_recovery_deps(), records, band, settings, profile, engine=engine, pixel_scale=pixel_scale)




_VERIFIED_OVERSIZED_CJK_RECOVERIES = {
    "oversized_multi_entry_local_ocr",
    "image_first_oversized_local_ocr",
}



def _record_already_represents_oversized_run(
    record: OCRRecord,
    run: tuple[int, int],
    zone_width: int,
    settings: AppSettings,
    profile: DictionaryProfile,
) -> bool:
    """Return True when an existing OCR row already represents this visual run.

    Giant or multi-line boxes are deliberately excluded because they are the
    failure mode the image-first channel is intended to bypass.
    """
    return _cjk_recovery._record_already_represents_oversized_run(_cjk_recovery_deps(), record, run, zone_width, settings, profile)


def _recover_image_first_oversized_cjk_records(
    records: list[OCRRecord],
    band: Image.Image,
    settings: AppSettings,
    profile: DictionaryProfile,
    *,
    engine: Any | None = None,
    pixel_scale: float = 1.0,
) -> tuple[list[OCRRecord], list[dict[str, Any]]]:
    """Recover large CJK heads from page pixels even when OCR has no good box.

    Image geometry only discovers possible oversized runs. Each unmatched run
    receives a tight local Paddle pass and is promoted only when that crop
    resolves to one leading Han headword. Decorative Latin initials therefore
    remain rejected while clipped, omitted, or out-of-parent-box CJK heads can
    become ordinary downstream candidates.
    """
    return _cjk_recovery._recover_image_first_oversized_cjk_records(_cjk_recovery_deps(), records, band, settings, profile, engine=engine, pixel_scale=pixel_scale)


def _suppress_raw_records_shadowed_by_verified_cjk_recovery(
    records: list[OCRRecord],
) -> tuple[list[OCRRecord], list[dict[str, Any]]]:
    """Drop raw OCR boxes that duplicate verified CJK recovery rows.

    Image-first recovery adds a synthetic single-Han record while preserving the
    immutable raw Paddle cache. Without derived-record dedup, that synthetic row
    can be merged back with its own source box, for example 摆 plus 摆1, or with
    a giant raw box spanning several recovered heads. Suppression affects only
    the effective derived record list; the raw cache remains untouched.
    """
    return _cjk_recovery._suppress_raw_records_shadowed_by_verified_cjk_recovery(_cjk_recovery_deps(), records)


def refine_separator_y(
    gray: np.ndarray,
    coarse_y: int,
    line_height: int,
    settings: AppSettings,
    pixel_scale: float = 1.0,
    lower_bound: int = 0,
) -> tuple[int, dict[str, Any]]:
    """Refine a coarse headword marker using a local horizontal ink valley.

    ``coarse_y`` is the OCR-derived marker position in the straightened column
    band.  Around it we inspect each row's black-pixel proportion.  A small
    vertical safety band is averaged so a one-pixel hole inside a descender is
    not mistaken for inter-line whitespace.  The returned Y is the centre of
    the contiguous near-minimum valley that contains the global minimum.

    This intentionally remains a *local* correction: OCR decides which text
    line is the headword, while projection only nudges the marker to the safest
    whitespace between the preceding line and the current one.
    """
    return _cjk_recovery.refine_separator_y(_cjk_recovery_deps(), gray, coarse_y, line_height, settings, pixel_scale=pixel_scale, lower_bound=lower_bound)


def refine_separator_y_adaptive(
    gray: np.ndarray,
    coarse_y: int,
    reference_line_height: int,
    settings: AppSettings,
    pixel_scale: float = 1.0,
    lower_bound: int = 0,
    content_top: int | None = None,
    preceding_gap_hint: int | None = None,
    fallback_refiner: Any | None = None,
) -> tuple[int, dict[str, Any]]:
    """Trace the nearest blank band above a CJK entry.

    ``preceding_gap_hint`` remains for compatibility/diagnostics. When dense
    print has no stable blank run, ``fallback_refiner`` selects the local-valley
    fallback without changing the adaptive geometry policy.
    """
    return _cjk_recovery.refine_separator_y_adaptive(_cjk_recovery_deps(), gray, coarse_y, reference_line_height, settings, pixel_scale=pixel_scale, lower_bound=lower_bound, content_top=content_top, preceding_gap_hint=preceding_gap_hint, fallback_refiner=fallback_refiner)


def refine_first_content_y(
    gray: np.ndarray,
    coarse_y: int,
    line_height: int,
    settings: AppSettings,
    pixel_scale: float = 1.0,
    lower_bound: int = 0,
) -> tuple[int, dict[str, Any]]:
    """Place the first entry marker at the onset of the first sustained ink run.

    The first printed entry has no preceding text line, so an inter-line valley
    does not exist.  Using the normal valley algorithm either keeps a slightly
    inaccurate OCR top or, on older versions, could drift upward into the large
    blank margin.  For this special case we scan downward around the OCR top and
    choose the first Y at which printed ink persists for several consecutive
    rows.  This follows the user's requested "first continuous-ink Y" rule.
    """
    return _cjk_recovery.refine_first_content_y(_cjk_recovery_deps(), gray, coarse_y, line_height, settings, pixel_scale=pixel_scale, lower_bound=lower_bound)



def _header_cutoff(gray: np.ndarray, settings: AppSettings, ratio: float) -> int:
    """Return band Y below a strong running-header separator, or zero."""
    if not settings.paddle_auto_header_rule or gray.size == 0:
        return 0
    search_height = min(gray.shape[0], max(1, round(settings.paddle_header_search_height * ratio)))
    if search_height <= 1:
        return 0
    dark = gray[:search_height] < 180
    row_ink = dark.mean(axis=1)
    active = row_ink >= min(0.98, max(0.05, settings.paddle_header_rule_ink_ratio))
    runs = _true_runs(active)
    if not runs:
        return 0
    # A real horizontal rule should survive on at least one full scan row.
    # Use the last qualifying rule in the top search zone; this handles a
    # double rule without treating the running-header text itself as a rule.
    _, end = runs[-1]
    return min(gray.shape[0], end + max(0, round(settings.paddle_header_rule_margin * ratio)))


def _accepted_cjk_row_for_visual_run(
    diagnostics: list[dict[str, Any]],
    run_start: int,
    run_end: int,
    word: str,
) -> dict[str, Any] | None:
    """Find an already accepted CJK row that belongs to the same visual glyph.

    The OCR/grammar path stores the *refined separator Y* as the entry marker,
    while visual projection starts from the glyph's ink run.  Comparing those
    two marker Y values directly is therefore unreliable.  Compare the original
    OCR box against the visual run instead; this is the physical evidence that
    both candidates describe the same printed character.
    """
    run_h = max(1, run_end - run_start)
    run_center = (run_start + run_end) / 2.0
    for row in diagnostics:
        if "meta" in row or not row.get("accepted"):
            continue
        lemma = str(row.get("normalized_headword", ""))
        features = row.get("features", {}) or {}
        if not (_is_single_cjk_ideograph(lemma) or features.get("cjk_single_visual")):
            continue
        box = row.get("box") or []
        if not isinstance(box, list) or len(box) != 4:
            continue
        y0, y1 = int(box[1]), int(box[3])
        box_h = max(1, y1 - y0)
        overlap = max(0, min(y1, run_end) - max(y0, run_start))
        center_distance = abs(((y0 + y1) / 2.0) - run_center)
        same_word = bool(word and lemma and word == lemma)
        same_physical_row = (
            overlap >= min(box_h, run_h) * 0.22
            or center_distance <= max(box_h, run_h) * 0.62
        )
        # OCR sometimes places the accepted single-Han box on the pinyin/baseline
        # rather than around the full display glyph.  If the normalized lemma is
        # the same, allow a wider vertical association so the later visual rescue
        # confirms the existing candidate instead of creating a second separator
        # inside the same entry.  Nearby repeated homographs remain distinct
        # because this relaxed window is still bounded to roughly one glyph.
        same_word_shifted_box = bool(
            same_word
            and center_distance <= max(run_h * 1.45, box_h * 1.6)
        )
        if (
            (same_physical_row and (same_word or features.get("cjk_single_visual")))
            or same_word_shifted_box
        ):
            return row
    return None


def _selected_tail_structure_evidence(
    settings: AppSettings,
    parsed: HeadwordParse | None,
    *,
    pos_allowed_by_rules: bool = True,
) -> tuple[tuple[str, ...], dict[str, bool]]:
    """Return only the post-lemma evidence families selected by the user.

    Version 0 mirrors the historical hidden gate (POS / inflection /
    descriptor). Version 1 makes each family explicit in Project Profile.
    """
    pronunciation = bool(
        parsed
        and any(
            str(item).startswith("pronunciation:")
            for item in parsed.parser_trace
        )
    )
    available = {
        "pos": bool(parsed and parsed.has_pos and pos_allowed_by_rules),
        "inflection": bool(parsed and parsed.has_inflection),
        "variant": bool(parsed and parsed.variants),
        "pronunciation": pronunciation,
        "descriptor": bool(parsed and parsed.has_descriptor),
    }
    if int(getattr(settings, "profile_tail_structure_version", 0) or 0) < 1:
        selected = {
            "pos": available["pos"],
            "inflection": available["inflection"],
            "variant": False,
            "pronunciation": False,
            "descriptor": available["descriptor"],
        }
    else:
        selected = {
            "pos": available["pos"] and bool(
                getattr(settings, "profile_tail_allow_pos", True)
            ),
            "inflection": available["inflection"] and bool(
                getattr(settings, "profile_tail_allow_inflection", True)
            ),
            "variant": available["variant"] and bool(
                getattr(settings, "profile_tail_allow_variant", True)
            ),
            "pronunciation": available["pronunciation"] and bool(
                getattr(settings, "profile_tail_allow_pronunciation", False)
            ),
            "descriptor": available["descriptor"] and bool(
                getattr(settings, "profile_tail_allow_descriptor", True)
            ),
        }
    names = tuple(name for name, present in selected.items() if present)
    diagnostics = {
        **{f"available_{name}": value for name, value in available.items()},
        **{f"selected_{name}": value for name, value in selected.items()},
    }
    return names, diagnostics


def _ordinary_visual_rescue_thresholds(
    settings: AppSettings,
) -> dict[str, float | str]:
    """Resolve thresholds used by ordinary left-edge visual rescue.

    Saved Project Profile tail controls (version >= 1) are fully explicit:
    rescue uses the same visible boldness threshold shown in the headword
    specificity panel. Left-edge tolerance and candidate-score thresholds are
    already applied by the ordinary candidate gate. No extra hidden height,
    boldness, or confidence threshold is added for saved explicit Profiles.

    Version 0 keeps the historical thresholds only for backward compatibility
    with projects that have not yet saved the new Profile controls.
    """
    explicit = int(
        getattr(settings, "profile_tail_structure_version", 0) or 0
    ) >= 1
    if explicit:
        return {
            "source": "visible_profile_specificity",
            "boldness": float(settings.paddle_boldness_ratio),
            "height": 0.0,
            "confidence": float(settings.paddle_rec_score_threshold),
        }
    return {
        "source": "legacy_hidden_thresholds",
        "boldness": max(
            float(getattr(settings, "paddle_strong_edge_visual_boldness_ratio", 1.22) or 1.22),
            float(settings.paddle_boldness_ratio) * 1.03,
        ),
        "height": max(
            0.75,
            float(getattr(settings, "paddle_strong_edge_visual_height_ratio", 0.90) or 0.90),
        ),
        "confidence": max(
            float(settings.paddle_rec_score_threshold),
            float(getattr(settings, "paddle_strong_edge_visual_min_confidence", 0.55) or 0.55),
        ),
    }


def _ordinary_strong_edge_visual_rescue(
    settings: AppSettings,
    parsed: HeadwordParse | None,
    *,
    at_left: bool,
    below_header: bool,
    boldness_ratio: float,
    height_ratio: float,
    confidence: float,
    looks_like_continuation: bool,
    marker_noise: bool,
) -> bool:
    """Recover a left-edge head when selected post-lemma OCR evidence fails.

    For saved explicit Profiles this path obeys the user-visible specificity
    controls instead of layering another hidden strong-edge threshold on top.
    Semantic guards remain: parsed lemma, strict left edge, body region, and
    no continuation/noise signal.
    """
    tail_controls_active = int(
        getattr(settings, "profile_tail_structure_version", 0) or 0
    ) >= 1
    rescue_enabled = (
        bool(getattr(settings, "profile_tail_allow_visual_rescue", False))
        if tail_controls_active
        else bool(getattr(settings, "paddle_allow_strong_edge_visual_rescue", False))
    )
    if not rescue_enabled:
        return False
    if (
        parsed is None
        or not parsed.normalized
        or len(parsed.normalized.strip("-")) < 3
        or not at_left
        or not below_header
        or looks_like_continuation
        or marker_noise
    ):
        return False

    thresholds = _ordinary_visual_rescue_thresholds(settings)
    return bool(
        boldness_ratio >= float(thresholds["boldness"])
        and height_ratio >= float(thresholds["height"])
        and confidence >= float(thresholds["confidence"])
    )


def _headword_filter_deps() -> _headword_filter.HeadwordFilterDeps:
    """Resolve original OCR filter patch seams and dictionaries at call time."""
    return _headword_filter.HeadwordFilterDeps(
        evaluate_headword_filter_rules=evaluate_headword_filter_rules,
        _headword_script_compatibility=_headword_script_compatibility,
        _is_chinese_ocr=_is_chinese_ocr,
        _configured_symbol_inventory=_configured_symbol_inventory,
        _is_single_cjk_ideograph=_is_single_cjk_ideograph,
        group_ocr_records=group_ocr_records,
        _repair_split_headword_lines=_repair_split_headword_lines,
        _repair_wrapped_headword_structure=_repair_wrapped_headword_structure,
        _repair_multiline_headword_state_machine=_repair_multiline_headword_state_machine,
        _compile_patterns=_compile_patterns,
        parse_headword_text=parse_headword_text,
        _looks_like_marker_noise_lemma=_looks_like_marker_noise_lemma,
        _ink_ratio=_ink_ratio,
        _leading_box=_leading_box,
        detect_image_separator_candidates=detect_image_separator_candidates,
        match_ocr_lines_to_image_boundaries=match_ocr_lines_to_image_boundaries,
        _trusted_visual_marker_lanes=_trusted_visual_marker_lanes,
        _detect_visual_entry_markers=_detect_visual_entry_markers,
        _match_visual_entry_markers_to_lines=_match_visual_entry_markers_to_lines,
        _parse_visual_configured_symbol_line=_parse_visual_configured_symbol_line,
        _cjk_visual_projection_runs=_cjk_visual_projection_runs,
        _cjk_right_context_metrics=_cjk_right_context_metrics,
        _cjk_right_context_features=_cjk_right_context_features,
        _cjk_candidate_right_context_metrics=_cjk_candidate_right_context_metrics,
        _cjk_candidate_right_context_features=_cjk_candidate_right_context_features,
        _cjk_word_for_visual_run=_cjk_word_for_visual_run,
        _recover_oversized_cjk_ocr_records=_recover_oversized_cjk_ocr_records,
        refine_separator_y=refine_separator_y,
        refine_separator_y_adaptive=refine_separator_y_adaptive,
        refine_first_content_y=refine_first_content_y,
        _header_cutoff=_header_cutoff,
        _accepted_cjk_row_for_visual_run=_accepted_cjk_row_for_visual_run,
        _selected_tail_structure_evidence=_selected_tail_structure_evidence,
        _ordinary_visual_rescue_thresholds=_ordinary_visual_rescue_thresholds,
        _ordinary_strong_edge_visual_rescue=_ordinary_strong_edge_visual_rescue,
        _annotate_peer_typography_matches=_annotate_peer_typography_matches,
        _BUNDLED_PROFILE=_BUNDLED_PROFILE,
        _VERIFIED_OVERSIZED_CJK_RECOVERIES=_VERIFIED_OVERSIZED_CJK_RECOVERIES,
        Entry=Entry,
        load_dictionary_profile=load_dictionary_profile,
        leading_relation_label=leading_relation_label,
        starts_with_internal_article_symbol=starts_with_internal_article_symbol,
    )


def filter_headword_records(
    records: list[OCRRecord],
    band: Image.Image,
    source_top: int,
    source_column_x: int,
    settings: AppSettings,
    separator_band: Image.Image | None = None,
    user_rules: list[HeadwordFilterRule] | None = None,
    engine_name: str = "paddle",
    profile: DictionaryProfile | None = None,
    pixel_scale: float | None = None,
    peer_typography_annotator: Any | None = None,
    separator_y_refiner: Any | None = None,
) -> tuple[list[Entry], list[dict[str, Any]]]:
    """Select dictionary headwords using structure, geometry and visual cues.

    The strongest signals are now: left alignment + lemma syntax + a nearby
    part-of-speech label. Size, ink density/boldness, special symbols and the
    gap before a line remain fallback evidence for entries without a POS label.
    """
    return _headword_filter.filter_headword_records(
        _headword_filter_deps(),
        records, band, source_top, source_column_x, settings,
        separator_band=separator_band,
        user_rules=user_rules,
        engine_name=engine_name,
        profile=profile,
        pixel_scale=pixel_scale,
        peer_typography_annotator=peer_typography_annotator,
        separator_y_refiner=separator_y_refiner,
    )



def _median_and_mad(values: list[float]) -> tuple[float, float]:
    """Return robust center/spread for page-local typography evidence."""
    if not values:
        return 0.0, 0.0
    array = np.asarray(values, dtype=float)
    median = float(np.median(array))
    mad = float(np.median(np.abs(array - median)))
    return median, mad


def _annotate_peer_typography_matches(
    diagnostics: list[dict[str, Any]],
) -> int:
    """Mark soft rejects that match the page's accepted headword typography.

    This is deliberately an annotation pass, not a direct acceptance pass.
    High-confidence accepted rows establish a page-local visual prototype.
    Borderline rows can then contribute this *independent* typography evidence
    to later multi-engine arbitration, which still requires an image boundary
    and the usual semantic safety guards before rescue.
    """
    anchors: list[dict[str, Any]] = []
    for row in diagnostics:
        if "meta" in row or not row.get("accepted"):
            continue
        features = row.get("features", {}) or {}
        if not isinstance(features, dict):
            continue
        try:
            confidence = float(row.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < 0.88:
            continue
        if features.get("forced_accept") or features.get("marker_noise"):
            continue
        if features.get("looks_like_continuation"):
            continue
        if not features.get("at_left", True):
            continue
        anchors.append(row)

    if len(anchors) < 4:
        return 0

    def feature_values(name: str) -> list[float]:
        values: list[float] = []
        for row in anchors:
            features = row.get("features", {}) or {}
            try:
                values.append(float(features.get(name)))
            except (TypeError, ValueError):
                pass
        return values

    height_center, height_mad = _median_and_mad(feature_values("height_ratio"))
    bold_center, bold_mad = _median_and_mad(feature_values("boldness_ratio"))
    gap_center, gap_mad = _median_and_mad(feature_values("preceding_gap"))

    soft_reasons = {
        "missing_pos_inflection_descriptor_or_symbol",
        "missing_selected_tail_structure",
        "score_below_threshold",
        "missing_structure_or_visual_cue",
        "candidate_rejected",
        "cjk_single_needs_stronger_visual_evidence",
        "cjk_single_not_visually_prominent",
        "cjk_bracket_needs_visual_evidence",
    }
    hard_flags = {
        "forced_reject",
        "marker_noise",
        "looks_like_continuation",
        "internal_article_symbol",
        "internal_relation_label",
        "internal_locution",
    }

    matched = 0
    for row in diagnostics:
        if "meta" in row or row.get("accepted"):
            continue
        reason = str(row.get("reject_reason", "") or "")
        if reason not in soft_reasons:
            continue
        if not str(row.get("normalized_headword", "") or "").strip():
            continue
        try:
            confidence = float(row.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < 0.68:
            continue
        features = row.get("features", {}) or {}
        if not isinstance(features, dict):
            continue
        if any(bool(features.get(name)) for name in hard_flags):
            continue
        if not features.get("at_left", False) or not features.get("below_header", True):
            continue
        if not features.get("image_boundary_supported", False):
            continue

        votes = 0
        details: dict[str, float | int] = {}

        def close_vote(
            name: str,
            center: float,
            mad: float,
            absolute_floor: float,
            *,
            lower_ratio: float | None = None,
        ) -> None:
            nonlocal votes
            try:
                value = float(features.get(name))
            except (TypeError, ValueError):
                return
            tolerance = max(float(absolute_floor), 3.5 * float(mad))
            if lower_ratio is not None and center > 0 and value < center * lower_ratio:
                details[f"peer_{name}_delta"] = round(value - center, 4)
                return
            if abs(value - center) <= tolerance:
                votes += 1
            details[f"peer_{name}_delta"] = round(value - center, 4)
            details[f"peer_{name}_tolerance"] = round(tolerance, 4)

        close_vote("height_ratio", height_center, height_mad, 0.14, lower_ratio=0.78)
        close_vote("boldness_ratio", bold_center, bold_mad, 0.12, lower_ratio=0.72)

        # Gap is useful only when the accepted typography has a stable rhythm.
        # On heterogeneous pages a large MAD automatically makes this cue weak.
        if gap_center > 0:
            gap_floor = max(2.0, gap_center * 0.20)
            close_vote("preceding_gap", gap_center, gap_mad, gap_floor)

        if votes < 2:
            continue

        features["peer_typography_match"] = True
        features["peer_typography_votes"] = int(votes)
        features["peer_typography_anchor_count"] = int(len(anchors))
        features["peer_typography_height_center"] = round(height_center, 4)
        features["peer_typography_boldness_center"] = round(bold_center, 4)
        features["peer_typography_gap_center"] = round(gap_center, 3)
        features.update(details)
        trace = row.setdefault("parser_trace", [])
        if "peer_typography_match" not in trace:
            trace.append("peer_typography_match")
        bugs = row.setdefault("bug_types", [])
        if "PEER_TYPOGRAPHY_MATCH" not in bugs:
            bugs.append("PEER_TYPOGRAPHY_MATCH")
        matched += 1
    return matched


def _attach_source_candidate_coordinates(
    diagnostics: list[dict[str, Any]],
    geometry: "Geometry",
    column: int,
) -> None:
    """Attach original-image X/Y while keeping reading-axis values private."""
    for item in diagnostics:
        if "meta" in item:
            meta = item.get("meta") or {}
            meta["coordinate_space"] = "source_image_pixels"
            if meta.get("_header_cutoff_axis_v") is not None:
                try:
                    axis_v = int(meta["_header_cutoff_axis_v"])
                    axis_u = int(geometry.x_at(column, axis_v))
                    sx, sy = geometry.canonical_to_source(axis_u, axis_v)
                    meta["header_cutoff_source_x"] = int(sx)
                    meta["header_cutoff_source_y"] = int(sy)
                except (TypeError, ValueError):
                    pass
            continue

        # Low-level filtering works on a temporary transformed reading axis.
        # Keep that fact private; every public/cache coordinate is source X/Y.
        try:
            axis_v = int(item.get("_axis_v", item.get("_axis_v", item.get("source_y", 0))))
        except (TypeError, ValueError):
            axis_v = 0
        try:
            coarse_axis_v = int(item.get("_coarse_axis_v", item.get("coarse_canonical_v", item.get("coarse_source_y", axis_v))))
        except (TypeError, ValueError):
            coarse_axis_v = axis_v
        try:
            anchor_axis_v = int(item.get("_anchor_axis_v", item.get("anchor_canonical_v", item.get("anchor_source_y", coarse_axis_v))))
        except (TypeError, ValueError):
            anchor_axis_v = coarse_axis_v

        axis_u = int(geometry.x_at(column, axis_v))
        source_x, source_y = geometry.canonical_to_source(axis_u, axis_v)
        coarse_axis_u = int(geometry.x_at(column, coarse_axis_v))
        coarse_source_x, coarse_source_y = geometry.canonical_to_source(
            coarse_axis_u, coarse_axis_v
        )
        anchor_axis_u = int(geometry.x_at(column, anchor_axis_v))
        anchor_source_x, anchor_source_y = geometry.canonical_to_source(
            anchor_axis_u, anchor_axis_v
        )

        item["_axis_v"] = axis_v
        item["_coarse_axis_v"] = coarse_axis_v
        item["_anchor_axis_v"] = anchor_axis_v
        for key in ("canonical_u", "canonical_v", "coarse_canonical_v", "anchor_canonical_v", "canonical_coordinate_space"):
            item.pop(key, None)
        item["coordinate_space"] = "source_image_pixels"
        item["source_x"] = int(source_x)
        item["source_y"] = int(source_y)
        item["coarse_source_x"] = int(coarse_source_x)
        item["coarse_source_y"] = int(coarse_source_y)
        item["anchor_source_x"] = int(anchor_source_x)
        item["anchor_source_y"] = int(anchor_source_y)


def _candidate_axis_v(candidate: dict[str, Any] | None) -> int | None:
    if not candidate:
        return None
    value = candidate.get("_axis_v", candidate.get("source_y"))
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_only_persistence(value: Any) -> Any:
    """Strip temporary transformed-axis fields before writing cache/debug JSON."""
    if isinstance(value, list):
        return [_source_only_persistence(item) for item in value]
    if isinstance(value, tuple):
        return [_source_only_persistence(item) for item in value]
    if not isinstance(value, dict):
        return value

    result: dict[str, Any] = {}
    for key, item in value.items():
        name = str(key)
        if name.startswith("_") or "canonical" in name.casefold():
            continue
        if name in {"column_coordinate_space", "coordinate_spaces"}:
            continue
        result[name] = _source_only_persistence(item)

    # Engine/member Y fields are page coordinates in persisted output and must
    # therefore equal their explicit source-image Y.
    if result.get("source_y") is not None and "y" in result:
        result["y"] = result["source_y"]
    for prefix in ("paddle", "tesseract", "lens"):
        source_key = f"{prefix}_source_y"
        axis_key = f"{prefix}_y"
        if result.get(source_key) is not None and axis_key in result:
            result[axis_key] = result[source_key]
        coarse_source_key = f"{prefix}_coarse_source_y"
        coarse_key = f"{prefix}_coarse_y"
        if result.get(coarse_source_key) is not None and coarse_key in result:
            result[coarse_key] = result[coarse_source_key]
        anchor_source_key = f"{prefix}_anchor_source_y"
        anchor_key = f"{prefix}_anchor_y"
        if result.get(anchor_source_key) is not None and anchor_key in result:
            result[anchor_key] = result[anchor_source_key]
    return result


def _image_cache_fingerprint(image: Image.Image) -> str:
    """Return an exact normalized-pixel hash for raw OCR cache invalidation."""
    rgb = normalize_page_rgb(image)
    digest = hashlib.sha256()
    digest.update(f"{rgb.width}x{rgb.height}|RGB|".encode("ascii"))
    digest.update(rgb.tobytes())
    return digest.hexdigest()


def _cache_signature(image: Image.Image, geometry: "Geometry", settings: AppSettings) -> str:
    from .ocr.paddle_raw_cache_signature import cache_signature
    return cache_signature(
        image, geometry, settings,
        image_fingerprint=_image_cache_fingerprint,
        paddle_language=_paddle_language,
        raw_threshold=_RAW_OCR_THRESHOLD,
    )


def _records_as_merged_lines(records: list[OCRRecord], settings: AppSettings) -> list[OCRLine]:
    return group_ocr_records([record for record in records if record.text], settings.paddle_line_merge_y_ratio)


def _candidate_rows(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in diagnostics if "meta" not in item]


def _alphabetical_sort_key(word: str) -> str:
    """Keep the historical annotation-only dictionary collation helper."""
    return _alphabetical_warnings.alphabetical_sort_key(word, unicode_data=unicodedata)


def _annotate_alphabetical_warnings(
    report_columns: list[dict[str, Any]],
    page_sections: list[PageSection] | None = None,
    *,
    top_v: int | None = None,
    bottom_v: int | None = None,
) -> list[dict[str, Any]]:
    """Flag diagnostic order anomalies; never alter acceptance decisions."""
    return _alphabetical_warnings.annotate_alphabetical_warnings(
        report_columns, page_sections, top_v=top_v, bottom_v=bottom_v,
        candidate_rows_fn=_candidate_rows,
        axis_fn=_candidate_axis_v,
        sort_key_fn=_alphabetical_sort_key,
        section_fn=section_index_for_v,
        normalize_fn=normalize_page_sections,
    )


def _apply_alphabetical_warnings_to_entries(
    report_columns: list[dict[str, Any]], entries: list[Entry], tolerance: int = 5,
) -> None:
    return _alphabetical_warnings.apply_alphabetical_warnings_to_entries(
        report_columns, entries, tolerance=tolerance,
        candidate_rows_fn=_candidate_rows,
    )

def _ocr_pairing_deps() -> _ocr_pairing.OcrPairingDeps:
    """Snapshot current monkeypatchable matching operations for this call."""
    return _ocr_pairing.OcrPairingDeps(
        _candidate_axis_v=_candidate_axis_v,
        _candidate_rows=_candidate_rows,
        _alignment_key=_alignment_key,
        _lemma_similarity=_lemma_similarity,
        _orthographic_similarity=_orthographic_similarity,
        _eligible_alignment_rows=_eligible_alignment_rows,
        _candidate_pair_score=_candidate_pair_score,
        _pair_ocr_candidates=_pair_ocr_candidates,
        _pairs_need_lens=_pairs_need_lens,
        _make_ocr_pair=_make_ocr_pair,
        _copy_candidate_to_pair=_copy_candidate_to_pair,
        _pair_with_lens_candidates=_pair_with_lens_candidates,
        _engine_quality=_engine_quality,
        _stable_candidate_id=_stable_candidate_id,
        _issues_for_pair=_issues_for_pair,
        _arbitrate_pair=_arbitrate_pair,
        _apply_pair_engine_position=_apply_pair_engine_position,
        _agreement_summary=_agreement_summary,
    )


def _alignment_key(word: str) -> str:
    """Return a Unicode-safe OCR alignment key.

    v2.8.1 accidentally reduced alignment to ASCII letters/digits, which made
    every Han headword collapse to the empty key.  That could mis-pair Chinese
    OCR rows and, in turn, leave two review candidates for one physical glyph.
    Preserve all Unicode alphanumeric characters while still discarding
    punctuation/spacing and combining marks.
    """
    return _ocr_pairing._alignment_key(_ocr_pairing_deps(), word)


def _lemma_similarity(left: str, right: str) -> float:
    return _ocr_pairing._lemma_similarity(_ocr_pairing_deps(), left, right)


def _orthographic_similarity(left: str, right: str) -> float:
    """Compare final spellings while preserving meaningful Spanish diacritics."""
    return _ocr_pairing._orthographic_similarity(_ocr_pairing_deps(), left, right)


def _eligible_alignment_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _ocr_pairing._eligible_alignment_rows(_ocr_pairing_deps(), rows)


def _candidate_pair_score(p: dict[str, Any], t: dict[str, Any], tolerance: int) -> float:
    return _ocr_pairing._candidate_pair_score(_ocr_pairing_deps(), p, t, tolerance)


def _pair_ocr_candidates(
    paddle_diagnostics: list[dict[str, Any]],
    tess_diagnostics: list[dict[str, Any]],
    tolerance: int,
    min_similarity: float = 0.55,
) -> list[dict[str, Any]]:
    """Align Paddle/Tesseract candidate sequences using lemma order + Y.

    SequenceMatcher first anchors stable equal subsequences. Replace blocks are
    then matched by a combined lemma-similarity/Y score. This prevents a single
    missing OCR row from shifting every subsequent nearest-Y pairing.
    """
    return _ocr_pairing._pair_ocr_candidates(_ocr_pairing_deps(), paddle_diagnostics, tess_diagnostics, tolerance, min_similarity=min_similarity)


def _pairs_need_lens(pairs: list[dict[str, Any]]) -> bool:
    """Return whether the remote third opinion could change/review a decision."""
    return _ocr_pairing._pairs_need_lens(_ocr_pairing_deps(), pairs)


def _make_ocr_pair(
    p: dict[str, Any] | None,
    t: dict[str, Any] | None,
    alignment_method: str = "",
) -> dict[str, Any]:
    return _ocr_pairing._make_ocr_pair(_ocr_pairing_deps(), p, t, alignment_method=alignment_method)


def _copy_candidate_to_pair(pair: dict[str, Any], prefix: str, candidate: dict[str, Any]) -> None:
    return _ocr_pairing._copy_candidate_to_pair(_ocr_pairing_deps(), pair, prefix, candidate)


def _pair_with_lens_candidates(
    pairs: list[dict[str, Any]],
    lens_diagnostics: list[dict[str, Any]],
    tolerance: int,
    min_similarity: float,
) -> list[dict[str, Any]]:
    """Attach Lens rows to the existing Paddle/Tesseract sequence alignment."""
    return _ocr_pairing._pair_with_lens_candidates(_ocr_pairing_deps(), pairs, lens_diagnostics, tolerance, min_similarity=min_similarity)


def _engine_quality(pair: dict[str, Any], prefix: str) -> float:
    return _ocr_pairing._engine_quality(_ocr_pairing_deps(), pair, prefix)


def _stable_candidate_id(column: int, y: int, ptext: str, ttext: str) -> str:
    return _ocr_pairing._stable_candidate_id(_ocr_pairing_deps(), column, y, ptext, ttext)


def _issues_for_pair(pair: dict[str, Any], chosen: str, needs_review: bool) -> list[str]:
    return _ocr_pairing._issues_for_pair(_ocr_pairing_deps(), pair, chosen, needs_review)


def _arbitrate_pair(
    pair: dict[str, Any],
    column: int,
    canonical_u: int,
    settings: AppSettings,
    *,
    geometry: "Geometry" | None = None,
) -> dict[str, Any]:
    return _ocr_pairing._arbitrate_pair(_ocr_pairing_deps(), pair, column, canonical_u, settings, geometry=geometry)


def _apply_pair_engine_position(
    item: dict[str, Any],
    pair: dict[str, Any],
    prefix: str,
    column: int,
    canonical_u: int,
    geometry: "Geometry" | None,
) -> None:
    """Apply one engine's position without mixing temporary reading axis and source Y."""
    return _ocr_pairing._apply_pair_engine_position(_ocr_pairing_deps(), item, pair, prefix, column, canonical_u, geometry)


def _agreement_summary(review_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return _ocr_pairing._agreement_summary(_ocr_pairing_deps(), review_candidates)



_QUALITY_SUMMARY_LOCK = threading.Lock()


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Publish OCR/cache text atomically and remove failed temporary files."""
    _cache_atomic_write_text_impl(path, text, encoding=encoding)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write machine-owned OCR JSON compactly while honoring core overrides."""
    _cache_atomic_write_json_impl(
        path,
        payload,
        write_text=_atomic_write_text,
    )


_OCR_REGENERABLE_SIDECAR_SUFFIXES = (
    "_ocr_diagnostics.txt",
    "_ocr_comparison.txt",
    "_issues.tsv",
    "_ocr_engines.tsv",
    "_fusion.tsv",
)


def _compact_cached_candidate(row: Any) -> Any:
    """Keep only candidate fields required by Profile coverage diagnostics."""
    return _cache_compact_cached_candidate_impl(
        row,
        source_only=_source_only_persistence,
    )


def compact_ocr_cache_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the reusable OCR cache in compact persisted representation."""
    return _cache_compact_ocr_cache_payload_impl(
        payload,
        source_only=_source_only_persistence,
        compact_candidate=_compact_cached_candidate,
    )


def _regenerable_sidecars(cache_path: Path) -> list[Path]:
    return _cache_regenerable_sidecars_impl(
        cache_path,
        suffixes=_OCR_REGENERABLE_SIDECAR_SUFFIXES,
    )


def compact_ocr_cache_file(cache_path: Path) -> tuple[int, int, int]:
    """Compact one page cache while preserving core monkeypatch semantics."""
    return _cache_compact_ocr_cache_file_impl(
        cache_path,
        sidecar_paths=_regenerable_sidecars,
        compact_payload=compact_ocr_cache_payload,
        write_json=_atomic_write_json,
    )

def _tsv_clean(value: Any) -> str:
    return _diag_tsv_clean_impl(value)


def _candidate_reason(cand: dict[str, Any]) -> str:
    return _diag_candidate_reason_impl(cand)


def _candidate_tsv_row(
    column: int,
    cand: dict[str, Any],
    raw_status: str | None = None,
    engine: str = "",
    extra_reason: str = "",
) -> str:
    return _diag_candidate_tsv_row_impl(
        column,
        cand,
        raw_status=raw_status,
        engine=engine,
        extra_reason=extra_reason,
        clean=_tsv_clean,
        reason_builder=_candidate_reason,
    )


_DIAGNOSTIC_HEADER = "column\tbox_band_xyxy\tconf\ttext\taccept/reject\tscore\tlemma\traw\tcorrected\tPOS\trepairs\treason"
_COMPARISON_HEADER = (
    "column\tpaddle_source_y\tpaddle_box_band_xyxy\tpaddle_conf\tpaddle_accept/reject\tpaddle_score\t"
    "paddle_lemma\tpaddle_raw\tpaddle_corrected\tpaddle_POS\tpaddle_repairs\tpaddle_text\t"
    "tesseract_source_y\ttesseract_box_band_xyxy\ttesseract_conf\ttesseract_accept/reject\ttesseract_score\t"
    "tesseract_lemma\ttesseract_raw\ttesseract_corrected\ttesseract_POS\ttesseract_repairs\t"
    "tesseract_text\tdelta_source_y\tlemma_compare\tstatus_compare\treason"
)


def _diagnostic_text(report_columns: list[dict[str, Any]]) -> str:
    return _diag_diagnostic_text_impl(
        report_columns,
        header=_DIAGNOSTIC_HEADER,
        candidate_rows=_candidate_rows,
        candidate_row=_candidate_tsv_row,
        clean=_tsv_clean,
    )


def _comparison_text(report_columns: list[dict[str, Any]]) -> str:
    return _diag_comparison_text_impl(
        report_columns,
        header=_COMPARISON_HEADER,
        clean=_tsv_clean,
    )


_ENGINES_LONG_HEADER = (
    "pair_id\tcolumn\tsource_y\tengine\tconf\ttext\tlemma\tPOS\tscore\trepairs\tparser_trace\taccepted\treason"
)


def _engines_long_text(report_columns: list[dict[str, Any]]) -> str:
    return _diag_engines_long_text_impl(
        report_columns,
        header=_ENGINES_LONG_HEADER,
        clean=_tsv_clean,
    )


_FUSION_HEADER = (
    "pair_id\tcolumn\tsource_y\tengines\tselected\tfinal_lemma\tfinal_engine\tconfidence\t"
    "score\tneeds_review\tissues\tdecision_reason"
)


def _fusion_text(review_candidates: list[dict[str, Any]]) -> str:
    return _diag_fusion_text_impl(
        review_candidates,
        header=_FUSION_HEADER,
        clean=_tsv_clean,
    )


_ISSUES_HEADER = (
    "candidate_id\tcolumn\tsource_y\tselected\tword\tfinal_engine\tconfidence\tscore\t"
    "issue_types\tpaddle_lemma\ttesseract_lemma\tlens_lemma\tpaddle_text\ttesseract_text\t"
    "lens_text\tdecision_reason"
)
_QUALITY_HEADER = (
    "page\tagreement\tcandidate_union\tpaired\texact\tsimilar\tconflict\tpaddle_only\t"
    "tesseract_only\tlens_used\tlens_only\ttriple_agree\tmulti_engine_majority\t"
    "selected\tissues\tneeds_review"
)


def _issues_text(review_candidates: list[dict[str, Any]]) -> str:
    return _diag_issues_text_impl(
        review_candidates,
        header=_ISSUES_HEADER,
        clean=_tsv_clean,
    )

def _manual_selection_path(cache_path: Path) -> Path:
    return cache_path.with_name(f"{cache_path.stem}_manual_selection.json")


def _expand_original_y_fallback_candidates(review_candidates: list[dict[str, Any]]) -> int:
    """Expose an image-derived anchor Y as the unchecked fallback position.

    v2.8.19 keeps three distinct vertical facts: ``original_box`` / OCR coarse Y
    for diagnosis, ``anchor_source_y`` derived from local image ink geometry,
    and the final refined Y.  The blue fallback checkbox uses the image anchor
    when available; this avoids returning to an OCR box top that may itself have
    leaked into the preceding line.  OCR coarse Y remains preserved in cache.
    """
    additions: list[dict[str, Any]] = []
    created = 0
    for item in list(review_candidates):
        if str(item.get("position_variant", "refined")) != "refined":
            continue
        try:
            refined_y = int(item.get("source_y", 0))
            refined_x = int(item.get("source_x", 0))
            coarse_y = int(item.get("coarse_source_y", refined_y))
            coarse_x = int(item.get("coarse_source_x", refined_x))
            anchor_y = int(item.get("anchor_source_y", coarse_y))
            anchor_x = int(item.get("anchor_source_x", coarse_x))
            refined_v = int(item.get("_axis_v", refined_y))
            coarse_v = int(item.get("_coarse_axis_v", refined_v))
            anchor_v = int(item.get("_anchor_axis_v", coarse_v))
        except (TypeError, ValueError):
            continue
        if refined_y <= 0 or anchor_y <= 0 or anchor_y == refined_y:
            continue
        base_id = str(item.get("candidate_id", ""))
        if not base_id:
            continue
        group_id = str(item.get("position_group_id") or base_id)
        item["position_group_id"] = group_id
        item["refined_source_y"] = refined_y
        item["coarse_source_y"] = coarse_y
        item["anchor_source_y"] = anchor_y
        item["position_variant"] = "refined"

        fallback = dict(item)
        fallback["candidate_id"] = f"{base_id}-rawy"
        fallback["source_x"] = anchor_x
        fallback["source_y"] = anchor_y
        fallback["_axis_v"] = anchor_v
        fallback["refined_source_y"] = refined_y
        fallback["coarse_source_x"] = coarse_x
        fallback["coarse_source_y"] = coarse_y
        fallback["_coarse_axis_v"] = coarse_v
        fallback["anchor_source_x"] = anchor_x
        fallback["anchor_source_y"] = anchor_y
        fallback["_anchor_axis_v"] = anchor_v
        fallback["position_group_id"] = group_id
        fallback["position_variant"] = "original"
        fallback["selected"] = False
        fallback["manual_override"] = False
        fallback["needs_review"] = False
        fallback["decision_reason"] = "image_anchor_y_fallback"
        fallback["fallback_kind"] = "image_anchor"
        fallback["issue_types"] = list(item.get("issue_types", []) or [])
        additions.append(fallback)
        created += 1
    review_candidates.extend(additions)
    review_candidates.sort(
        key=lambda row: (
            int(row.get("column", 0)),
            int(row.get("canonical_v", row.get("source_y", 0))),
            str(row.get("position_variant", "")),
        )
    )
    return created


def _enforce_position_variant_exclusivity(review_candidates: list[dict[str, Any]]) -> int:
    """Ensure at most one Y variant is selected for each physical headword."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in review_candidates:
        group_id = str(item.get("position_group_id", ""))
        if group_id:
            groups.setdefault(group_id, []).append(item)
    changed = 0
    for rows in groups.values():
        selected = [row for row in rows if row.get("selected")]
        if len(selected) <= 1:
            continue
        # A manually chosen variant wins; otherwise keep the refined default.
        manual = [row for row in selected if row.get("manual_override")]
        if manual:
            keeper = manual[-1]
        else:
            keeper = next((row for row in selected if row.get("position_variant") == "refined"), selected[0])
        for row in selected:
            if row is keeper:
                continue
            row["selected"] = False
            changed += 1
    return changed


def _load_manual_selection_overrides(cache_path: Path | None) -> dict[str, dict[str, Any]]:
    if cache_path is None:
        return {}
    path = _manual_selection_path(cache_path)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        overrides = raw.get("overrides", {}) if isinstance(raw, dict) else {}
        return {str(k): dict(v) for k, v in overrides.items() if isinstance(v, dict)}
    except Exception:
        return {}


def _apply_manual_selection_overrides(
    review_candidates: list[dict[str, Any]], overrides: dict[str, dict[str, Any]],
) -> None:
    for item in review_candidates:
        override = overrides.get(str(item.get("candidate_id", "")))
        if not override:
            continue
        if "selected" in override:
            item["selected"] = bool(override["selected"])
        if override.get("word") is not None:
            item["word"] = str(override.get("word") or "")
        if override.get("engine"):
            item["final_engine"] = str(override["engine"])
        item["manual_override"] = True
        item["decision_reason"] = "manual_override"
        issues = list(item.get("issue_types", []) or [])
        if "MANUAL_OVERRIDE" not in issues:
            issues.append("MANUAL_OVERRIDE")
        item["issue_types"] = issues


_FINAL_LINE_DEDUP_RATIO = 0.22
_SINGLE_CJK_LINE_DEDUP_RATIO = 0.55


def _review_finalization_deps() -> _review_finalization.ReviewFinalizationDeps:
    """Resolve monkeypatchable OCR globals and shared quality lock live."""
    return _review_finalization.ReviewFinalizationDeps(
        _is_single_cjk_ideograph=_is_single_cjk_ideograph,
        _review_candidate_box_height=_review_candidate_box_height,
        _review_candidates_same_cjk_glyph=_review_candidates_same_cjk_glyph,
        _review_candidate_priority=_review_candidate_priority,
        _normalize_cjk_review_word=_normalize_cjk_review_word,
        _looks_like_multi_cjk_headword=_looks_like_multi_cjk_headword,
        _review_candidates_same_cjk_compound=_review_candidates_same_cjk_compound,
        _candidate_has_single_cjk_identity=_candidate_has_single_cjk_identity,
        _candidate_line_height=_candidate_line_height,
        _boxes_same_large_cjk_region=_boxes_same_large_cjk_region,
        _single_cjk_duplicate_pair=_single_cjk_duplicate_pair,
        _FINAL_LINE_DEDUP_RATIO=_FINAL_LINE_DEDUP_RATIO,
        _SINGLE_CJK_LINE_DEDUP_RATIO=_SINGLE_CJK_LINE_DEDUP_RATIO,
        Entry=Entry,
        _QUALITY_SUMMARY_LOCK=_QUALITY_SUMMARY_LOCK,
        _QUALITY_HEADER=_QUALITY_HEADER,
        _tsv_clean=_tsv_clean,
        _atomic_write_text=_atomic_write_text,
    )


def _review_candidate_box_height(item: dict[str, Any]) -> int:
    return _review_finalization._review_candidate_box_height(_review_finalization_deps(), item)


def _review_candidates_same_cjk_glyph(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return True when two selected rows are duplicate detections of one Han glyph."""
    return _review_finalization._review_candidates_same_cjk_glyph(_review_finalization_deps(), left, right)


def _review_candidate_priority(item: dict[str, Any]) -> tuple[float, float, float, float]:
    return _review_finalization._review_candidate_priority(_review_finalization_deps(), item)


def _normalize_cjk_review_word(word: str) -> str:
    """Return a Unicode-safe normalized review word for CJK duplicate checks."""
    return _review_finalization._normalize_cjk_review_word(_review_finalization_deps(), word)


def _looks_like_multi_cjk_headword(word: str) -> bool:
    return _review_finalization._looks_like_multi_cjk_headword(_review_finalization_deps(), word)


def _review_candidates_same_cjk_compound(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return True when two selected rows are duplicate detections of one CJK compound headword.

    This handles ordinary-size Chinese bracketed compounds such as 【並肩】 that
    can be emitted twice by slightly different OCR pairings.  To avoid merging
    neighbouring real entries, require the normalized lemma to match exactly and
    the physical boxes to overlap strongly or have almost identical centres.
    """
    return _review_finalization._review_candidates_same_cjk_compound(_review_finalization_deps(), left, right)


def _candidate_has_single_cjk_identity(item: dict[str, Any]) -> bool:
    """Return True when review metadata identifies a large single-Han headword.

    Do not rely only on the final OCR word: the two OCR engines can disagree on
    the glyph while still pointing at the same oversized dictionary headword.
    Parser traces and each engine's lemma/raw/corrected forms are therefore also
    inspected.
    """
    return _review_finalization._candidate_has_single_cjk_identity(_review_finalization_deps(), item)


def _candidate_line_height(item: dict[str, Any]) -> float:
    return _review_finalization._candidate_line_height(_review_finalization_deps(), item)


def _boxes_same_large_cjk_region(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Check whether two candidates plausibly cover the same oversized glyph."""
    return _review_finalization._boxes_same_large_cjk_region(_review_finalization_deps(), left, right)


def _single_cjk_duplicate_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Use a wider Y tolerance for duplicate large single-character entries.

    OCR and visual-projection channels can refine the separator independently,
    leaving two lines farther apart than the ordinary 0.22-line threshold.  A
    single-character pair may therefore use 0.55 of a normal text line, but only
    when geometry still says both candidates belong to the same large glyph.
    """
    return _review_finalization._single_cjk_duplicate_pair(_review_finalization_deps(), left, right)


def _deduplicate_selected_cjk_review_candidates(review_candidates: list[dict[str, Any]]) -> int:
    """Suppress duplicate final separator lines with type-aware Y tolerances.

    Ordinary/bracketed entries keep the strict ~0.22-normal-line rule.  Large
    single-character CJK heads first get a dedicated OCR+visual-channel check
    with a wider ~0.55-normal-line allowance, because their two refinement paths
    can legitimately land farther apart while still describing one glyph.

    For ordinary/bracketed duplicates the final separator keeps the *lower*
    safe Y.  For oversized single-CJK duplicates we keep the *upper* boundary:
    the lower visual/OCR duplicate can fall inside the same entry around
    pronunciation/radical metadata (e.g. between 播 ba and Bộ:), while the upper
    line is the true entry-start separator.
    """
    return _review_finalization._deduplicate_selected_cjk_review_candidates(_review_finalization_deps(), review_candidates)


def _entries_from_review_candidates(review_candidates: list[dict[str, Any]]) -> list[Entry]:
    return _review_finalization._entries_from_review_candidates(_review_finalization_deps(), review_candidates)


def _update_project_quality_summary(
    cache_path: Path, summary: dict[str, Any], review_candidates: list[dict[str, Any]],
) -> None:
    return _review_finalization._update_project_quality_summary(_review_finalization_deps(), cache_path, summary, review_candidates)



def _page_detection_deps() -> _page_detection.PageDetectionDeps:
    """Capture current original OCR callbacks and policies for this invocation."""
    return _page_detection.PageDetectionDeps(
        load_headword_filter_rules=load_headword_filter_rules,
        unwrap_column_band=unwrap_column_band,
        run_paddle_band=run_paddle_band,
        _records_to_canonical_band=_records_to_canonical_band,
        run_tesseract_band_records=run_tesseract_band_records,
        _recover_oversized_cjk_ocr_records=_recover_oversized_cjk_ocr_records,
        _recover_image_first_oversized_cjk_records=_recover_image_first_oversized_cjk_records,
        _suppress_raw_records_shadowed_by_verified_cjk_recovery=_suppress_raw_records_shadowed_by_verified_cjk_recovery,
        filter_headword_records=filter_headword_records,
        _attach_source_candidate_coordinates=_attach_source_candidate_coordinates,
        _candidate_axis_v=_candidate_axis_v,
        _cache_signature=_cache_signature,
        _records_as_merged_lines=_records_as_merged_lines,
        _candidate_rows=_candidate_rows,
        _annotate_alphabetical_warnings=_annotate_alphabetical_warnings,
        _apply_alphabetical_warnings_to_entries=_apply_alphabetical_warnings_to_entries,
        _eligible_alignment_rows=_eligible_alignment_rows,
        _pair_ocr_candidates=_pair_ocr_candidates,
        _pairs_need_lens=_pairs_need_lens,
        _make_ocr_pair=_make_ocr_pair,
        _pair_with_lens_candidates=_pair_with_lens_candidates,
        _issues_for_pair=_issues_for_pair,
        _arbitrate_pair=_arbitrate_pair,
        _apply_pair_engine_position=_apply_pair_engine_position,
        _agreement_summary=_agreement_summary,
        _atomic_write_json=_atomic_write_json,
        compact_ocr_cache_payload=compact_ocr_cache_payload,
        _regenerable_sidecars=_regenerable_sidecars,
        _expand_original_y_fallback_candidates=_expand_original_y_fallback_candidates,
        _enforce_position_variant_exclusivity=_enforce_position_variant_exclusivity,
        _load_manual_selection_overrides=_load_manual_selection_overrides,
        _apply_manual_selection_overrides=_apply_manual_selection_overrides,
        _deduplicate_selected_cjk_review_candidates=_deduplicate_selected_cjk_review_candidates,
        _entries_from_review_candidates=_entries_from_review_candidates,
        _update_project_quality_summary=_update_project_quality_summary,
        PROFILE_FILENAME=PROFILE_FILENAME,
        effective_project_profile_id=effective_project_profile_id,
        load_dictionary_profile=load_dictionary_profile,
        resolved_tesseract_language=resolved_tesseract_language,
        tesseract_status=tesseract_status,
        run_google_lens=run_google_lens,
        normalize_page_rgb=normalize_page_rgb,
        OCRRecord=OCRRecord,
        asdict=asdict,
        _FINAL_LINE_DEDUP_RATIO=_FINAL_LINE_DEDUP_RATIO,
    )


def detect_paddle_headwords(
    image: Image.Image,
    geometry: "Geometry",
    settings: AppSettings,
    cache_path: Path | None = None,
    force_refresh: bool = False,
    engine: Any | None = None,
    filter_rules_path: Path | None = None,
    page_sections: list[PageSection] | None = None,
    record_filter: Any | None = None,
) -> list[Entry]:
    """Run the mature multi-OCR dictionary headword pipeline."""
    return _page_detection.detect_paddle_headwords(
        _page_detection_deps(), image, geometry, settings,
        cache_path=cache_path,
        force_refresh=force_refresh,
        engine=engine,
        filter_rules_path=filter_rules_path,
        page_sections=page_sections,
        record_filter=record_filter,
    )
