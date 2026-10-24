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
from .ocr import band_coordinates as _band_coordinates
from .ocr import boundary_measurements as _boundary_measurements
from .ocr import image_separator_geometry as _image_separator_geometry
from .ocr import line_structure_repairs as _line_structure_repairs
from .ocr import visual_rescue_policy as _visual_rescue_policy
from .ocr import peer_typography as _peer_typography
from .ocr import user_filter_rules as _user_filter_rules
from .ocr import grammar_tail_parsing as _grammar_tail_parsing
from .ocr import language_resolution as _language_resolution
from .ocr import source_coordinate_persistence as _source_coordinate_persistence
from .ocr import symbol_inventory as _symbol_inventory
from .ocr import source_candidate_coordinates as _source_candidate_coordinates
from .ocr import review_anchor_variants as _review_anchor_variants
from .ocr import lemma_parser as _lemma_parser
from .ocr import review_manual_selection as _review_manual_selection
from .ocr import pos_cue_policy as _pos_cue_policy
from .ocr import cjk_prefix_parsing as _cjk_prefix_parsing
from .ocr import cjk_single_lemma_parsing as _cjk_single_lemma_parsing
from .ocr import column_band_sampling as _column_band_sampling
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
    return _user_filter_rules.parse_headword_filter_rules(
        text, source, aliases=_RULE_ALIASES, kinds=_RULE_KINDS,
        rule_cls=HeadwordFilterRule, re_module=re,
    )


def load_headword_filter_rules(path: Path | None) -> list[HeadwordFilterRule]:
    return _user_filter_rules.load_headword_filter_rules(
        path, parse_fn=parse_headword_filter_rules,
    )


def _rule_matches(
    rule: HeadwordFilterRule, *, raw_lemma: str, normalized_lemma: str,
    line_text: str, pos_text: str,
) -> bool:
    return _user_filter_rules.rule_matches(
        rule, raw_lemma=raw_lemma, normalized_lemma=normalized_lemma,
        line_text=line_text, pos_text=pos_text,
    )


def evaluate_headword_filter_rules(
    rules: list[HeadwordFilterRule], *, raw_lemma: str, normalized_lemma: str,
    line_text: str, pos_text: str,
) -> dict[str, Any]:
    return _user_filter_rules.evaluate_headword_filter_rules(
        rules, raw_lemma=raw_lemma, normalized_lemma=normalized_lemma,
        line_text=line_text, pos_text=pos_text, match_fn=_rule_matches,
    )

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
    """Historical Chinese OCR script selector."""
    return _language_resolution.is_chinese_ocr(settings)


def _is_japanese_ocr(settings: AppSettings) -> bool:
    """Historical Japanese OCR script selector."""
    return _language_resolution.is_japanese_ocr(settings)

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
    """Profile symbol roles; pass current public parser and family hooks."""
    return _symbol_inventory.configured_symbol_inventory(
        settings, profile,
        split_symbols_fn=_split_configured_symbols,
        visual_samples_fn=visual_marker_samples_from_settings,
        symbol_families=_SYMBOL_FAMILY_BY_LITERAL,
    )

def _starts_with_unconfigured_headword_symbol(
    text: str,
    settings: AppSettings,
    profile: DictionaryProfile,
) -> bool:
    """Historical profile symbol gate with current inventory and Unicode hooks."""
    return _cjk_prefix_parsing.starts_with_unconfigured_headword_symbol(
        text, settings, profile, inventory_fn=_configured_symbol_inventory,
        symbol_families=_SYMBOL_FAMILY_BY_LITERAL, unicode_module=unicodedata,
    )

def _parse_cjk_marker_pinyin_headword(
    text: str, settings: AppSettings, profile: DictionaryProfile,
) -> HeadwordParse | None:
    """Historical CJK marker headword parser; preserve core callback seams."""
    return _cjk_prefix_parsing.parse_cjk_marker_pinyin_headword(
        text, settings, profile,
        is_chinese_fn=_is_chinese_ocr,
        repair_fn=_repair_headword_ocr,
        inventory_fn=_configured_symbol_inventory,
        headword_cls=HeadwordParse,
        regex_module=re, unicode_module=unicodedata,
    )

_CJK_SINGLE_PINYIN_RE = re.compile(
    r"^\s*(?P<head>[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff])\s*[＊*]?\s*"
    r"(?P<pinyin>[A-Za-z\u00C0-\u024F\u1E00-\u1EFF]+"
    r"(?:[ '\-’]+[A-Za-z\u00C0-\u024F\u1E00-\u1EFF]+)*)\b",
    flags=re.UNICODE,
)


def _parse_cjk_single_with_pinyin(text: str, settings: AppSettings) -> HeadwordParse | None:
    """Historical single-Han pinyin parser, retaining source profile regex."""
    return _cjk_single_lemma_parsing.parse_cjk_single_with_pinyin(
        text, settings, is_chinese_fn=_is_chinese_ocr,
        repair_fn=_repair_headword_ocr,
        single_pinyin_re=_CJK_SINGLE_PINYIN_RE,
        visual_headword_fn=_make_chinese_visual_headword,
    )

def _parse_chinese_bracketed_headword(
    text: str,
    settings: AppSettings,
    *,
    enforce_chinese_language: bool = True,
    allow_japanese_reading_prefix: bool = False,
    allowed_openers: tuple[str, ...] | None = None,
) -> HeadwordParse | None:
    """Historical bracketed CJK parser; retain exact configured opener policy."""
    return _cjk_prefix_parsing.parse_chinese_bracketed_headword(
        text, settings, enforce_chinese_language=enforce_chinese_language,
        allow_japanese_reading_prefix=allow_japanese_reading_prefix,
        allowed_openers=allowed_openers,
        is_chinese_fn=_is_chinese_ocr, repair_fn=_repair_headword_ocr,
        headword_cls=HeadwordParse, bracket_closers=_BRACKET_CLOSER_BY_OPENER,
        regex_module=re, unicode_module=unicodedata,
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


def _make_chinese_visual_headword(
    raw: str, parse_text: str, repairs: tuple[str, ...], *, stage: str,
) -> HeadwordParse:
    """Historical single-Han constructor, preserving HeadwordParse identity."""
    return _cjk_single_lemma_parsing.make_chinese_visual_headword(
        raw, parse_text, repairs, stage=stage,
        unicode_module=unicodedata, headword_cls=HeadwordParse,
    )

def _parse_chinese_single_character_headword(text: str, settings: AppSettings) -> HeadwordParse | None:
    """Historical glyph-only candidate parser with visual validation deferred."""
    return _cjk_single_lemma_parsing.parse_chinese_single_character_headword(
        text, settings, is_chinese_fn=_is_chinese_ocr,
        repair_fn=_repair_headword_ocr,
        is_ideograph_fn=_is_single_cjk_ideograph,
        visual_headword_fn=_make_chinese_visual_headword,
        radical_section_re=_CJK_RADICAL_SECTION_RE,
        regex_module=re, unicode_module=unicodedata,
    )

def _paddle_language(settings: AppSettings) -> str:
    """Historical Paddle model-language mapping, preserving a public patch hook."""
    return _language_resolution.paddle_language(settings)

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
    """Historical straightened OCR column band using original source pixels."""
    return _column_band_sampling.unwrap_column_band_impl(
        image, geometry, column, settings, source_width,
        source_rgb=source_rgb, np_module=np,
        normalize_rgb_fn=normalize_page_rgb, image_class=Image,
    )


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
    """Historical source-to-canonical OCR box bridge, preserving record identity."""
    from .geometry.layout_transform import LayoutTransform
    return _band_coordinates.records_to_canonical_band(
        records, source_band_size, transform_kind,
        transform_cls=LayoutTransform, record_cls=OCRRecord,
    )

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
    """Keep the historical right-fragment rescue and active patch hooks."""
    return _line_structure_repairs.repair_split_headword_lines(
        lines, settings, left_limit, patterns,
        parse_fn=parse_headword_text, overlap_fn=_vertical_overlap,
        merge_fn=_merge_ocr_lines, np_module=np,
    )


def _repair_wrapped_headword_structure(
    lines: list[OCRLine],
    settings: AppSettings,
    left_limit: int,
    patterns: tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]],
) -> list[OCRLine]:
    """Historical wrapped-POS repair with current parse/grammar helpers."""
    return _line_structure_repairs.repair_wrapped_headword_structure(
        lines, settings, left_limit, patterns,
        parse_fn=parse_headword_text, find_pos_fn=_find_pos_cue,
        strip_fn=_strip_entry_modifiers, line_cls=OCRLine, np_module=np,
    )


def _repair_multiline_headword_state_machine(
    lines: list[OCRLine],
    settings: AppSettings,
    left_limit: int,
    patterns: tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]],
    max_follow_lines: int = 2,
) -> list[OCRLine]:
    """Historical multiline grammar rescue; no source Y movement."""
    return _line_structure_repairs.repair_multiline_headword_state_machine(
        lines, settings, left_limit, patterns, max_follow_lines,
        parse_fn=parse_headword_text, find_pos_fn=_find_pos_cue,
        line_cls=OCRLine, np_module=np, re_module=re,
    )

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
    """Historical regex compiler retaining profile-specific Latin selection."""
    return _pos_cue_policy.compile_patterns(
        settings, profile, regex_module=re, settings_class=AppSettings,
    )


def _strip_entry_modifiers(prefix: str) -> str:
    """Historical grammar morphology stripping, with active regexp module."""
    return _pos_cue_policy.strip_entry_modifiers(prefix, regex_module=re)


def _find_pos_cue(
    tail: str, pos_pattern: re.Pattern[str], limit: int, *, allow_numeric_prefix: bool = False,
) -> tuple[re.Match[str] | None, str]:
    """Historical POS recognition with current core grammar callbacks."""
    return _pos_cue_policy.find_pos_cue(
        tail, pos_pattern, limit,
        allow_numeric_prefix=allow_numeric_prefix,
        regex_module=re, strip_fn=_strip_entry_modifiers,
    )


def _leading_inflection_cue(tail: str) -> tuple[bool, str]:
    """Historical leading morphology cue with live regex dependency."""
    return _grammar_tail_parsing.leading_inflection_cue(tail, re_module=re)


def _parallel_marker_extension(
    tail: str,
) -> tuple[str, int, bool, str]:
    """Historical dictionary parallel bar / OCR ll marker recognition."""
    return _grammar_tail_parsing.parallel_marker_extension(tail, re_module=re)

_BUNDLED_PROFILE = load_dictionary_profile(preset="latin_structured_symbols", language="spa")
_USAGE_ABBREVIATIONS = {
    label.casefold().rstrip(".")
    for label in _BUNDLED_PROFILE.metadata_labels
} | {
    # Common accent-loss OCR variants.
    "amer", "naut", "quim", "mus", "fis",
}


def _consume_leading_space(text: str, cursor: int) -> int:
    return _grammar_tail_parsing.consume_leading_space(text, cursor)


def _parse_structured_tail(
    tail: str,
    pos_pattern: re.Pattern[str],
    search_limit: int,
    *,
    parallel_descriptor: bool = False,
    parallel_label: str = "",
    allow_numeric_prefix: bool = False,
) -> GrammarTailParse:
    """Original ordered grammar state machine; preserve current helper seams."""
    return _grammar_tail_parsing.parse_structured_tail(
        tail, pos_pattern, search_limit,
        parallel_descriptor=parallel_descriptor,
        parallel_label=parallel_label, allow_numeric_prefix=allow_numeric_prefix,
        consume_space_fn=_consume_leading_space, find_pos_fn=_find_pos_cue,
        strip_fn=_strip_entry_modifiers, usage_abbreviations=_USAGE_ABBREVIATIONS,
        grammar_cls=GrammarTailParse, re_module=re,
    )


def _parse_bug_types(
    repairs: tuple[str, ...], grammar: GrammarTailParse, continuation_reason: str,
) -> tuple[str, ...]:
    return _grammar_tail_parsing.parse_bug_types(repairs, grammar, continuation_reason)

def parse_headword_text(
    text: str,
    settings: AppSettings,
    patterns: tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]] | None = None,
    profile: DictionaryProfile | None = None,
) -> HeadwordParse | None:
    """Historical OCR lemma parser with live core callbacks and model origin."""
    return _lemma_parser.parse_headword_text_impl(
        text, settings, patterns, profile,
        deps={
            "_BUNDLED_PROFILE": _BUNDLED_PROFILE,
            "_configured_symbol_inventory": _configured_symbol_inventory,
            "_parse_chinese_bracketed_headword": _parse_chinese_bracketed_headword,
            "_is_chinese_ocr": _is_chinese_ocr,
            "_parse_cjk_single_with_pinyin": _parse_cjk_single_with_pinyin,
            "_parse_cjk_marker_pinyin_headword": _parse_cjk_marker_pinyin_headword,
            "_is_japanese_ocr": _is_japanese_ocr,
            "_parse_chinese_single_character_headword": _parse_chinese_single_character_headword,
            "_starts_with_unconfigured_headword_symbol": _starts_with_unconfigured_headword_symbol,
            "_compile_patterns": _compile_patterns,
            "_repair_headword_ocr": _repair_headword_ocr,
            "_parallel_marker_extension": _parallel_marker_extension,
            "normalize_headword": normalize_headword,
            "_parse_structured_tail": _parse_structured_tail,
            "_parse_bug_types": _parse_bug_types,
            "HeadwordParse": HeadwordParse,
        },
    )


def _looks_like_marker_noise_lemma(parsed: HeadwordParse | None) -> bool:
    """Historical OCR marker-noise gate with current regexp module."""
    return _lemma_parser.looks_like_marker_noise_lemma(parsed, regex_module=re)

def _ink_ratio(gray: np.ndarray, box: tuple[int, int, int, int]) -> float:
    return _boundary_measurements.ink_ratio(gray, box)


def _leading_box(line: OCRLine, matched_chars: int) -> tuple[int, int, int, int]:
    """Keep the historical lemma box helper and its callable origin."""
    return _boundary_measurements.leading_box(line, matched_chars)


def _true_runs(values: np.ndarray) -> list[tuple[int, int]]:
    return _boundary_measurements.true_runs(values)

def _otsu_threshold(gray: np.ndarray) -> int:
    """Historical black/white threshold; implementation owned by OCR band leaf."""
    return _band_preprocessing.otsu_threshold(gray, np_module=np)

def _separator_analysis_x_bounds(
    width: int,
    settings: AppSettings,
    pixel_scale: float = 1.0,
) -> tuple[int, int]:
    """Historical local-column OCR separator ROI policy."""
    return _boundary_measurements.separator_analysis_x_bounds(
        width, settings, pixel_scale,
    )

def detect_image_separator_candidates(
    gray: np.ndarray,
    reference_line_height: int,
    settings: AppSettings,
    pixel_scale: float = 1.0,
    lower_bound: int = 0,
) -> list[dict[str, Any]]:
    """Historical image-only boundary proposal entrypoint."""
    return _image_separator_geometry.detect_image_separator_candidates(
        gray, reference_line_height, settings, pixel_scale, lower_bound,
        roi_fn=_separator_analysis_x_bounds,
        otsu_fn=_otsu_threshold,
        runs_fn=_true_runs,
        np_module=np,
    )


def match_ocr_lines_to_image_boundaries(
    lines: list[OCRLine],
    boundaries: list[dict[str, Any]],
    reference_line_height: int,
) -> dict[int, dict[str, Any]]:
    """Historical mutual-nearest OCR/boundary pairing entrypoint."""
    return _image_separator_geometry.match_ocr_lines_to_image_boundaries(
        lines, boundaries, reference_line_height,
    )

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
    """Historical running-header cut-off with live contiguous-run hook."""
    return _boundary_measurements.header_cutoff(
        gray, settings, ratio, true_runs_fn=_true_runs,
    )

def _accepted_cjk_row_for_visual_run(
    diagnostics: list[dict[str, Any]],
    run_start: int,
    run_end: int,
    word: str,
) -> dict[str, Any] | None:
    """Historical CJK glyph physical-row association with active script classifier."""
    return _visual_rescue_policy.accepted_cjk_row_for_visual_run(
        diagnostics, run_start, run_end, word,
        single_cjk_fn=_is_single_cjk_ideograph,
    )


def _selected_tail_structure_evidence(
    settings: AppSettings,
    parsed: HeadwordParse | None,
    *,
    pos_allowed_by_rules: bool = True,
) -> tuple[tuple[str, ...], dict[str, bool]]:
    """Historical selected tail-evidence policy; Profile switches unchanged."""
    return _visual_rescue_policy.selected_tail_structure_evidence(
        settings, parsed, pos_allowed_by_rules=pos_allowed_by_rules,
    )


def _ordinary_visual_rescue_thresholds(
    settings: AppSettings,
) -> dict[str, float | str]:
    return _visual_rescue_policy.ordinary_visual_rescue_thresholds(settings)


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
    """Historical visual rescue with live Profile threshold helper."""
    return _visual_rescue_policy.ordinary_strong_edge_visual_rescue(
        settings, parsed, at_left=at_left, below_header=below_header,
        boldness_ratio=boldness_ratio, height_ratio=height_ratio,
        confidence=confidence, looks_like_continuation=looks_like_continuation,
        marker_noise=marker_noise, thresholds_fn=_ordinary_visual_rescue_thresholds,
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
    """Historical robust page-local typography center/spread."""
    return _peer_typography.median_and_mad(values, np_module=np)


def _annotate_peer_typography_matches(
    diagnostics: list[dict[str, Any]],
) -> int:
    """Historical peer-typography annotation (not direct candidate acceptance)."""
    return _peer_typography.annotate_peer_typography_matches(
        diagnostics, median_mad_fn=_median_and_mad,
    )

def _attach_source_candidate_coordinates(
    diagnostics: list[dict[str, Any]],
    geometry: "Geometry",
    column: int,
) -> None:
    """Attach original source pixel coordinates via the canonical OCR owner."""
    return _source_candidate_coordinates.attach_source_candidate_coordinates(
        diagnostics, geometry, column,
    )

def _candidate_axis_v(candidate: dict[str, Any] | None) -> int | None:
    """Historical transient reading-axis candidate coordinate lookup."""
    return _source_candidate_coordinates.candidate_axis_v(candidate)

def _source_only_persistence(value: Any) -> Any:
    """Historical source-coordinate persistence, preserving callable origin."""
    return _source_coordinate_persistence.source_only_persistence(value)


def _image_cache_fingerprint(image: Image.Image) -> str:
    """Historical exact pixel hash using the current normalization callback."""
    return _source_coordinate_persistence.image_cache_fingerprint(
        image, normalize_rgb_fn=normalize_page_rgb, hash_module=hashlib,
    )


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
    """Historical anchor-Y fallback variant expansion; preserve mutation and order."""
    return _review_anchor_variants.expand_original_y_fallback_candidates(review_candidates)

def _enforce_position_variant_exclusivity(review_candidates: list[dict[str, Any]]) -> int:
    """Keep only one physical Y candidate with historical manual priority."""
    return _review_manual_selection.enforce_position_variant_exclusivity(review_candidates)

def _load_manual_selection_overrides(cache_path: Path | None) -> dict[str, dict[str, Any]]:
    """Historical read-only manual selection sidecar with live path/JSON hooks."""
    return _review_manual_selection.load_manual_selection_overrides(
        cache_path, path_fn=_manual_selection_path, json_loads_fn=json.loads,
    )

def _apply_manual_selection_overrides(
    review_candidates: list[dict[str, Any]], overrides: dict[str, dict[str, Any]],
) -> None:
    """Apply manual candidate selection in place without changing its schema."""
    return _review_manual_selection.apply_manual_selection_overrides(
        review_candidates, overrides,
    )


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
