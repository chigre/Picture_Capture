from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING
import difflib
import gc
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import unicodedata
from io import BytesIO

import numpy as np
from PIL import Image, ImageOps

from .models import AppSettings, Entry, resolved_tesseract_language
from .runtime_environment import resolve_paddle_device
from .coordinate_space import (
    REFERENCE_CANONICAL_WIDTH,
    reference_to_canonical,
    stored_geometry_to_canonical,
)
from .image_utils import normalize_page_rgb
from .page_sections import PageSection, normalize_page_sections, section_index_for_v
from .dictionary_profile import (
    PROFILE_FILENAME,
    DictionaryProfile,
    effective_project_profile_id,
    leading_relation_label,
    load_dictionary_profile,
    starts_with_internal_article_symbol,
)
from .ocr_engines import find_tesseract, run_google_lens, tesseract_status

if TYPE_CHECKING:
    from .processing import Geometry


@dataclass(slots=True)
class OCRRecord:
    text: str
    confidence: float
    box: tuple[int, int, int, int]


@dataclass(slots=True)
class OCRLine:
    """One visual text line assembled from one or more OCR records."""

    text: str
    confidence: float
    box: tuple[int, int, int, int]
    records: list[OCRRecord]
    # Logical repairs applied after OCR grouping (right-fragment absorption,
    # wrapped POS recovery, multi-line state-machine joins).  Keeping them on
    # the line makes the parser/debug report explain *how* a synthetic line was
    # assembled instead of only showing its final text.
    logical_repairs: tuple[str, ...] = ()


@dataclass(slots=True)
class GrammarTailParse:
    """Structured grammar tail produced after the display lemma.

    The parser advances a cursor through morphology, POS, usage/labels and the
    remaining definition.  Individual stages may still use small regexes, but
    the overall decision is a state machine rather than one monolithic match.
    """

    variants: tuple[str, ...] = ()
    inflections: tuple[str, ...] = ()
    pos_text: str = ""
    usage_text: str = ""
    descriptor_text: str = ""
    definition_text: str = ""
    consumed: int = 0
    stage: str = "lemma"
    trace: tuple[str, ...] = ()


@dataclass(slots=True)
class HeadwordParse:
    raw: str
    normalized: str
    has_pos: bool
    pos_text: str
    has_inflection: bool
    inflection_text: str
    has_descriptor: bool
    descriptor_text: str
    match_end: int
    looks_like_continuation: bool = False
    continuation_reason: str = ""
    corrected_raw: str = ""
    parse_text: str = ""
    ocr_repairs: tuple[str, ...] = ()
    # v2.0 structured grammar parse. These fields are deliberately explicit so
    # diagnostics can show where parsing stopped instead of reducing the whole
    # decision to one regular-expression match.
    variants: tuple[str, ...] = ()
    plural_text: str = ""
    usage_text: str = ""
    definition_text: str = ""
    parser_stage: str = ""
    parser_trace: tuple[str, ...] = ()
    bug_types: tuple[str, ...] = ()


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


@dataclass(slots=True)
class HeadwordFilterRule:
    kind: str
    value: str
    line_number: int
    source: str
    regex: re.Pattern[str] | None = None

    @property
    def display(self) -> str:
        return f"{self.kind}: {self.value}"


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
    if int(getattr(settings, "profile_parser_controls_version", 0) or 0) >= 1:
        generic_markers = ("○", "●", "◦", "•", "〓", "◆", "◇", "►", "▶")
        profile_markers = (
            tuple(m for m in profile.entry_leading_symbols if m)
            if profile.uses_parser("cjk_marker_pinyin") else ()
        )
        markers = tuple(
            sorted(dict.fromkeys(generic_markers + profile_markers), key=len, reverse=True)
        )
    else:
        markers = tuple(sorted((m for m in profile.entry_leading_symbols if m), key=len, reverse=True))
        if not markers:
            markers = ("○", "●", "◦", "•", "〓")
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

    # Chinese profiles require the bracket at the physical line start.  The
    # Japanese shueisha-style profile may prepend a short kana reading such as
    # "あい【愛】"; that prefix is entry metadata, not part of the lemma.
    reading_prefix = ""
    if allow_japanese_reading_prefix:
        opener = re.match(
            r"^\s*(?:(?P<reading>[\u3040-\u30ff\u31f0-\u31ffー・･]{1,12})\s*)?"
            r"(?P<opening>[【〔［\[])\s*(?P<remainder>.*)$",
            parse_text,
            flags=re.UNICODE,
        )
        if opener:
            reading_prefix = str(opener.group("reading") or "")
    else:
        opener = re.match(
            r"^\s*(?P<opening>[【〔［\[])\s*(?P<remainder>.*)$",
            parse_text,
            flags=re.UNICODE,
        )
    if not opener:
        return None

    opening = opener.group("opening")
    remainder = opener.group("remainder").rstrip()
    close_match = re.search(r"[】〕］\]]", remainder, flags=re.UNICODE)
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
    from .layout_detection import clear_text_detection_cache
    clear_text_detection_cache()
    # Avoid the PaddlePaddle 3.3.x CPU PIR/oneDNN incompatibility also for
    # ordinary OCR, not only the separate layout detector.
    os.environ["FLAGS_enable_pir_api"] = "0"
    from .windows_gpu_runtime import configure_windows_nvidia_dlls
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
    canonical_width = geometry.transform.canonical_size(image.size)[0]
    band_ratio = max(
        1, min(100, int(getattr(settings, "paddle_band_width_ratio", 100)))
    ) / 100.0
    left_margin = max(
        0,
        reference_to_canonical(
            settings.paddle_band_left_margin, canonical_width,
        ),
    )
    if source_width is not None:
        band_width = max(24, int(source_width))
    else:
        configured_band_width = max(
            24,
            round(
                reference_to_canonical(
                    settings.paddle_band_width, canonical_width,
                )
                * band_ratio
            ),
        )
        # Never let the OCR candidate strip spill into the next dictionary
        # column. This mattered little on wide two-column Latin pages but is
        # destructive on dense three-column CJK pages: OCR would merge a large
        # one-character head from this column with a bracketed entry in the
        # next column and neither parser could recover the boundary.
        column_width = (
            int(geometry.column_widths[column])
            if 0 <= column < len(geometry.column_widths)
            else configured_band_width
        )
        band_width = max(24, min(configured_band_width, max(24, column_width + left_margin)))
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
    payload = getattr(result, "json", result)
    if callable(payload):
        payload = payload()
    if not isinstance(payload, dict):
        raise RuntimeError("PaddleOCR 返回了无法解析的结果格式")
    nested = payload.get("res")
    return nested if isinstance(nested, dict) else payload


def extract_ocr_records(result: Any) -> list[OCRRecord]:
    payload = _json_payload(result)
    raw_texts = payload.get("rec_texts")
    raw_scores = payload.get("rec_scores")
    raw_boxes = payload.get("rec_boxes")
    texts = list(raw_texts) if raw_texts is not None else []
    scores = list(raw_scores) if raw_scores is not None else []
    boxes = list(raw_boxes) if raw_boxes is not None else []
    if not boxes:
        raw_polygons = payload.get("rec_polys")
        polygons = list(raw_polygons) if raw_polygons is not None else []
        for polygon in polygons:
            array = np.asarray(polygon)
            boxes.append([array[:, 0].min(), array[:, 1].min(), array[:, 0].max(), array[:, 1].max()])
    records: list[OCRRecord] = []
    for text, score, box in zip(texts, scores, boxes):
        values = [int(round(float(value))) for value in list(box)]
        if len(values) != 4:
            continue
        x0, y0, x1, y1 = values
        if x1 <= x0 or y1 <= y0:
            continue
        records.append(OCRRecord(str(text).strip(), float(score), (x0, y0, x1, y1)))
    return sorted(records, key=lambda item: (item.box[1], item.box[0]))


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
    """Return a temporary OCR image and source-to-input coordinate scale."""
    source = normalize_page_rgb(band)
    mode = str(mode or "original").strip().lower()
    if mode in {"grayscale", "gray", "auto_contrast", "binary"}:
        gray = ImageOps.grayscale(source)
        if mode in {"auto_contrast", "binary"}:
            gray = ImageOps.autocontrast(gray)
        if mode == "binary":
            array = np.asarray(gray)
            threshold = _otsu_threshold(array)
            gray = Image.fromarray(np.where(array > threshold, 255, 0).astype(np.uint8), mode="L")
        source = gray.convert("RGB")
    limit = max(256, int(max_long_side or 2800))
    scale = min(1.0, limit / max(source.size))
    if scale < 1.0:
        source = source.resize(
            (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
            Image.Resampling.LANCZOS,
        )
    return source, scale


def _records_to_canonical_band(
    records: list[OCRRecord], source_band_size: tuple[int, int], transform_kind: str
) -> list[OCRRecord]:
    """Map OCR boxes to analysis space without transforming OCR input pixels."""
    from .layout_transform import LayoutTransform

    transform = LayoutTransform(transform_kind)
    return [
        OCRRecord(record.text, record.confidence, transform.source_box_to_canonical(record.box, source_band_size))
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
    """Run Tesseract TSV on the same candidate band used by PaddleOCR.

    This is deliberately optional.  A missing/broken Tesseract installation must
    never prevent the primary PaddleOCR pass from completing; callers catch and
    record the exception in the diagnostics report.
    """
    resolved = _tesseract_executable(settings.ocr_executable)
    if not resolved:
        raise RuntimeError("未找到 Tesseract OCR；请在环境中心选择 Tesseract 可执行程序或查看安装帮助。")
    payload = BytesIO()
    normalize_page_rgb(band).save(payload, format="PNG")
    command = [
        resolved, "stdin", "stdout", "-l", resolved_tesseract_language(settings),
        "--psm", str(max(3, int(psm_override if psm_override is not None else settings.paddle_tesseract_psm))), "tsv",
    ]
    try:
        proc = subprocess.run(
            command, input=payload.getvalue(), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Tesseract OCR 超时（120 秒）；本栏已放弃 Tesseract 结果。") from exc
    if proc.returncode:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Tesseract OCR 失败：{detail}")
    tsv = proc.stdout.decode("utf-8", errors="replace")
    records: list[OCRRecord] = []
    lines = tsv.splitlines()
    if not lines:
        return records, ""
    header = lines[0].split("\t")
    index = {name: i for i, name in enumerate(header)}
    required = {"level", "left", "top", "width", "height", "conf", "text"}
    if not required.issubset(index):
        raise RuntimeError("Tesseract TSV 缺少必要字段")
    for row in lines[1:]:
        cells = row.split("\t")
        if len(cells) < len(header):
            cells += [""] * (len(header) - len(cells))
        try:
            if int(cells[index["level"]]) != 5:
                continue
            text = cells[index["text"]].strip()
            if not text:
                continue
            conf = float(cells[index["conf"]]) / 100.0
            left = int(cells[index["left"]]); top = int(cells[index["top"]])
            width = int(cells[index["width"]]); height = int(cells[index["height"]])
        except (ValueError, IndexError):
            continue
        if width <= 0 or height <= 0:
            continue
        records.append(OCRRecord(text, max(0.0, conf), (left, top, left + width, top + height)))
    records.sort(key=lambda item: (item.box[1], item.box[0]))
    full_text = "\n".join(line.text for line in group_ocr_records(records, settings.paddle_line_merge_y_ratio))
    return records, full_text


def _repair_headword_ocr(text: str) -> tuple[str, tuple[str, ...]]:
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
        return bool(ch and re.match(r"[^\W\d_]", ch, flags=re.UNICODE))

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
        if re.match(
            r"\s+(?:s\.|adj\.?|adv\.?|[vy]\.|prep\.?|pron\.?|interj\.?|art\.?|num\.?|loc\.?|superlat\.?)",
            tail,
            flags=re.UNICODE | re.IGNORECASE,
        ):
            prev = chars[last - 1]
            if is_letter(prev) or prev in separators:
                old = chars[last]
                chars[last] = mapping[old]
                repairs.append(f"{old}->{mapping[old]}@{last}(terminal)")

    return "".join(chars), tuple(repairs)

def _vertical_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    top = max(a[1], b[1])
    bottom = min(a[3], b[3])
    overlap = max(0, bottom - top)
    minimum = max(1, min(a[3] - a[1], b[3] - b[1]))
    return overlap / minimum


def group_ocr_records(records: list[OCRRecord], y_ratio: float = 0.55) -> list[OCRLine]:
    """Merge OCR fragments that belong to the same printed line.

    Paddle normally returns a whole text line, but mixed bold/italic dictionary
    typography can split ``lemma`` and ``(plural) POS`` into adjacent boxes.
    Merging them before parsing lets grammatical labels become a strong cue.
    """
    usable = [record for record in records if record.text]
    if not usable:
        return []
    heights = np.asarray([max(1, record.box[3] - record.box[1]) for record in usable], dtype=float)
    median_height = max(1.0, float(np.median(heights)))
    center_tolerance = max(2.0, median_height * max(0.1, y_ratio))

    clusters: list[list[OCRRecord]] = []
    cluster_boxes: list[tuple[int, int, int, int]] = []
    for record in sorted(usable, key=lambda item: ((item.box[1] + item.box[3]) / 2.0, item.box[0])):
        cy = (record.box[1] + record.box[3]) / 2.0
        best_index: int | None = None
        best_distance = float("inf")
        # Only nearby recent clusters are plausible; dictionary lines do not
        # interleave vertically.
        for index in range(max(0, len(clusters) - 3), len(clusters)):
            box = cluster_boxes[index]
            cluster_cy = (box[1] + box[3]) / 2.0
            distance = abs(cy - cluster_cy)
            if distance <= center_tolerance or _vertical_overlap(record.box, box) >= 0.72:
                if distance < best_distance:
                    best_index = index
                    best_distance = distance
        if best_index is None:
            clusters.append([record])
            cluster_boxes.append(record.box)
            continue
        clusters[best_index].append(record)
        x0, y0, x1, y1 = cluster_boxes[best_index]
        rx0, ry0, rx1, ry1 = record.box
        cluster_boxes[best_index] = (min(x0, rx0), min(y0, ry0), max(x1, rx1), max(y1, ry1))

    lines: list[OCRLine] = []
    for members, box in zip(clusters, cluster_boxes):
        members = sorted(members, key=lambda item: item.box[0])
        text = " ".join(member.text.strip() for member in members if member.text.strip()).strip()
        weights = [max(1, len(member.text.strip())) for member in members]
        confidence = float(np.average([member.confidence for member in members], weights=weights))
        lines.append(OCRLine(text=text, confidence=confidence, box=box, records=members))
    return sorted(lines, key=lambda item: (item.box[1], item.box[0]))



def _merge_ocr_lines(lines: list[OCRLine]) -> OCRLine:
    members = sorted(
        [record for line in lines for record in line.records],
        key=lambda item: item.box[0],
    )
    x0 = min(line.box[0] for line in lines); y0 = min(line.box[1] for line in lines)
    x1 = max(line.box[2] for line in lines); y1 = max(line.box[3] for line in lines)
    text = " ".join(record.text.strip() for record in members if record.text.strip()).strip()
    weights = [max(1, len(record.text.strip())) for record in members]
    confidence = float(np.average([record.confidence for record in members], weights=weights))
    repairs = tuple(dict.fromkeys(r for line in lines for r in line.logical_repairs))
    return OCRLine(text=text, confidence=confidence, box=(x0, y0, x1, y1), records=members, logical_repairs=repairs)


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
    """Normalize a dictionary display headword without destroying real hyphens.

    Besides normal interpuncts, OCR commonly emits ``+`` and mixed runs such as
    ``.-`` / ``+-`` for a printed syllable dot.  Those are collapsed only when
    they occur between letters.  A leading/trailing hyphen is preserved for
    bound morphemes such as ``-aico`` or ``agro-``.
    """
    value = text.strip()
    if remove_syllable_separators:
        letter = r"[^\W\d_]"
        # Mixed OCR separator runs between letters are unambiguous syllable
        # separators. Collapse them first so later real-hyphen logic stays safe.
        value = re.sub(
            rf"(?<={letter})\s*(?:[·•∙‧.:+]+\s*-+|-+\s*[·•∙‧.:+]+)\s*(?={letter})",
            "·", value, flags=re.UNICODE,
        )
        separators = re.escape(_SYLLABLE_SEPARATORS)
        had_unambiguous_separator = bool(re.search(
            rf"(?<={letter})\s*[{separators}]\s*(?={letter})",
            value, flags=re.UNICODE,
        ))
        value = re.sub(
            rf"(?<={letter})\s*[{separators}]\s*(?={letter})",
            "", value, flags=re.UNICODE,
        )
        internal_hyphens = re.findall(
            rf"(?<={letter})\s*-\s*(?={letter})",
            value, flags=re.UNICODE,
        )
        remove_hyphens = had_unambiguous_separator or len(internal_hyphens) >= 2
        if not remove_hyphens and len(internal_hyphens) == 1:
            compact = re.sub(r"\s+", "", value)
            # Do not count leading/trailing bound-morpheme hyphens here.
            inner = compact.strip("-")
            parts = inner.split("-")
            if len(parts) == 2:
                left_letters = len(re.findall(letter, parts[0], flags=re.UNICODE))
                right_letters = len(re.findall(letter, parts[1], flags=re.UNICODE))
                remove_hyphens = min(left_letters, right_letters) <= 2 and max(left_letters, right_letters) <= 8
        if remove_hyphens:
            value = re.sub(
                rf"(?<={letter})\s*-\s*(?={letter})",
                "", value, flags=re.UNICODE,
            )
    value = re.sub(r"\s*([-\u2019'])\s*", r"\1", value)
    return value.strip()

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
            bracketed = _parse_chinese_bracketed_headword(
                text, settings, enforce_chinese_language=False,
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
        chinese = _parse_chinese_bracketed_headword(
            text,
            settings,
            enforce_chinese_language=not explicit_cjk_profile,
            allow_japanese_reading_prefix=(
                explicit_cjk_profile and _is_japanese_ocr(settings)
            ),
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
    """Return a conservative page-local black/white threshold.

    Dictionary scans are usually high contrast, but paper tone and antialiasing
    vary by source. Otsu keeps the separator refinement independent of a
    project-specific hardcoded gray value. The clamp prevents an unusually
    bright or dark crop from turning most of the paper into ink.
    """
    if gray.size == 0:
        return 180
    hist = np.bincount(gray.astype(np.uint8).ravel(), minlength=256).astype(np.float64)
    total = float(gray.size)
    weighted_total = float(np.dot(np.arange(256, dtype=np.float64), hist))
    background_weight = 0.0
    background_sum = 0.0
    best_variance = -1.0
    best_threshold = 180
    for threshold in range(256):
        background_weight += hist[threshold]
        if background_weight <= 0:
            continue
        foreground_weight = total - background_weight
        if foreground_weight <= 0:
            break
        background_sum += threshold * hist[threshold]
        background_mean = background_sum / background_weight
        foreground_mean = (weighted_total - background_sum) / foreground_weight
        between = background_weight * foreground_weight * (background_mean - foreground_mean) ** 2
        if between > best_variance:
            best_variance = between
            best_threshold = threshold
    return int(min(220, max(80, best_threshold)))





def _separator_analysis_x_bounds(
    width: int,
    settings: AppSettings,
    reference_to_canonical_scale: float = 1.0,
) -> tuple[int, int]:
    """Return the left-local X ROI used for separator/boundary analysis.

    Dictionary headwords usually live at the left of a column while definitions
    can run across its full width.  Analysing the whole column lets long text on
    the preceding definition line contaminate a local Y boundary.  The user can
    therefore limit refinement to a percentage of the left side of the column.
    """
    width = max(1, int(width))
    margin = max(0, round(max(0, settings.paddle_separator_column_margin) * reference_to_canonical_scale))
    margin = min(margin, max(0, width // 4))
    ratio = max(10, min(100, int(getattr(settings, "paddle_separator_roi_width_ratio", 60)))) / 100.0
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
    reference_to_canonical_scale: float = 1.0,
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
    x0, x1 = _separator_analysis_x_bounds(width, settings, reference_to_canonical_scale)
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
    safety = max(0, round(configured_safety * max(0.5, float(reference_to_canonical_scale))))

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


def _binary_rle_components(
    mask: np.ndarray,
) -> list[tuple[int, int, int, int, int]]:
    """Dependency-free 8-connected components for visual marker analysis."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2 or mask.size == 0:
        return []
    height, _width = mask.shape
    parent: list[int] = []
    rank: list[int] = []
    boxes: list[list[int]] = []

    def make(x0: int, x1: int, y: int) -> int:
        index = len(parent)
        parent.append(index)
        rank.append(0)
        boxes.append([x0, y, x1, y + 1, x1 - x0])
        return index

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1

    previous: list[tuple[int, int, int]] = []
    for y in range(height):
        padded = np.r_[False, mask[y], False].astype(np.int8)
        changes = np.diff(padded)
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1)
        current: list[tuple[int, int, int]] = []
        cursor = 0
        for x0, x1 in zip(starts.tolist(), ends.tolist()):
            component = make(x0, x1, y)
            while cursor < len(previous) and previous[cursor][1] < x0 - 1:
                cursor += 1
            k = cursor
            while k < len(previous) and previous[k][0] <= x1 + 1:
                px0, px1, prior = previous[k]
                if px1 >= x0 - 1:
                    union(component, prior)
                k += 1
            current.append((x0, x1, component))
        previous = current

    merged: dict[int, list[int]] = {}
    for index, box in enumerate(boxes):
        root = find(index)
        target = merged.setdefault(root, [box[0], box[1], box[2], box[3], 0])
        target[0] = min(target[0], box[0])
        target[1] = min(target[1], box[1])
        target[2] = max(target[2], box[2])
        target[3] = max(target[3], box[3])
        target[4] += box[4]
    return [tuple(value) for value in merged.values()]


def _visual_marker_shape_metrics(mask: np.ndarray) -> dict[str, float]:
    """Shape descriptors for a hollow or filled circular entry marker."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2 or mask.size == 0 or not mask.any():
        return {"density": 0.0, "central_ink": 1.0, "outer_ink_fraction": 1.0}
    height, width = mask.shape
    density = float(mask.mean())
    y0, y1 = round(height * 0.30), round(height * 0.70)
    x0, x1 = round(width * 0.30), round(width * 0.70)
    central = mask[max(0, y0):max(y0 + 1, y1), max(0, x0):max(x0 + 1, x1)]
    central_ink = float(central.mean()) if central.size else 1.0

    yy, xx = np.indices(mask.shape, dtype=np.float64)
    xn = (xx - (width - 1) / 2.0) / max(1.0, width / 2.0)
    yn = (yy - (height - 1) / 2.0) / max(1.0, height / 2.0)
    radius = np.sqrt(xn * xn + yn * yn)
    dark_radius = radius[mask]
    outer_ink_fraction = (
        float(np.mean(dark_radius > 1.05)) if dark_radius.size else 1.0
    )
    return {
        "density": round(density, 4),
        "central_ink": round(central_ink, 4),
        "outer_ink_fraction": round(outer_ink_fraction, 4),
    }


def _detect_visual_entry_markers(
    gray: np.ndarray,
    median_height: float,
    left_limit: int,
    *,
    lower_bound: int = 0,
) -> list[dict[str, Any]]:
    """Detect CNIT-style ○/● entry markers directly from page pixels.

    PaddleOCR often drops or substitutes the small circle itself.  On the
    supplied CNIT pages the visual marker is much more stable: compact, nearly
    square, aligned to a narrow left marker lane, and either a hollow ring or a
    dense disk.  A robust lane estimate removes incidental round glyphs inside
    definitions.
    """
    if gray.size == 0 or gray.ndim != 2:
        return []
    height, width = gray.shape
    line_h = max(8.0, float(median_height))
    zone_width = min(
        width,
        max(int(left_limit + round(line_h * 1.6)), round(line_h * 2.2), 48),
    )
    lower = max(0, min(height - 1, int(lower_bound)))
    if zone_width < 12 or lower >= height - 2:
        return []

    roi = gray[lower:, :zone_width]
    threshold = _otsu_threshold(roi)
    dark = roi <= threshold
    candidates: list[dict[str, Any]] = []
    broad_left = max(int(left_limit), round(line_h * 1.50))

    for x0, y0, x1, y1, _area in _binary_rle_components(dark):
        box_w = x1 - x0
        box_h = y1 - y0
        if box_w <= 0 or box_h <= 0 or x0 > broad_left:
            continue
        aspect = box_w / max(1.0, float(box_h))
        if not 0.72 <= aspect <= 1.30:
            continue

        shape = _visual_marker_shape_metrics(dark[y0:y1, x0:x1])
        density = float(shape["density"])
        central_ink = float(shape["central_ink"])
        outer_fraction = float(shape["outer_ink_fraction"])
        marker_type = ""

        # Tuned against CNIT_0013–0032: real hollow markers are consistently
        # close to one body-line high and have a genuinely empty centre.
        if (
            line_h * 0.84 <= box_w <= line_h * 1.25
            and line_h * 0.80 <= box_h <= line_h * 1.25
            and 0.25 <= density <= 0.38
            and central_ink <= 0.06
            and outer_fraction <= 0.04
        ):
            marker_type = "open_circle"
        # Filled sub-entry bullets are slightly smaller but remain compact and
        # centrally solid.
        elif (
            line_h * 0.55 <= box_w <= line_h * 1.10
            and line_h * 0.66 <= box_h <= line_h * 1.15
            and 0.70 <= density <= 0.90
            and central_ink >= 0.80
            and outer_fraction <= 0.04
        ):
            marker_type = "filled_circle"
        if not marker_type:
            continue

        candidates.append({
            "type": marker_type,
            "symbol": "○" if marker_type == "open_circle" else "●",
            "x0": int(x0),
            "x1": int(x1),
            "y0": int(lower + y0),
            "y1": int(lower + y1),
            "center_y": round(float(lower + (y0 + y1) / 2.0), 2),
            "width": int(box_w),
            "height": int(box_h),
            "density": density,
            "central_ink": central_ink,
            "outer_ink_fraction": outer_fraction,
            "threshold": int(threshold),
        })

    # True entry markers occupy one gently drifting lane.  Use the median lane
    # only when enough markers exist; this rejects small round letters/punctuation
    # inside body text without assuming a fixed pixel X.
    if len(candidates) >= 3:
        lane_x = float(np.median([item["x0"] for item in candidates]))
        lane_tolerance = max(8.0, line_h * 0.50)
        candidates = [
            item for item in candidates
            if abs(float(item["x0"]) - lane_x) <= lane_tolerance
        ]
        for item in candidates:
            item["lane_x"] = round(lane_x, 2)
            item["lane_delta"] = round(abs(float(item["x0"]) - lane_x), 2)
    return candidates


def _match_visual_entry_markers_to_lines(
    lines: list[OCRLine],
    markers: list[dict[str, Any]],
    median_height: float,
) -> dict[int, dict[str, Any]]:
    """Pair visual ○/● markers with OCR rows on the same physical line."""
    if not lines or not markers:
        return {}
    line_h = max(8.0, float(median_height))
    max_delta = max(8.0, line_h * 0.80)
    proposals: list[tuple[float, int, int]] = []
    for marker_index, marker in enumerate(markers):
        marker_center = float(marker["center_y"])
        marker_x1 = int(marker["x1"])
        for line_index, line in enumerate(lines):
            x0, y0, _x1, y1 = line.box
            line_center = (y0 + y1) / 2.0
            delta = abs(line_center - marker_center)
            if delta > max_delta:
                continue
            if x0 > marker_x1 + line_h * 3.2:
                continue
            overlap = max(
                0, min(int(marker["y1"]), y1) - max(int(marker["y0"]), y0)
            )
            if overlap <= 0 and delta > line_h * 0.55:
                continue
            proposals.append((delta, marker_index, line_index))

    matches: dict[int, dict[str, Any]] = {}
    used_markers: set[int] = set()
    used_lines: set[int] = set()
    for delta, marker_index, line_index in sorted(proposals):
        if marker_index in used_markers or line_index in used_lines:
            continue
        item = dict(markers[marker_index])
        item["match_method"] = "visual_marker_nearest_row"
        item["ocr_line_index"] = int(line_index)
        item["center_delta"] = round(float(delta), 2)
        matches[line_index] = item
        used_markers.add(marker_index)
        used_lines.add(line_index)
    return matches


def _parse_cjk_visual_marker_line(
    text: str,
    marker_symbol: str,
    settings: AppSettings,
    profile: DictionaryProfile,
) -> HeadwordParse | None:
    """Recover a marker-led CJK head when OCR omitted/misread the visual marker."""
    parse_text, _repairs = _repair_headword_ocr(text)
    # At most a few OCR junk glyphs may precede the Han lemma where the circle
    # was.  The visual marker itself supplies the strong boundary evidence.
    match = re.search(
        r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]",
        parse_text[:10],
    )
    if match is None or match.start() > 4:
        return None
    synthetic = marker_symbol + parse_text[match.start():]
    parsed = _parse_cjk_marker_pinyin_headword(synthetic, settings, profile)
    if parsed is None:
        return None
    parsed.parser_stage = "cjk_visual_marker_rescue"
    parsed.descriptor_text = "cjk_marker_pinyin"
    parsed.parser_trace = (
        f"visual_entry_marker:{marker_symbol}",
        "cjk_visual_marker_rescue",
    )
    return parsed


def _leading_cjk_ideograph(text: str) -> str:
    """Return a CJK glyph only when it is the actual leading token.

    Visual single-character rescue must never mine an arbitrary Han character
    from the middle of an ordinary definition line (for example "Âm: 波 ba ...").
    The oversized glyph may be followed by pinyin/variants, but it must itself
    start the OCR record.
    """
    normalized = unicodedata.normalize("NFKC", text or "").lstrip()
    if not normalized or not _is_single_cjk_ideograph(normalized[0]):
        return ""
    tail = normalized[1:].lstrip()
    if not tail:
        return normalized[0]
    # A rescue record may append pinyin/pronunciation to the display glyph, but
    # ordinary Chinese prose beginning with several Han characters is not a
    # single-character headword record.
    first_tail = tail[0]
    if _is_single_cjk_ideograph(first_tail):
        return ""
    if first_tail.isalpha():
        return normalized[0]
    if first_tail in "([（［/·,，:：":
        remainder = tail[1:].lstrip(" 	([（［/·,，:：")
        if not remainder or (
            remainder[0].isalpha()
            and not _is_single_cjk_ideograph(remainder[0])
        ):
            return normalized[0]
    return ""


def _cjk_visual_projection_runs(
    gray: np.ndarray, header_cutoff: int, settings: AppSettings, reference_to_canonical_scale: float,
) -> tuple[int, list[tuple[int, int]]]:
    """Locate oversized single-character rows from image geometry alone.

    Chinese character dictionaries often print single-character entries at
    roughly twice the body-text height while compound entries use ordinary-size
    bracketed lines.  OCR segmentation can merge the large glyph with nearby
    pronunciation/variant text, so a left-strip row projection is a more stable
    way to recover the entry Y position.  This detector does *not* decide the
    word; it only supplies visual runs that must still be associated with OCR.
    """
    if gray.size == 0:
        return 0, []
    ratio = max(0.25, float(reference_to_canonical_scale))
    zone_width = min(gray.shape[1], max(48, round(100 * ratio)))
    if zone_width <= 0:
        return 0, []
    threshold = _otsu_threshold(gray[:, :zone_width])
    dark_counts = (gray[:, :zone_width] <= threshold).sum(axis=1)
    active = dark_counts >= max(3, round(zone_width * 0.015))

    # Fill only tiny vertical holes inside a glyph.  Do not bridge the whitespace
    # between ordinary dictionary lines.
    max_gap = max(2, round(2.2 * ratio))
    active_list = active.tolist()
    index = 0
    while index < len(active_list):
        if active_list[index]:
            index += 1
            continue
        end = index
        while end < len(active_list) and not active_list[end]:
            end += 1
        if index > 0 and end < len(active_list) and end - index <= max_gap:
            active_list[index:end] = [True] * (end - index)
        index = end

    runs = _true_runs(np.asarray(active_list, dtype=bool))
    canonical_width = max(1, round(REFERENCE_CANONICAL_WIDTH * ratio))
    expected_body = max(
        8.0,
        float(
            stored_geometry_to_canonical(
                settings.character_height, canonical_width, settings,
            )
        ),
    )
    body_heights = [
        end - start for start, end in runs
        if expected_body * 0.45 <= end - start <= expected_body * 1.55
    ]
    if body_heights:
        body_median = float(np.median(np.asarray(body_heights, dtype=float)))
    else:
        plausible = [end - start for start, end in runs if end - start >= max(6, round(5 * ratio))]
        body_median = float(np.median(np.asarray(plausible, dtype=float))) if plausible else expected_body

    minimum_large = max(body_median * 1.45, expected_body * 1.55)
    maximum_large = max(minimum_large + 1.0, body_median * 3.6)
    result: list[tuple[int, int]] = []
    for start, end in runs:
        height = end - start
        if start < header_cutoff:
            continue
        if height < minimum_large or height > maximum_large:
            continue
        result.append((start, end))
    return zone_width, result


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
    enabled = bool(
        getattr(settings, "profile_cjk_right_context_enabled", True)
    )
    width_percent = max(
        30,
        min(
            200,
            int(getattr(settings, "profile_cjk_right_context_width_percent", 80) or 80),
        ),
    )
    metrics: dict[str, Any] = {
        "enabled": enabled,
        "available": False,
        "sparse": False,
        "width_percent": width_percent,
        "width_px": 0,
        "blank_ratio": 0.0,
        "lower_blank_ratio": 0.0,
        "row_occupancy": 1.0,
        "ink_density": 1.0,
        "baseline_ink_density": 0.0,
        "density_ratio": 1.0,
        "sparse_votes": 0,
    }
    if not enabled or gray.size == 0:
        return metrics

    image_h, image_w = gray.shape[:2]
    start = max(0, min(image_h, int(run[0])))
    end = max(start + 1, min(image_h, int(run[1])))
    run_height = max(1, end - start)
    x0 = max(0, min(image_w, int(zone_width)))
    requested = max(8, round(run_height * width_percent / 100.0))
    x1 = min(image_w, x0 + requested)
    if x1 - x0 < 6:
        return metrics

    analysis_top = max(0, min(image_h, int(header_cutoff)))
    threshold_source = gray[analysis_top:, x0:x1]
    if threshold_source.size == 0:
        threshold_source = gray[:, x0:x1]
    threshold = _otsu_threshold(threshold_source)

    roi = gray[start:end, x0:x1]
    if roi.size == 0:
        return metrics
    dark = roi <= threshold
    ink_density = float(np.mean(dark))
    blank_ratio = 1.0 - ink_density

    lower_offset = max(0, min(dark.shape[0] - 1, round(dark.shape[0] * 0.35)))
    lower = dark[lower_offset:, :]
    lower_blank_ratio = (
        1.0 - float(np.mean(lower)) if lower.size else blank_ratio
    )
    row_dark_counts = dark.sum(axis=1)
    row_ink_floor = max(1, round(dark.shape[1] * 0.035))
    row_occupancy = float(np.mean(row_dark_counts >= row_ink_floor))

    baseline_parts: list[np.ndarray] = []
    if start > analysis_top:
        baseline_parts.append(gray[analysis_top:start, x0:x1])
    if end < image_h:
        baseline_parts.append(gray[end:image_h, x0:x1])
    baseline = (
        np.concatenate(baseline_parts, axis=0)
        if baseline_parts else np.empty((0, x1 - x0), dtype=gray.dtype)
    )
    if baseline.size:
        baseline_ink_density = float(np.mean(baseline <= threshold))
    else:
        baseline_ink_density = 0.0
    density_ratio = (
        ink_density / max(0.01, baseline_ink_density)
        if baseline_ink_density > 0
        else 1.0
    )

    votes = 0
    if blank_ratio >= 0.78:
        votes += 1
    if lower_blank_ratio >= 0.86:
        votes += 1
    if row_occupancy <= 0.50:
        votes += 1
    if baseline_ink_density >= 0.02 and density_ratio <= 0.60:
        votes += 1
    sparse = bool(lower_blank_ratio >= 0.80 and votes >= 2)

    metrics.update({
        "available": True,
        "sparse": sparse,
        "width_px": int(x1 - x0),
        "blank_ratio": round(blank_ratio, 4),
        "lower_blank_ratio": round(lower_blank_ratio, 4),
        "row_occupancy": round(row_occupancy, 4),
        "ink_density": round(ink_density, 4),
        "baseline_ink_density": round(baseline_ink_density, 4),
        "density_ratio": round(density_ratio, 4),
        "sparse_votes": int(votes),
    })
    return metrics


def _cjk_right_context_features(metrics: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten right-context diagnostics into JSON-safe candidate features."""
    if not metrics:
        return {}
    return {
        "cjk_right_context_enabled": bool(metrics.get("enabled", False)),
        "cjk_right_context_available": bool(metrics.get("available", False)),
        "cjk_right_context_sparse": bool(metrics.get("sparse", False)),
        "cjk_right_context_width_percent": int(metrics.get("width_percent", 0) or 0),
        "cjk_right_context_width_px": int(metrics.get("width_px", 0) or 0),
        "cjk_right_blank_ratio": float(metrics.get("blank_ratio", 0.0) or 0.0),
        "cjk_lower_right_blank_ratio": float(
            metrics.get("lower_blank_ratio", 0.0) or 0.0
        ),
        "cjk_right_row_occupancy": float(
            metrics.get("row_occupancy", 0.0) or 0.0
        ),
        "cjk_right_density_ratio": float(
            metrics.get("density_ratio", 1.0) or 1.0
        ),
        "cjk_right_sparse_votes": int(metrics.get("sparse_votes", 0) or 0),
    }


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
    x0, y0, x1, y1 = (int(value) for value in box)
    box_height = max(1, y1 - y0)
    expected_height = max(box_height, round(max(1.0, median_height) * 1.45))
    center_y = (y0 + y1) / 2.0
    run_start = round(center_y - expected_height / 2.0)
    run_end = run_start + expected_height
    image_h, image_w = gray.shape[:2]
    if run_start < header_cutoff:
        run_end += header_cutoff - run_start
        run_start = header_cutoff
    if run_end > image_h:
        run_start = max(header_cutoff, run_start - (run_end - image_h))
        run_end = image_h

    # Start at the candidate's own right edge.  For very narrow/clipped boxes,
    # keep at least a modest glyph-width estimate so we do not sample through
    # the right half of the Han character itself.
    estimated_glyph_width = max(
        box_height,
        round(max(1.0, median_height) * 0.78),
    )
    context_x = max(x1, x0 + estimated_glyph_width)
    context_x = min(max(0, context_x), image_w)
    metrics = _cjk_right_context_metrics(
        gray,
        (run_start, run_end),
        context_x,
        settings,
        header_cutoff=header_cutoff,
    )
    metrics["candidate_box_height"] = int(box_height)
    metrics["candidate_expected_height"] = int(expected_height)
    metrics["candidate_context_x"] = int(context_x)
    metrics["candidate_run_start"] = int(run_start)
    metrics["candidate_run_end"] = int(run_end)
    metrics["candidate_baseline_supported"] = bool(
        float(metrics.get("baseline_ink_density", 0.0) or 0.0) >= 0.01
    )
    return metrics


def _cjk_candidate_right_context_features(
    metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Candidate-local right-context diagnostics with a non-colliding prefix."""
    if not metrics:
        return {}
    return {
        "cjk_candidate_right_context_available": bool(
            metrics.get("available", False)
        ),
        "cjk_candidate_right_context_sparse": bool(metrics.get("sparse", False)),
        "cjk_candidate_right_blank_ratio": float(
            metrics.get("blank_ratio", 0.0) or 0.0
        ),
        "cjk_candidate_lower_right_blank_ratio": float(
            metrics.get("lower_blank_ratio", 0.0) or 0.0
        ),
        "cjk_candidate_right_row_occupancy": float(
            metrics.get("row_occupancy", 0.0) or 0.0
        ),
        "cjk_candidate_right_density_ratio": float(
            metrics.get("density_ratio", 1.0) or 1.0
        ),
        "cjk_candidate_right_sparse_votes": int(
            metrics.get("sparse_votes", 0) or 0
        ),
        "cjk_candidate_right_context_x": int(
            metrics.get("candidate_context_x", 0) or 0
        ),
        "cjk_candidate_expected_height": int(
            metrics.get("candidate_expected_height", 0) or 0
        ),
    }


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
    start, end = run
    center = (start + end) / 2.0
    height = max(1, end - start)
    ranked: list[tuple[float, int, float, str, OCRRecord]] = []
    for record in records:
        x0, y0, x1, y1 = record.box
        if x0 > zone_width * 1.12:
            continue
        record_height = max(1, y1 - y0)
        record_width = max(1, x1 - x0)
        overlap = max(0, min(end, y1) - max(start, y0))
        record_center = (y0 + y1) / 2.0
        distance = abs(record_center - center)

        parsed = parse_headword_text(record.text, settings, profile=profile)
        profile_pinyin = None
        parser_controls = int(
            getattr(settings, "profile_parser_controls_version", 0) or 0
        ) >= 1
        single_enabled = (
            bool(getattr(settings, "profile_cjk_allow_single_headword", True))
            if parser_controls else True
        )
        if single_enabled:
            # "大字单字" is the user-facing Project Profile contract.  Inside an
            # already detected oversized visual run, a record that starts with
            # one Han glyph plus romanization is strong structure even when the
            # generic parser/profile metadata did not return a parsed object.
            # The compact-width and overlap gates below still prevent ordinary
            # definition lines from using this relaxed path.
            profile_pinyin = _parse_cjk_single_with_pinyin(record.text, settings)
        if profile_pinyin is not None:
            parsed = profile_pinyin
        parsed_single = bool(
            parsed and _is_single_cjk_ideograph(parsed.normalized)
        )
        profile_pinyin_single = bool(
            profile_pinyin is not None and parsed_single
        )
        profile_visual_single = bool(
            parsed_single
            and single_enabled
            and profile is not None
            and profile.family == "cjk_visual"
            and parsed is not None
            and parsed.parser_stage in {
                "chinese_single_character",
                "chinese_single_character_with_variant",
            }
        )
        word = parsed.normalized if parsed_single else _leading_cjk_ideograph(record.text)
        if not word:
            continue

        context_available = bool(
            right_context and right_context.get("available")
        )
        context_sparse = bool(
            right_context and right_context.get("sparse")
        )
        if profile_pinyin_single or profile_visual_single:
            # Strong Project-Profile structure plus a sparse right-side layout is
            # especially characteristic of a real display head.  It safely buys
            # a little extra recall when OCR vertically clips the glyph.  If the
            # right side is dense, keep a slightly stricter box gate rather than
            # rejecting the otherwise strong OCR structure outright.
            if context_sparse:
                minimum_height_ratio = 0.24
                overlap_ratio = 0.18
                distance_ratio = 0.76
            elif context_available:
                minimum_height_ratio = 0.30
                overlap_ratio = 0.24
                distance_ratio = 0.70
            else:
                # Backward-compatible neutral behavior for callers/caches that
                # do not yet carry right-context metrics.
                minimum_height_ratio = 0.28
                overlap_ratio = 0.22
                distance_ratio = 0.72
            if record_width > zone_width * 1.75:
                continue
            if distance > height * distance_ratio:
                continue
        elif parsed_single:
            minimum_height_ratio = 0.40
            overlap_ratio = 0.30
        else:
            # Weak fallback evidence should not be rescued from a dense block of
            # ordinary body text when the right-context measurement is available.
            if context_available and not context_sparse:
                continue
            minimum_height_ratio = 0.55
            overlap_ratio = 0.45

        # OCR boxes are integer-valued; allow half a pixel of quantization
        # tolerance at an exact ratio boundary (e.g. 14 px / 50 px = 0.28).
        if record_height + 0.5 < height * minimum_height_ratio:
            continue
        overlap_floor = min(record_height, height) * overlap_ratio
        if overlap < overlap_floor:
            continue

        # The unparsed fallback is intentionally stricter: it must start inside
        # the left visual zone instead of merely containing a Han character.
        if not parsed_single and x0 > zone_width * 0.95:
            continue

        quality_rank = 0 if profile_pinyin_single else (1 if parsed_single else 2)
        ranked.append((distance, quality_rank, -float(record.confidence), word, record))
    if not ranked:
        return "", 0.0, None
    ranked.sort(key=lambda item: (item[1], item[0], item[2]))
    _distance, _quality, _neg_conf, word, record = ranked[0]
    return word, float(record.confidence), record


def refine_separator_y(
    gray: np.ndarray,
    coarse_y: int,
    line_height: int,
    settings: AppSettings,
    reference_to_canonical_scale: float = 1.0,
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
    if not settings.paddle_refine_separator_y or gray.size == 0:
        return int(coarse_y), {"enabled": False, "reason": "disabled"}

    height, width = gray.shape[:2]
    if height <= 2 or width <= 8:
        return int(coarse_y), {"enabled": True, "reason": "image_too_small"}

    coarse_y = int(min(height - 1, max(lower_bound, coarse_y)))
    line_height = max(2, int(line_height))
    search_ratio = max(0.05, min(0.80, float(settings.paddle_separator_search_ratio)))
    search_radius = max(2, round(line_height * search_ratio))
    top = max(int(lower_bound), coarse_y - search_radius)
    bottom = min(height - 1, coarse_y + search_radius)
    if bottom <= top:
        return coarse_y, {"enabled": True, "reason": "empty_search"}

    x0, x1 = _separator_analysis_x_bounds(width, settings, reference_to_canonical_scale)

    roi = gray[top:bottom + 1, x0:x1]
    threshold = _otsu_threshold(roi)
    ink = roi <= threshold

    # Remove page borders / vertical rules that remain dark through almost the
    # whole local search window. They add a constant term to every row and can
    # flatten the whitespace valley.
    if ink.shape[0] >= 3 and ink.shape[1] >= 3:
        rule_columns = ink.mean(axis=0) >= 0.72
        if rule_columns.any():
            ink = ink.copy()
            ink[:, rule_columns] = False

    row_ink = ink.mean(axis=1).astype(np.float64)
    band_radius = max(0, round(max(0, settings.paddle_separator_band_radius) * reference_to_canonical_scale))
    band_radius = min(band_radius, max(0, (len(row_ink) - 1) // 3))
    if band_radius > 0:
        kernel = np.ones(2 * band_radius + 1, dtype=np.float64) / (2 * band_radius + 1)
        padded = np.pad(row_ink, (band_radius, band_radius), mode="edge")
        smooth = np.convolve(padded, kernel, mode="valid")
    else:
        smooth = row_ink.copy()

    minimum_index = int(np.argmin(smooth))
    minimum = float(smooth[minimum_index])
    # Expand around the minimum through rows that are effectively part of the
    # same whitespace valley. The tolerance scales to both image width and the
    # local distribution, so near-white plateaus are centred rather than pinned
    # to whichever scan row happened to contain zero pixels.
    q35 = float(np.percentile(smooth, 35)) if smooth.size else minimum
    quantization = 1.0 / max(1, ink.shape[1] * max(1, 2 * band_radius + 1))
    valley_tolerance = max(quantization, (q35 - minimum) * 0.35)
    low_rows = smooth <= (minimum + valley_tolerance)
    runs = _true_runs(low_rows)
    valley = next(
        ((start, end) for start, end in runs if start <= minimum_index < end),
        (minimum_index, minimum_index + 1),
    )
    valley_center = round((valley[0] + valley[1] - 1) / 2)

    # A low-ink run that reaches the edge of our search interval is not a
    # bounded inter-line gap.  The common case is the first printed line of a
    # page/column: there may be a large blank area above it, and centring that
    # open whitespace would drag the separator far upward.  In that situation
    # keep the OCR coarse marker instead of inventing a new Y from an unbounded
    # valley.
    # Only an upper-edge-open valley is dangerous for separator placement.
    # The genuine gap immediately above a tightly packed headword can extend
    # to the *bottom* of a small search interval, so bottom contact alone must
    # not suppress a useful downward correction.
    valley_touches_search_edge = valley[0] == 0
    if valley_touches_search_edge:
        refined_y = int(coarse_y)
        refinement_reason = "open_valley_at_search_edge_keep_coarse"
    else:
        refined_y = int(top + valley_center)
        refinement_reason = "bounded_low_ink_valley"

    return refined_y, {
        "enabled": True,
        "reason": refinement_reason,
        "coarse_y": coarse_y,
        "refined_y": refined_y,
        "shift": refined_y - coarse_y,
        "search_top": top,
        "search_bottom": bottom,
        "search_radius": search_radius,
        "line_height": line_height,
        "band_radius": band_radius,
        "threshold": threshold,
        "minimum_ink_ratio": round(minimum, 6),
        "coarse_ink_ratio": round(float(smooth[min(len(smooth) - 1, max(0, coarse_y - top))]), 6),
        "valley_start": int(top + valley[0]),
        "valley_end": int(top + valley[1] - 1),
        "valley_touches_search_edge": valley_touches_search_edge,
        "analysis_x0": x0,
        "analysis_x1": x1,
    }


def refine_separator_y_adaptive(
    gray: np.ndarray,
    coarse_y: int,
    reference_line_height: int,
    settings: AppSettings,
    reference_to_canonical_scale: float = 1.0,
    lower_bound: int = 0,
    content_top: int | None = None,
    preceding_gap_hint: int | None = None,
) -> tuple[int, dict[str, Any]]:
    """Refine a CJK separator by tracing the nearest blank band above the entry.

    v2.8.16 deliberately stops classifying a whole page as loose/normal/dense.
    The separator is a *local* boundary problem: starting from the OCR/visual
    headword top, first locate the real onset of sustained ink (the OCR box may
    begin a few pixels too high or already inside the glyph), then walk upward
    and find the nearest run of consecutive near-blank rows.  The marker is
    placed just above the ink onset with a small safety clearance, i.e. at the
    lower edge of that blank band.  This keeps the rule visually attached to
    the following headword for both oversized single Han heads and bracketed
    compounds.

    ``preceding_gap_hint`` is retained in the signature for cache/API
    compatibility and diagnostics, but it no longer selects different geometry
    modes.  If no stable local blank band exists, the legacy local valley
    refiner remains the safe fallback for extremely dense print.
    """
    if not settings.paddle_refine_separator_y or gray.size == 0:
        return int(coarse_y), {"enabled": False, "reason": "disabled", "adaptive_mode": "off"}
    height, width = gray.shape[:2]
    if height <= 2 or width <= 8:
        return int(coarse_y), {"enabled": True, "reason": "image_too_small", "adaptive_mode": "fallback"}

    line_h = max(3, int(round(reference_line_height)))
    coarse_y = int(min(height - 1, max(lower_bound, coarse_y)))
    if content_top is None:
        canonical_width = max(
            1,
            round(
                REFERENCE_CANONICAL_WIDTH
                * max(0.01, reference_to_canonical_scale)
            ),
        )
        row_padding = stored_geometry_to_canonical(
            settings.row_padding, canonical_width, settings,
        )
        content_top = coarse_y + max(0, row_padding)
    content_top = int(min(height - 1, max(lower_bound, content_top)))

    # Analyse enough of the column to see the preceding blank band and a small
    # portion of the current entry.  The logic remains local to the candidate.
    look_up = max(8, round(line_h * 1.30))
    # Look far enough below OCR box.y to recover when the box accidentally
    # starts inside the preceding text line.  The actual headword can begin
    # after one full inter-line gap, so half a line was insufficient.
    look_down = max(7, round(line_h * 1.10))
    top = max(int(lower_bound), content_top - look_up)
    bottom = min(height - 1, content_top + look_down)
    if bottom <= top:
        return coarse_y, {"enabled": True, "reason": "empty_search", "adaptive_mode": "fallback"}

    x0, x1 = _separator_analysis_x_bounds(width, settings, reference_to_canonical_scale)
    roi = gray[top:bottom + 1, x0:x1]
    threshold = _otsu_threshold(roi)
    ink = roi <= threshold

    # A page border / column rule can be black on every row and would make an
    # otherwise empty separator band look non-blank. Remove such rule columns.
    if ink.shape[0] >= 3 and ink.shape[1] >= 3:
        rule_columns = ink.mean(axis=0) >= 0.72
        if rule_columns.any():
            # Remove only *narrow* persistent dark runs. A broad text block can
            # occupy the same X range on several neighbouring lines and must not
            # be mistaken for a vertical page rule.
            narrow_rule = np.zeros_like(rule_columns, dtype=bool)
            max_rule_width = max(2, round(ink.shape[1] * 0.025))
            for a, b in _true_runs(rule_columns):
                if b - a <= max_rule_width:
                    narrow_rule[a:b] = True
            if narrow_rule.any():
                ink = ink.copy()
                ink[:, narrow_rule] = False

    row_ink = ink.mean(axis=1).astype(np.float64)
    if row_ink.size >= 3:
        padded = np.pad(row_ink, (1, 1), mode="edge")
        smooth = np.convolve(padded, np.ones(3, dtype=np.float64) / 3.0, mode="valid")
    else:
        smooth = row_ink.copy()

    # "Blank" is intentionally tolerant rather than exactly zero: old scans
    # contain dust, antialiasing and residual punctuation.  Conversely, an ink
    # onset must be sustained for several rows so a single speck does not cause
    # us to reverse direction too early.
    quantization = 1.0 / max(1, ink.shape[1] * 3)
    positive = smooth[smooth > 0]
    low_positive = float(np.percentile(positive, 20)) if positive.size else 0.0
    blank_threshold = max(quantization * 2.5, min(0.010, low_positive * 0.45 if low_positive else 0.0025))
    blank_mask = smooth <= blank_threshold
    ink_threshold = max(blank_threshold * 1.8, quantization * 5.0)
    ink_mask = smooth > ink_threshold

    target_local = int(min(len(smooth) - 1, max(0, content_top - top)))
    min_ink_rows = max(2, round(line_h * 0.07))
    min_blank_rows = max(2, round(line_h * 0.08))
    # User-configurable safety clearance uses 1400-width reference pixels and
    # is scaled to the current canonical resolution. A value of 0 is
    # allowed when the user deliberately wants the rule to touch the detected
    # ink boundary.
    configured_safety = max(0, int(getattr(settings, "paddle_separator_safety_px", 2)))
    safety = max(0, round(configured_safety * max(0.5, float(reference_to_canonical_scale))))

    # Step 1: establish an image-derived ink onset rather than blindly trusting
    # OCR box.y.  OCR can occasionally merge the preceding definition line into
    # the headword box, so a non-blank box top is not automatically the current
    # headword.  If box.y starts in ink, look a short distance downward for a
    # *real inter-line blank run* followed by sustained ink; when found, the ink
    # after that gap is the current headword.  This relocation uses a stricter
    # blank-run length than ordinary separator refinement so internal white holes
    # inside a large Han glyph are not mistaken for a line break.
    max_onset_local = min(len(smooth) - 1, target_local + max(6, round(line_h * 0.90)))
    onset_local: int | None = None
    relocated_from_prior_ink = False
    box_top_was_blank = bool(blank_mask[target_local])
    relocation_blank_rows = max(min_blank_rows, round(line_h * 0.14))

    if box_top_was_blank:
        i = target_local + 1
        while i <= max_onset_local:
            run_end = min(len(smooth), i + min_ink_rows)
            sustained_nonblank = (
                run_end - i >= min_ink_rows
                and bool(np.all(~blank_mask[i:run_end]))
            )
            if sustained_nonblank or bool(ink_mask[i]):
                onset_local = i
                break
            i += 1
    else:
        # First assume box.y is correct.  Only replace it when a sufficiently
        # long blank run appears soon below it and is followed by a new ink run.
        i = target_local + max(1, min_ink_rows)
        while i <= max_onset_local:
            if not bool(blank_mask[i]):
                i += 1
                continue
            gap_start = i
            while i <= max_onset_local and bool(blank_mask[i]):
                i += 1
            gap_end = i
            if gap_end - gap_start < relocation_blank_rows:
                continue
            j = gap_end
            while j <= max_onset_local:
                run_end = min(len(smooth), j + min_ink_rows)
                sustained_nonblank = (
                    run_end - j >= min_ink_rows
                    and bool(np.all(~blank_mask[j:run_end]))
                )
                if sustained_nonblank or bool(ink_mask[j]):
                    onset_local = j
                    relocated_from_prior_ink = True
                    break
                j += 1
            if onset_local is not None:
                break
        if onset_local is None:
            onset_local = target_local

    if onset_local is None:
        onset_local = target_local

    onset_y = top + onset_local
    anchor_y = int(min(height - 1, max(lower_bound, onset_y - safety)))

    # Step 2: reverse direction and find the nearest *consecutive* blank run
    # immediately above the current glyph.  We scan upward from the ink onset,
    # accumulate blank rows, and accept the first run reaching min_blank_rows.
    blank_run_end: int | None = None       # exclusive, nearest to the glyph
    blank_run_start: int | None = None
    j = onset_local - 1
    while j >= 0:
        if blank_mask[j]:
            run_end = j + 1
            k = j
            while k >= 0 and blank_mask[k]:
                k -= 1
            run_start = k + 1
            if run_end - run_start >= min_blank_rows:
                blank_run_start, blank_run_end = run_start, run_end
                break
            j = k
        else:
            j -= 1

    if blank_run_start is not None and blank_run_end is not None:
        # Use the bottom of the nearest valid blank band.  Keep ``safety`` rows
        # clear of the actual ink onset so the rule never cuts into the glyph.
        # This is equivalent to "nearest blank above the word, then stay ~2 px
        # above the ink" and is intentionally more downward-biased than v2.8.13.
        blank_bottom_y = top + blank_run_end - 1
        refined = min(blank_bottom_y, onset_y - safety)
        refined = int(min(height - 1, max(lower_bound, refined)))
        reason = "nearest_blank_band_above_headword"
        return refined, {
            "enabled": True,
            "reason": reason,
            "adaptive_mode": "local_blank_trace",
            "coarse_y": coarse_y,
            "refined_y": refined,
            "shift": refined - coarse_y,
            "reference_line_height": line_h,
            "content_top": content_top,
            "current_ink_onset": onset_y,
            "anchor_y": anchor_y,
            "box_top_was_blank": box_top_was_blank,
            "relocated_from_prior_ink": relocated_from_prior_ink,
            "relocation_blank_rows": int(relocation_blank_rows),
            "blank_run_start": int(top + blank_run_start),
            "blank_run_end": int(top + blank_run_end - 1),
            "blank_run_height": int(blank_run_end - blank_run_start),
            "minimum_blank_rows": int(min_blank_rows),
            "minimum_ink_rows": int(min_ink_rows),
            "safety_pixels": int(safety),
            "configured_safety_pixels": int(configured_safety),
            "blank_threshold": round(float(blank_threshold), 6),
            "ink_threshold": round(float(ink_threshold), 6),
            "threshold": threshold,
            "search_top": top,
            "search_bottom": bottom,
            "analysis_x0": x0,
            "analysis_x1": x1,
            "preceding_gap_hint": preceding_gap_hint,
        }

    # Extremely dense dictionaries can genuinely have no stable run of blank
    # rows. Preserve the old local valley method as a fallback, but if it offers
    # a bounded valley, use its lower edge so the marker still hugs the entry.
    refined, legacy = refine_separator_y(
        gray, coarse_y, line_h, settings,
        reference_to_canonical_scale=reference_to_canonical_scale,
        lower_bound=lower_bound,
    )
    if legacy.get("reason") == "bounded_low_ink_valley" and legacy.get("valley_end") is not None:
        valley_end = int(legacy["valley_end"])
        refined = min(max(lower_bound, onset_y - safety), valley_end)
        legacy["refined_y"] = int(refined)
        legacy["shift"] = int(refined) - int(coarse_y)
        legacy["reason"] = "dense_valley_fallback_bottom_bias"
    legacy["adaptive_mode"] = "dense_fallback"
    legacy["current_ink_onset"] = int(onset_y)
    legacy["anchor_y"] = int(anchor_y)
    legacy["box_top_was_blank"] = bool(box_top_was_blank)
    legacy["relocated_from_prior_ink"] = bool(relocated_from_prior_ink)
    legacy["relocation_blank_rows"] = int(relocation_blank_rows)
    legacy["minimum_blank_rows"] = int(min_blank_rows)
    legacy["minimum_ink_rows"] = int(min_ink_rows)
    legacy["safety_pixels"] = int(safety)
    legacy["configured_safety_pixels"] = int(configured_safety)
    legacy["blank_threshold"] = round(float(blank_threshold), 6)
    legacy["ink_threshold"] = round(float(ink_threshold), 6)
    legacy["preceding_gap_hint"] = preceding_gap_hint
    return int(refined), legacy


def refine_first_content_y(
    gray: np.ndarray,
    coarse_y: int,
    line_height: int,
    settings: AppSettings,
    reference_to_canonical_scale: float = 1.0,
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
    if not settings.paddle_refine_separator_y or gray.size == 0:
        return int(coarse_y), {"enabled": False, "reason": "disabled"}
    height, width = gray.shape[:2]
    coarse_y = int(min(height - 1, max(lower_bound, coarse_y)))
    line_height = max(2, int(line_height))
    search_ratio = max(0.05, min(0.80, float(settings.paddle_separator_search_ratio)))
    radius = max(2, round(line_height * search_ratio))
    top = max(int(lower_bound), coarse_y - radius)
    # The coarse marker is normally OCR-top minus row padding, not the visual
    # centre of the glyphs. Give the downward side more room so the sustained
    # ink onset is fully visible even when OCR's box starts a few pixels early.
    bottom = min(height - 1, coarse_y + max(radius, line_height // 2))
    if bottom <= top:
        return coarse_y, {"enabled": True, "reason": "empty_search"}

    x0, x1 = _separator_analysis_x_bounds(width, settings, reference_to_canonical_scale)
    roi = gray[top:bottom + 1, x0:x1]
    threshold = _otsu_threshold(roi)
    ink = roi <= threshold
    if ink.shape[0] >= 3 and ink.shape[1] >= 3:
        rule_columns = ink.mean(axis=0) >= 0.72
        if rule_columns.any():
            ink = ink.copy()
            ink[:, rule_columns] = False
    row_ink = ink.mean(axis=1).astype(np.float64)

    # A row is "ink-active" when it contains more than a few quantized dark
    # pixels. Requiring a short sustained run rejects isolated dust/antialiasing.
    quantization = 1.0 / max(1, ink.shape[1])
    positive = row_ink[row_ink > 0]
    local_low = float(np.percentile(positive, 20)) if positive.size else 0.0
    active_threshold = max(quantization * 3.0, min(0.004, local_low * 0.55 if local_low else 0.002))
    active = row_ink >= active_threshold
    min_run = max(2, round(max(1, settings.paddle_separator_band_radius) * reference_to_canonical_scale) + 1)
    runs = [(a, b) for a, b in _true_runs(active) if (b - a) >= min_run]

    # Prefer the first sustained run whose centre is not implausibly far above
    # the OCR top. This still catches accents at the top of the headword line.
    onset = None
    coarse_local = coarse_y - top
    for start, end in runs:
        if end >= max(0, coarse_local - max(2, line_height // 3)):
            onset = start
            break
    if onset is None:
        refined = coarse_y
        reason = "no_sustained_ink_keep_coarse"
    else:
        ink_onset = int(top + onset)
        # A separator should mark the whitespace immediately *before* the first
        # entry, not touch the top stroke/accent of the glyph.  Keep a small
        # scale-aware clearance above the sustained-ink onset while respecting
        # the header/lower bound.
        clearance = max(
            2,
            round(
                max(1.0, line_height * 0.12)
                + max(0, settings.row_padding) * 0.35 * reference_to_canonical_scale
            ),
        )
        refined = max(int(lower_bound), ink_onset - clearance)
        reason = "whitespace_before_first_sustained_ink"

    return refined, {
        "enabled": True,
        "reason": reason,
        "coarse_y": coarse_y,
        "refined_y": refined,
        "shift": refined - coarse_y,
        "search_top": top,
        "search_bottom": bottom,
        "line_height": line_height,
        "threshold": threshold,
        "active_ink_threshold": round(float(active_threshold), 6),
        "minimum_active_run": min_run,
        "analysis_x0": x0,
        "analysis_x1": x1,
    }


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
    reference_to_canonical_scale: float | None = None,
) -> tuple[list[Entry], list[dict[str, Any]]]:
    """Select dictionary headwords using structure, geometry and visual cues.

    The strongest signals are now: left alignment + lemma syntax + a nearby
    part-of-speech label. Size, ink density/boldness, special symbols and the
    gap before a line remain fallback evidence for entries without a POS label.
    """
    if profile is None and _is_chinese_ocr(settings):
        # Backward-compatible direct API behavior: before v2.10 Chinese parsing
        # was selected from OCR language alone. The full application pipeline
        # passes an explicit layout Profile, but low-level callers/tests that do
        # not pass one should keep the historical bracket/single-character mode.
        active_profile = load_dictionary_profile(
            preset="cjk_bracket_display", language=settings.ocr_language,
        )
    else:
        active_profile = profile or _BUNDLED_PROFILE
    patterns = _compile_patterns(settings, active_profile)
    _headword_pattern, special_pattern, _pos_pattern = patterns
    # Merge first, then actively repair the special case where OCR split a
    # left-edge bold lemma from its right-side gender/POS fragments.
    lines = group_ocr_records([record for record in records if record.text], settings.paddle_line_merge_y_ratio)
    configured_width = max(1, settings.paddle_band_width)
    reference_scale = (
        max(0.01, float(reference_to_canonical_scale))
        if reference_to_canonical_scale is not None
        else band.width / configured_width
    )
    canonical_width = max(
        1, round(REFERENCE_CANONICAL_WIDTH * reference_scale),
    )
    row_padding = stored_geometry_to_canonical(
        settings.row_padding, canonical_width, settings,
    )
    character_height = stored_geometry_to_canonical(
        settings.character_height, canonical_width, settings,
    )
    row_height = max(1, character_height + row_padding)
    left_limit = round(
        (settings.paddle_band_left_margin + settings.paddle_left_tolerance)
        * reference_scale
    )
    lines = _repair_split_headword_lines(lines, settings, left_limit, patterns)
    lines = _repair_wrapped_headword_structure(lines, settings, left_limit, patterns)
    lines = _repair_multiline_headword_state_machine(lines, settings, left_limit, patterns)
    lines = [line for line in lines if line.confidence >= settings.paddle_rec_score_threshold]
    if not lines:
        return [], []

    gray = np.asarray(ImageOps.grayscale(band), dtype=np.uint8)
    separator_gray = (
        np.asarray(ImageOps.grayscale(separator_band), dtype=np.uint8)
        if separator_band is not None
        else gray
    )
    heights = np.asarray([line.box[3] - line.box[1] for line in lines], dtype=float)
    median_height = max(1.0, float(np.median(heights)))

    # Profile/OCR tuning distances use fixed reference pixels at canonical
    # width 1400; project line geometry itself is full-resolution canonical.
    gap_threshold = row_height * settings.paddle_gap_ratio
    header_cutoff = _header_cutoff(gray, settings, reference_scale)

    # Independent image-only separator candidates.  OCR lines and boundaries
    # are paired with a mutual-nearest rule, so the image validates OCR geometry
    # and OCR in turn validates which blank-to-ink transitions are actual entry
    # candidates.  Pages without stable whitespace simply get no matches.
    image_separator_candidates = detect_image_separator_candidates(
        separator_gray,
        max(2, round(median_height)),
        settings,
        reference_to_canonical_scale=reference_scale,
        lower_bound=header_cutoff,
    )
    image_boundary_matches = match_ocr_lines_to_image_boundaries(
        lines, image_separator_candidates, max(2, round(median_height))
    )

    parser_controls = int(
        getattr(settings, "profile_parser_controls_version", 0) or 0
    ) >= 1
    marker_prefix_enabled = (
        bool(getattr(settings, "profile_allow_marker_prefix", False))
        if parser_controls else active_profile.uses_parser("cjk_marker_pinyin")
    )
    visual_entry_markers = (
        _detect_visual_entry_markers(
            gray, median_height, left_limit, lower_bound=header_cutoff,
        )
        if marker_prefix_enabled and _is_chinese_ocr(settings) else []
    )
    visual_marker_matches = _match_visual_entry_markers_to_lines(
        lines, visual_entry_markers, median_height,
    )

    # Estimate a page-local reference density from leading text portions, not
    # from the whole line (which often mixes bold lemma with normal definition).
    leading_boxes: list[tuple[int, int, int, int]] = []
    parses: list[HeadwordParse | None] = []
    for line_index, line in enumerate(lines):
        parsed = parse_headword_text(line.text, settings, patterns, active_profile)
        visual_marker = visual_marker_matches.get(line_index)
        if visual_marker is not None and (
            parsed is None or parsed.parser_stage != "cjk_marker_pinyin"
        ):
            rescued = _parse_cjk_visual_marker_line(
                line.text,
                str(visual_marker.get("symbol") or "○"),
                settings,
                active_profile,
            )
            if rescued is not None:
                parsed = rescued
        parses.append(parsed)
        leading_boxes.append(
            _leading_box(line, parsed.match_end if parsed else min(12, len(line.text)))
        )
    densities = np.asarray([_ink_ratio(gray, box) for box in leading_boxes], dtype=float)
    positive_densities = densities[densities > 0]
    median_density = max(1e-6, float(np.median(positive_densities)) if positive_densities.size else 1e-6)

    diagnostics: list[dict[str, Any]] = []
    accepted: list[tuple[float, Entry]] = []
    previous_bottom = header_cutoff

    for index, line in enumerate(lines):
        parsed = parses[index]
        image_boundary = image_boundary_matches.get(index)
        visual_entry_marker = visual_marker_matches.get(index)
        height_ratio = heights[index] / median_height
        boldness_ratio = densities[index] / median_density
        x0, y0, _, y1 = line.box
        at_left = bool(x0 <= left_limit or visual_entry_marker is not None)
        below_header = y0 >= header_cutoff
        special = bool(
            special_pattern.search(line.text) or visual_entry_marker is not None
        )
        internal_symbol = starts_with_internal_article_symbol(line.text, active_profile)
        relation_label = leading_relation_label(line.text, active_profile)
        rule_result = evaluate_headword_filter_rules(
            user_rules or [],
            raw_lemma=parsed.raw if parsed else "",
            normalized_lemma=parsed.normalized if parsed else "",
            line_text=line.text,
            pos_text=parsed.pos_text if parsed else "",
        )
        has_pos = bool(parsed and parsed.has_pos and not rule_result["pos_excluded"])
        has_inflection = bool(parsed and parsed.has_inflection)
        cjk_marker_prefixed = bool(
            parsed and parsed.descriptor_text == "cjk_marker_pinyin"
        )
        cjk_single_visual = bool(
            _is_chinese_ocr(settings)
            and parsed
            and _is_single_cjk_ideograph(parsed.normalized)
            and parsed.descriptor_text != "chinese_bracketed_headword"
            and not cjk_marker_prefixed
        )
        parser_controls = int(
            getattr(settings, "profile_parser_controls_version", 0) or 0
        ) >= 1
        cjk_profile_active = bool(
            getattr(active_profile, "family", "") == "cjk_visual"
            or getattr(active_profile, "key", "") == "cjk_visual"
            or parser_controls
        )
        cjk_bracketed = bool(
            cjk_profile_active
            and parsed
            and parsed.descriptor_text == "chinese_bracketed_headword"
        )
        cjk_allow_single = bool(
            getattr(settings, "profile_cjk_allow_single_headword", True)
        )
        cjk_allow_bracketed = bool(
            getattr(settings, "profile_cjk_allow_bracketed_headword", True)
        )
        cjk_require_left_edge = bool(
            getattr(settings, "profile_cjk_require_left_edge", True)
        )
        cjk_brackets_in_body = bool(
            getattr(settings, "profile_cjk_brackets_in_body", False)
        )
        cjk_require_visual_evidence = bool(
            getattr(settings, "profile_cjk_require_visual_evidence", False)
        )
        # OCR sometimes merges a large single-character head with a small
        # pronunciation/variant fragment. The generic parser may still extract
        # a one-Han lemma from that merged line; treat it as the same visual
        # candidate family instead of requiring the dedicated parser stage.
        cjk_at_left = bool(
            at_left
            or (cjk_single_visual and x0 <= max(left_limit, round(band.width * 0.18)))
        )
        # A single Han glyph is intentionally *not* treated as a structural
        # descriptor.  Its acceptance must come from strong visual prominence
        # (large display glyph) rather than the mere fact that it is one CJK
        # character.  Bracketed Chinese compounds remain structural cues.
        has_descriptor = bool(parsed and parsed.has_descriptor and not cjk_single_visual)
        internal_locution = bool(
            parsed and parsed.descriptor_text in {"parallel_gloss", "parallel_gloss_ocr"}
        )
        large = height_ratio >= settings.paddle_height_ratio
        bold = boldness_ratio >= settings.paddle_boldness_ratio
        preceding_gap = max(0, y0 - previous_bottom)
        separated = preceding_gap >= gap_threshold
        leading_record_height_ratio = height_ratio
        leading_record: OCRRecord | None = None
        if line.records:
            leading_record = min(line.records, key=lambda record: (record.box[0], record.box[1]))
            leading_record_height_ratio = (
                leading_record.box[3] - leading_record.box[1]
            ) / median_height

        cjk_candidate_right_context: dict[str, Any] | None = None
        cjk_candidate_right_sparse = False
        if (
            cjk_single_visual
            and cjk_allow_single
            and cjk_at_left
            and leading_record is not None
            and bool(getattr(settings, "profile_cjk_right_context_enabled", True))
        ):
            cjk_candidate_right_context = _cjk_candidate_right_context_metrics(
                gray,
                leading_record.box,
                median_height,
                settings,
                header_cutoff=header_cutoff,
            )
            # Candidate-centered sparsity is allowed to rescue a missed visual
            # projection only when the same X-region contains ordinary body ink
            # elsewhere on the page.  This prevents an all-white synthetic/empty
            # region from becoming positive evidence by itself.
            cjk_candidate_right_sparse = bool(
                cjk_candidate_right_context.get("sparse")
                and cjk_candidate_right_context.get("candidate_baseline_supported")
            )

        # Structure carries most of the evidence. POS is deliberately stronger
        # than boldness because body text can also be bold (ANT., FAM., etc.).
        score = (
            (2.0 if parsed else 0.0)
            + (2.0 if (cjk_at_left if cjk_single_visual else at_left) else 0.0)
            + (3.0 if has_pos else 0.0)
            + (2.0 if has_inflection else 0.0)
            + (3.0 if has_descriptor else 0.0)
            + (1.0 if special else 0.0)
            + (0.75 if large else 0.0)
            + (1.0 if bold else 0.0)
            + (0.5 if separated else 0.0)
            + (0.75 if cjk_candidate_right_sparse else 0.0)
        )
        structural_cue = has_pos or has_inflection or has_descriptor or special
        visual_cue = large or bold or separated
        fallback_cue = structural_cue or visual_cue
        # Character dictionaries use oversized single glyphs as entry heads.
        # Their size contrast is much stronger than ordinary bold body text, so
        # use a dedicated gate rather than lowering the global candidate score.
        cjk_single_sparse_context_rescue = bool(
            cjk_single_visual
            and cjk_candidate_right_sparse
            and cjk_at_left
            and leading_record_height_ratio >= 0.72
            and (
                separated
                or bool(
                    parsed
                    and parsed.parser_stage in {
                        "cjk_single_with_pinyin",
                        "chinese_single_character_with_variant",
                    }
                )
                or boldness_ratio >= 0.92
            )
        )
        cjk_single_prominent = bool(
            cjk_single_visual
            and (
                leading_record_height_ratio >= 1.45
                or (
                    leading_record_height_ratio >= 1.28
                    and boldness_ratio >= max(1.08, settings.paddle_boldness_ratio * 0.95)
                    and separated
                )
                or cjk_single_sparse_context_rescue
            )
        )
        looks_like_continuation = bool(parsed and parsed.looks_like_continuation)
        marker_noise = _looks_like_marker_noise_lemma(parsed)
        strong_visual = bool(
            parsed and len(parsed.normalized.strip("-")) >= 3 and at_left and below_header
            and boldness_ratio >= max(1.25, settings.paddle_boldness_ratio * 1.08)
            and height_ratio >= 0.92
        )
        # "普通左缘短词" always means left-edge. The optional
        # relaxation applies only to the explicitly CJK structural channels.
        if cjk_single_visual or cjk_bracketed:
            position_ok = (
                (cjk_at_left if cjk_single_visual else at_left)
                if cjk_require_left_edge else True
            )
        else:
            position_ok = at_left
        base_eligible = bool(
            parsed and parsed.normalized and below_header and position_ok
        )
        cjk_bracket_visual_supported = bool(large or bold)
        cjk_bracket_extra_required = bool(
            cjk_bracketed
            and (cjk_brackets_in_body or cjk_require_visual_evidence)
        )
        ordinary_accept = bool(
            base_eligible
            and not cjk_single_visual
            and (not cjk_bracketed or cjk_allow_bracketed)
            and (
                not cjk_bracket_extra_required
                or cjk_bracket_visual_supported
            )
            and not looks_like_continuation
            and not marker_noise
            and score >= settings.paddle_min_candidate_score
            and (structural_cue or not settings.paddle_require_pos_or_symbol)
            and (fallback_cue or not settings.paddle_require_visual_cue)
        )
        cjk_single_strong_visual = bool(
            cjk_single_prominent
            and (
                leading_record_height_ratio >= 1.55
                or (
                    leading_record_height_ratio >= 1.35
                    and boldness_ratio >= max(1.12, settings.paddle_boldness_ratio)
                    and separated
                )
                or cjk_single_sparse_context_rescue
            )
        )
        cjk_single_accept = bool(
            base_eligible
            and cjk_single_visual
            and (not cjk_profile_active or cjk_allow_single)
            and cjk_single_prominent
            and (
                not cjk_profile_active
                or not cjk_require_visual_evidence
                or cjk_single_strong_visual
            )
            and not looks_like_continuation
            and not marker_noise
        )
        # Explicit reject rules win. Explicit accept rules may rescue a parsed,
        # left-aligned body candidate that fails built-in structural/visual
        # thresholds, but cannot turn arbitrary OCR noise outside the column
        # entry zone into a marker.
        is_headword = bool(
            base_eligible
            and not internal_symbol
            and not relation_label
            and not internal_locution
            and not rule_result["rejected"]
            and (ordinary_accept or cjk_single_accept or rule_result["accepted"])
        )
        if is_headword:
            reject_reason = ""
        elif internal_symbol:
            reject_reason = "internal_article_symbol"
        elif relation_label:
            reject_reason = "internal_relation_label"
        elif internal_locution:
            reject_reason = "internal_locution"
        elif rule_result["rejected"]:
            reject_reason = "user_reject_rule"
        elif not parsed:
            reject_reason = "lemma_parse_failed"
        elif cjk_profile_active and cjk_single_visual and not cjk_allow_single:
            reject_reason = "cjk_single_headword_disabled"
        elif cjk_bracketed and not cjk_allow_bracketed:
            reject_reason = "cjk_bracketed_headword_disabled"
        elif cjk_bracket_extra_required and not cjk_bracket_visual_supported:
            reject_reason = "cjk_bracket_needs_visual_evidence"
        elif (
            cjk_profile_active
            and cjk_single_visual
            and cjk_require_visual_evidence
            and cjk_single_prominent
            and not cjk_single_strong_visual
        ):
            reject_reason = "cjk_single_needs_stronger_visual_evidence"
        elif not position_ok:
            reject_reason = "not_at_column_left"
        elif not below_header:
            reject_reason = "above_header_cutoff"
        elif looks_like_continuation:
            reject_reason = "continuation_fragment"
        elif marker_noise:
            reject_reason = "marker_glyph_ocr_noise"
        elif cjk_single_visual and not cjk_single_prominent:
            reject_reason = "cjk_single_not_visually_prominent"
        elif settings.paddle_require_pos_or_symbol and not structural_cue:
            reject_reason = "missing_pos_inflection_descriptor_or_symbol"
        elif score < settings.paddle_min_candidate_score:
            reject_reason = "score_below_threshold"
        elif settings.paddle_require_visual_cue and not fallback_cue:
            reject_reason = "missing_structure_or_visual_cue"
        else:
            reject_reason = "candidate_rejected"
        coarse_band_y = max(0, y0 - row_padding)
        if visual_entry_marker is not None:
            marker_coarse_y = max(
                0, int(visual_entry_marker["y0"]) - max(1, int(row_padding))
            )
            coarse_band_y = min(coarse_band_y, marker_coarse_y)
        # The first printed entry is a special geometry case: there is no
        # preceding line and therefore no inter-line whitespace valley. Locate
        # the first sustained ink row instead of applying the ordinary valley rule.
        has_prior_content_line = previous_bottom > header_cutoff
        if is_headword and not has_prior_content_line:
            refined_band_y, separator_refinement = refine_first_content_y(
                separator_gray,
                coarse_band_y,
                max(2, round(median_height)),
                settings,
                reference_to_canonical_scale=reference_scale,
                lower_bound=header_cutoff,
            )
        elif is_headword and _is_chinese_ocr(settings):
            refined_band_y, separator_refinement = refine_separator_y_adaptive(
                separator_gray,
                coarse_band_y,
                max(2, round(median_height)),
                settings,
                reference_to_canonical_scale=reference_scale,
                lower_bound=header_cutoff,
                content_top=(int(image_boundary.get("ink_onset_y", y0)) if image_boundary else y0),
                preceding_gap_hint=preceding_gap,
            )
        elif is_headword:
            refined_band_y, separator_refinement = refine_separator_y(
                separator_gray,
                coarse_band_y,
                max(2, y1 - y0),
                settings,
                reference_to_canonical_scale=reference_scale,
                lower_bound=header_cutoff,
            )
        else:
            refined_band_y = coarse_band_y
            separator_refinement = {"enabled": False, "reason": "candidate_rejected"}

        if is_headword and image_boundary is not None and has_prior_content_line:
            boundary_y = int(image_boundary.get("y", refined_band_y))
            previous_refined_y = int(refined_band_y)
            # The mutually matched image boundary is an independent geometry
            # observation. Use its lower blank edge as the final separator while
            # preserving the OCR-only refinement in diagnostics for fallback.
            refined_band_y = max(header_cutoff, min(separator_gray.shape[0] - 1, boundary_y))
            separator_refinement = dict(separator_refinement or {})
            separator_refinement.update({
                "image_boundary_matched": True,
                "pre_boundary_refined_y": previous_refined_y,
                "image_boundary_y": int(boundary_y),
                "image_boundary_ink_onset_y": int(image_boundary.get("ink_onset_y", boundary_y)),
                "image_boundary_blank_rows": int(image_boundary.get("blank_rows", 0)),
                "image_boundary_strength": float(image_boundary.get("strength", 0.0)),
                "image_boundary_match_method": str(image_boundary.get("match_method", "mutual_nearest_y")),
                "reason": "ocr_image_boundary_mutual_match",
                "refined_y": int(refined_band_y),
                "shift": int(refined_band_y) - int(coarse_band_y),
            })
        source_y = source_top + refined_band_y
        coarse_source_y = source_top + coarse_band_y
        anchor_band_y = int((separator_refinement or {}).get("anchor_y", coarse_band_y))
        anchor_source_y = source_top + anchor_band_y
        word = parsed.normalized if parsed else ""
        diagnostics.append({
            "text": line.text,
            "raw_headword": parsed.raw if parsed else "",
            "corrected_headword": parsed.corrected_raw if parsed else "",
            "ocr_parse_text": parsed.parse_text if parsed else line.text,
            "ocr_repairs": list(dict.fromkeys((list(parsed.ocr_repairs) if parsed else []) + list(line.logical_repairs))),
            "logical_repairs": list(line.logical_repairs),
            "normalized_headword": word,
            # Keep the legacy key for tools that already read v1.4 reports.
            "extracted": word,
            "pos_cue": parsed.pos_text if parsed else "",
            "inflection_cue": parsed.inflection_text if parsed else "",
            "descriptor_cue": parsed.descriptor_text if parsed else "",
            "variants": list(parsed.variants) if parsed else [],
            "usage_cue": parsed.usage_text if parsed else "",
            "definition_preview": (parsed.definition_text[:160] if parsed else ""),
            "parser_stage": parsed.parser_stage if parsed else "lemma",
            "parser_trace": list(parsed.parser_trace) if parsed else ["lemma:failed"],
            "bug_types": list(parsed.bug_types) if parsed else ["LEMMA_PARSE_FAILED"],
            "looks_like_continuation": bool(parsed and parsed.looks_like_continuation),
            "continuation_reason": parsed.continuation_reason if parsed else "",
            "confidence": round(line.confidence, 6),
            "box": list(line.box),
            "source_y": source_y,
            "coarse_source_y": coarse_source_y,
            "anchor_source_y": anchor_source_y,
            "separator_refinement": separator_refinement,
            "image_boundary_match": dict(image_boundary) if image_boundary is not None else None,
            "score": round(score, 3),
            "accepted": is_headword,
            "reject_reason": reject_reason,
            "user_rule": {
                "rejected": bool(rule_result["rejected"]),
                "accepted": bool(rule_result["accepted"]),
                "pos_excluded": bool(rule_result["pos_excluded"]),
                "reject_rule": rule_result["reject_rule"],
                "accept_rule": rule_result["accept_rule"],
                "pos_exclude_rule": rule_result["pos_exclude_rule"],
            },
            "features": {
                "at_left": at_left,
                "below_header": below_header,
                "has_pos": has_pos,
                "has_inflection": has_inflection,
                "has_descriptor": has_descriptor,
                "structural_cue": structural_cue,
                "cjk_single_visual": cjk_single_visual,
                "cjk_at_left": cjk_at_left,
                "cjk_single_prominent": cjk_single_prominent,
                "cjk_single_accept": cjk_single_accept,
                "cjk_single_strong_visual": cjk_single_strong_visual,
                "cjk_single_sparse_context_rescue": cjk_single_sparse_context_rescue,
                **_cjk_candidate_right_context_features(
                    cjk_candidate_right_context
                ),
                "cjk_candidate_right_baseline_supported": bool(
                    cjk_candidate_right_context
                    and cjk_candidate_right_context.get("candidate_baseline_supported")
                ),
                "visual_entry_marker": bool(visual_entry_marker),
                "visual_entry_marker_type": (
                    str(visual_entry_marker.get("type") or "")
                    if visual_entry_marker else ""
                ),
                "visual_entry_marker_symbol": (
                    str(visual_entry_marker.get("symbol") or "")
                    if visual_entry_marker else ""
                ),
                "visual_entry_marker_density": (
                    float(visual_entry_marker.get("density") or 0.0)
                    if visual_entry_marker else 0.0
                ),
                "visual_entry_marker_center_delta": (
                    float(visual_entry_marker.get("center_delta") or 0.0)
                    if visual_entry_marker else 0.0
                ),
                "cjk_marker_prefixed": cjk_marker_prefixed,
                "cjk_bracketed": cjk_bracketed,
                "cjk_bracket_visual_supported": cjk_bracket_visual_supported,
                "cjk_bracket_extra_required": cjk_bracket_extra_required,
                "cjk_allow_single": cjk_allow_single,
                "cjk_allow_bracketed": cjk_allow_bracketed,
                "cjk_require_left_edge": cjk_require_left_edge,
                "strong_visual_fallback": strong_visual,
                "image_boundary_supported": bool(image_boundary is not None),
                "marker_noise": marker_noise,
                "ordinary_accept": ordinary_accept,
                "forced_accept": bool(rule_result["accepted"]),
                "forced_reject": bool(rule_result["rejected"]),
                "looks_like_continuation": looks_like_continuation,
                "has_prior_content_line": has_prior_content_line,
                "special_symbol": special,
                "internal_article_symbol": internal_symbol,
                "internal_relation_label": relation_label,
                "internal_locution": internal_locution,
                "height_ratio": round(float(height_ratio), 4),
                "leading_record_height_ratio": round(float(leading_record_height_ratio), 4),
                "boldness_ratio": round(float(boldness_ratio), 4),
                "preceding_gap": round(float(preceding_gap), 2),
            },
            "members": [asdict(member) for member in line.records],
        })
        if is_headword:
            accepted.append((score + line.confidence, Entry(
                word=word, x=source_column_x, y=source_y,
                confidence=float(line.confidence), ocr_source=engine_name,
            )))
        previous_bottom = max(previous_bottom, y1)

    # Chinese character dictionaries frequently mix ordinary-size bracketed
    # compounds with oversized single-character heads.  Recover the latter from
    # a left-strip visual projection even when OCR merged the glyph with nearby
    # pronunciation/variant text or shifted its box slightly to the right.
    parser_controls = int(
        getattr(settings, "profile_parser_controls_version", 0) or 0
    ) >= 1
    if _is_chinese_ocr(settings) and (
        not parser_controls
        or bool(getattr(settings, "profile_cjk_allow_single_headword", True))
    ):
        zone_width, visual_runs = _cjk_visual_projection_runs(
            gray, header_cutoff, settings, reference_scale
        )
        for run_start, run_end in visual_runs:
            right_context = _cjk_right_context_metrics(
                gray,
                (run_start, run_end),
                zone_width,
                settings,
                header_cutoff=header_cutoff,
            )
            word, confidence, matched_record = _cjk_word_for_visual_run(
                records,
                (run_start, run_end),
                zone_width,
                settings,
                active_profile,
                right_context,
            )
            if not word or matched_record is None:
                continue
            coarse_band_y = max(header_cutoff, run_start - row_padding)
            prior_record_bottom = max(
                (int(record.box[3]) for record in records if int(record.box[3]) <= run_start),
                default=header_cutoff,
            )
            visual_gap_hint = max(0, run_start - prior_record_bottom)
            refined_band_y, visual_separator_refinement = refine_separator_y_adaptive(
                separator_gray,
                coarse_band_y,
                max(2, round(median_height)),
                settings,
                reference_to_canonical_scale=reference_scale,
                lower_bound=header_cutoff,
                content_top=run_start,
                preceding_gap_hint=visual_gap_hint,
            )
            source_y = source_top + refined_band_y
            visual_anchor_band_y = int((visual_separator_refinement or {}).get("anchor_y", coarse_band_y))
            visual_anchor_source_y = source_top + visual_anchor_band_y
            run_center_source = source_top + (run_start + run_end) // 2
            run_height = max(1, run_end - run_start)

            # If the OCR grammar path already accepted this physical glyph, do
            # not create a second candidate.  Compare the OCR box with the ink
            # run rather than comparing separator-marker Y values: the latter
            # can legitimately differ by 20+ pixels for a large Han glyph.
            existing_cjk = _accepted_cjk_row_for_visual_run(
                diagnostics, run_start, run_end, word
            )
            if existing_cjk is not None:
                # The OCR/grammar path has already produced the entry boundary.
                # The visual run is confirmation/de-duplication evidence only;
                # it must NOT replace a valid separator with a lower line inside
                # the same entry (for example between 播 ba and its Bộ:/radical
                # metadata).  Keep the original marker and store the visual
                # geometry separately for diagnostics.
                existing_cjk.setdefault(
                    "ocr_coarse_source_y", existing_cjk.get("coarse_source_y")
                )
                existing_cjk["visual_confirmation_source_y"] = source_y
                existing_cjk["visual_confirmation_anchor_source_y"] = (
                    visual_anchor_source_y
                )
                existing_cjk["visual_confirmation_separator_refinement"] = (
                    visual_separator_refinement
                )
                features = existing_cjk.setdefault("features", {})
                features["cjk_visual_projection_confirmed"] = True
                features["cjk_visual_run_height"] = run_height
                features["cjk_visual_zone_width"] = zone_width
                features["cjk_visual_run_start"] = int(run_start)
                features["cjk_visual_run_end"] = int(run_end)
                features.update(_cjk_right_context_features(right_context))
                trace = existing_cjk.setdefault("parser_trace", [])
                if "chinese_visual_projection_confirmed" not in trace:
                    trace.append("chinese_visual_projection_confirmed")
                continue

            # Legacy marker-Y proximity is retained as a second guard for rows
            # whose OCR box is unavailable in an imported/cache diagnostic.
            if any(abs(entry.y - source_y) <= max(3, round(run_height * 0.75)) for _rank, entry in accepted):
                continue

            # Reuse the closest diagnostic row when possible so dual-OCR
            # alignment sees one candidate rather than an artificial duplicate.
            nearest: dict[str, Any] | None = None
            nearest_distance = float("inf")
            for row in diagnostics:
                if "meta" in row:
                    continue
                box = row.get("box") or []
                if not isinstance(box, list) or len(box) != 4:
                    continue
                row_center_source = source_top + (int(box[1]) + int(box[3])) / 2.0
                distance = abs(row_center_source - run_center_source)
                if distance <= run_height * 0.80 and distance < nearest_distance:
                    nearest = row
                    nearest_distance = distance

            if nearest is not None:
                nearest["normalized_headword"] = word
                nearest["extracted"] = word
                nearest["accepted"] = True
                nearest["reject_reason"] = ""
                nearest["source_y"] = source_y
                nearest["coarse_source_y"] = source_top + coarse_band_y
                nearest["anchor_source_y"] = visual_anchor_source_y
                nearest["separator_refinement"] = visual_separator_refinement
                context_bonus = 0.75 if right_context.get("sparse") else 0.0
                nearest["score"] = max(
                    float(nearest.get("score") or 0.0), 8.0 + context_bonus
                )
                features = nearest.setdefault("features", {})
                features["cjk_visual_projection_rescue"] = True
                features["cjk_visual_run_height"] = run_height
                features["cjk_visual_zone_width"] = zone_width
                features.update(_cjk_right_context_features(right_context))
                nearest.setdefault("parser_trace", []).append("chinese_visual_projection_rescue")
                nearest["parser_stage"] = "chinese_visual_projection_rescue"
            else:
                diagnostics.append({
                    "text": matched_record.text,
                    "raw_headword": word,
                    "corrected_headword": word,
                    "ocr_parse_text": matched_record.text,
                    "ocr_repairs": [],
                    "logical_repairs": [],
                    "normalized_headword": word,
                    "extracted": word,
                    "pos_cue": "",
                    "inflection_cue": "",
                    "descriptor_cue": "chinese_single_character_visual",
                    "variants": [],
                    "usage_cue": "",
                    "definition_preview": "",
                    "parser_stage": "chinese_visual_projection_rescue",
                    "parser_trace": ["chinese_visual_projection_rescue"],
                    "bug_types": [],
                    "looks_like_continuation": False,
                    "continuation_reason": "",
                    "confidence": round(confidence, 6),
                    "box": list(matched_record.box),
                    "source_y": source_y,
                    "coarse_source_y": source_top + coarse_band_y,
                    "anchor_source_y": visual_anchor_source_y,
                    "separator_refinement": visual_separator_refinement,
                    "score": 8.0 + (
                        0.75 if right_context.get("sparse") else 0.0
                    ),
                    "accepted": True,
                    "reject_reason": "",
                    "user_rule": {
                        "rejected": False, "accepted": False, "pos_excluded": False,
                        "reject_rule": "", "accept_rule": "", "pos_exclude_rule": "",
                    },
                    "features": {
                        "at_left": True,
                        "below_header": True,
                        "has_pos": False,
                        "has_inflection": False,
                        "has_descriptor": False,
                        "structural_cue": False,
                        "cjk_single_visual": True,
                        "cjk_at_left": True,
                        "cjk_single_prominent": True,
                        "cjk_single_accept": True,
                        "cjk_visual_projection_rescue": True,
                        "cjk_visual_run_height": run_height,
                        "cjk_visual_zone_width": zone_width,
                        **_cjk_right_context_features(right_context),
                        "strong_visual_fallback": True,
                        "marker_noise": False,
                        "ordinary_accept": False,
                        "forced_accept": False,
                        "forced_reject": False,
                        "looks_like_continuation": False,
                        "has_prior_content_line": True,
                        "special_symbol": False,
                        "internal_article_symbol": False,
                        "internal_relation_label": False,
                        "internal_locution": False,
                        "height_ratio": round(run_height / median_height, 4),
                        "leading_record_height_ratio": round(run_height / median_height, 4),
                        "boldness_ratio": 0.0,
                        "preceding_gap": 0.0,
                    },
                    "members": [asdict(matched_record)],
                })
            accepted.append((8.0 + confidence, Entry(
                word=word, x=source_column_x, y=source_y,
                confidence=confidence, ocr_source=engine_name,
            )))

    accepted.sort(key=lambda item: item[1].y)
    deduplicated: list[tuple[float, Entry]] = []
    tolerance = max(2, round(character_height * 0.5))
    for item in accepted:
        if deduplicated and item[1].y - deduplicated[-1][1].y <= tolerance:
            if item[0] > deduplicated[-1][0]:
                deduplicated[-1] = item
        else:
            deduplicated.append(item)
    diagnostics.insert(0, {
        "meta": {
            "header_cutoff_band_y": header_cutoff,
            "header_cutoff_canonical_v": source_top + header_cutoff,
            "line_count": len(lines),
            "left_limit_band_x": left_limit,
            "separator_band_width": int(separator_gray.shape[1]),
            "separator_roi_width_ratio": int(getattr(settings, "paddle_separator_roi_width_ratio", 60)),
            "image_separator_candidates": image_separator_candidates,
            "image_separator_match_count": len(image_boundary_matches),
            "user_filter_rule_count": len(user_rules or []),
        }
    })
    return [entry for _, entry in deduplicated], diagnostics


def _attach_source_candidate_coordinates(
    diagnostics: list[dict[str, Any]],
    geometry: "Geometry",
    column: int,
) -> None:
    """Attach explicit canonical and original-image coordinates to candidates."""
    for item in diagnostics:
        if "meta" in item:
            meta = item.get("meta") or {}
            meta["candidate_coordinate_space"] = "canonical_full_resolution_pixels"
            meta["source_coordinate_space"] = "source_image_pixels"
            meta["ocr_box_coordinate_space"] = "ocr_band_local_pixels"
            if meta.get("header_cutoff_canonical_v") is not None:
                try:
                    cutoff_v = int(meta["header_cutoff_canonical_v"])
                    cutoff_u = int(geometry.x_at(column, cutoff_v))
                    sx, sy = geometry.canonical_to_source(cutoff_u, cutoff_v)
                    meta["header_cutoff_source_point"] = [int(sx), int(sy)]
                except (TypeError, ValueError):
                    pass
            continue

        # Low-level filtering historically called these values source_y even
        # though they were reading-axis canonical V. Convert them once here.
        try:
            canonical_v = int(item.get("canonical_v", item.get("source_y", 0)))
        except (TypeError, ValueError):
            canonical_v = 0
        try:
            coarse_v = int(
                item.get(
                    "coarse_canonical_v",
                    item.get("coarse_source_y", canonical_v),
                )
            )
        except (TypeError, ValueError):
            coarse_v = canonical_v
        try:
            anchor_v = int(
                item.get(
                    "anchor_canonical_v",
                    item.get("anchor_source_y", coarse_v),
                )
            )
        except (TypeError, ValueError):
            anchor_v = coarse_v

        canonical_u = int(geometry.x_at(column, canonical_v))
        source_x, source_y = geometry.canonical_to_source(canonical_u, canonical_v)
        coarse_u = int(geometry.x_at(column, coarse_v))
        coarse_source_x, coarse_source_y = geometry.canonical_to_source(
            coarse_u, coarse_v
        )
        anchor_u = int(geometry.x_at(column, anchor_v))
        anchor_source_x, anchor_source_y = geometry.canonical_to_source(
            anchor_u, anchor_v
        )

        item["canonical_u"] = canonical_u
        item["canonical_v"] = canonical_v
        item["coarse_canonical_v"] = coarse_v
        item["anchor_canonical_v"] = anchor_v
        item["source_x"] = int(source_x)
        item["source_y"] = int(source_y)
        item["coarse_source_x"] = int(coarse_source_x)
        item["coarse_source_y"] = int(coarse_source_y)
        item["anchor_source_x"] = int(anchor_source_x)
        item["anchor_source_y"] = int(anchor_source_y)


def _candidate_axis_v(candidate: dict[str, Any] | None) -> int | None:
    if not candidate:
        return None
    value = candidate.get("canonical_v", candidate.get("source_y"))
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _image_cache_fingerprint(image: Image.Image) -> str:
    """Return an exact normalized-pixel hash for raw OCR cache invalidation."""
    rgb = normalize_page_rgb(image)
    digest = hashlib.sha256()
    digest.update(f"{rgb.width}x{rgb.height}|RGB|".encode("ascii"))
    digest.update(rgb.tobytes())
    return digest.hexdigest()


def _cache_signature(image: Image.Image, geometry: "Geometry", settings: AppSettings) -> str:
    # Only OCR-input-affecting settings belong here. Candidate rules are
    # intentionally omitted so users can tune regex/weights and reuse cached
    # raw OCR without re-running the model.
    data = {
        "version": 3,
        "image_size": list(image.size),
        "image_fingerprint": _image_cache_fingerprint(image),
        "layout_transform": geometry.transform.kind,
        "geometry_coordinate_version": int(
            getattr(settings, "geometry_coordinate_version", 0) or 0
        ),
        "paths": [path.points for path in geometry.column_paths],
        "geometry_top": int(geometry.top),
        "geometry_bottom": int(geometry.bottom),
        "band_width": settings.paddle_band_width,
        "band_width_ratio": max(1, min(100, int(getattr(settings, "paddle_band_width_ratio", 100)))),
        "band_left_margin": settings.paddle_band_left_margin,
        "language": _paddle_language(settings),
        "device": settings.paddle_device,
        "ocr_version": settings.paddle_ocr_version,
        "preprocessing": str(getattr(settings, "paddle_preprocessing", "original")),
        "max_input_side": int(getattr(settings, "paddle_max_input_side", 2800)),
        "use_textline_orientation": bool(getattr(settings, "paddle_use_textline_orientation", False)),
        "raw_rec_threshold": _RAW_OCR_THRESHOLD,
        "use_paddleocr": bool(getattr(settings, "paddle_use_paddleocr", True)),
    }
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()



def _records_as_merged_lines(records: list[OCRRecord], settings: AppSettings) -> list[OCRLine]:
    return group_ocr_records([record for record in records if record.text], settings.paddle_line_merge_y_ratio)


def _candidate_rows(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in diagnostics if "meta" not in item]


def _alphabetical_sort_key(word: str) -> str:
    """Approximate Spanish dictionary collation for anomaly detection only."""
    value = (word or "").casefold().strip()
    # Preserve ñ as distinct from n while stripping acute/diaeresis accents.
    value = value.replace("ñ", "\ue000")
    value = "".join(
        ch for ch in unicodedata.normalize("NFD", value)
        if unicodedata.category(ch) != "Mn"
    )
    value = value.replace("\ue000", "n~")
    return "".join(ch for ch in value if ch.isalpha() or ch == "~")


def _annotate_alphabetical_warnings(
    report_columns: list[dict[str, Any]],
    page_sections: list[PageSection] | None = None,
    *,
    top_v: int | None = None,
    bottom_v: int | None = None,
) -> list[dict[str, Any]]:
    """Annotate, never reject, order anomalies along the real page reading path."""
    warnings: list[dict[str, Any]] = []
    effective_sections = None
    if page_sections and top_v is not None and bottom_v is not None:
        effective_sections = normalize_page_sections(page_sections, int(top_v), int(bottom_v))

    for engine in ("paddle", "tesseract", "lens"):
        seq: list[tuple[int, int, dict[str, Any], str]] = []
        for col in report_columns:
            diagnostics = (
                col.get("candidates", []) if engine == "paddle"
                else (col.get(engine, {}) or {}).get("candidates", [])
            )
            col_idx = int(col.get("column", 0))
            for cand in _candidate_rows(diagnostics):
                cand["alphabetical_warning"] = ""
                if not cand.get("accepted"):
                    continue
                lemma = str(cand.get("normalized_headword", ""))
                key = _alphabetical_sort_key(lemma)
                if not key:
                    continue
                axis_v = _candidate_axis_v(cand) or 0
                section_idx = (
                    section_index_for_v(
                        axis_v, effective_sections, int(top_v), int(bottom_v),
                    )
                    if effective_sections is not None else 0
                )
                seq.append((section_idx, col_idx, cand, key))

        seq.sort(key=lambda item: (
            item[0], item[1], _candidate_axis_v(item[2]) or 0,
        ))
        for i, (section_idx, col_idx, cand, key) in enumerate(seq):
            prev_key = seq[i - 1][3] if i > 0 else ""
            next_key = seq[i + 1][3] if i + 1 < len(seq) else ""
            prev_lemma = str(seq[i - 1][2].get("normalized_headword", "")) if i > 0 else ""
            next_lemma = str(seq[i + 1][2].get("normalized_headword", "")) if i + 1 < len(seq) else ""
            warning = ""
            if prev_key and key < prev_key:
                warning = f"alphabetical_backtrack_vs:{prev_lemma}"
            elif prev_key and next_key and prev_key <= next_key and key > next_key:
                warning = f"alphabetical_forward_outlier_between:{prev_lemma}|{next_lemma}"
            if warning:
                cand["alphabetical_warning"] = warning
                warnings.append({
                    "engine": engine,
                    "section": section_idx + 1,
                    "column": col_idx,
                    "source_y": cand.get("source_y"),
                    "lemma": cand.get("normalized_headword", ""),
                    "warning": warning,
                })
    return warnings


def _apply_alphabetical_warnings_to_entries(
    report_columns: list[dict[str, Any]], entries: list[Entry], tolerance: int = 5,
) -> None:
    warning_candidates: list[tuple[str, int, str, str]] = []
    for col in report_columns:
        for engine, diagnostics in (
            ("paddle", col.get("candidates", [])),
            ("tesseract", (col.get("tesseract", {}) or {}).get("candidates", [])),
            ("lens", (col.get("lens", {}) or {}).get("candidates", [])),
        ):
            for cand in _candidate_rows(diagnostics):
                warning = str(cand.get("alphabetical_warning", ""))
                if warning and cand.get("accepted"):
                    warning_candidates.append((
                        engine, int(cand.get("source_y", 0)),
                        str(cand.get("normalized_headword", "")), warning,
                    ))
    for entry in entries:
        for engine, y, lemma, warning in warning_candidates:
            if entry.ocr_source == engine and entry.word.casefold() == lemma.casefold() and abs(entry.y - y) <= tolerance:
                entry.alphabetical_warning = warning
                break


def _alignment_key(word: str) -> str:
    """Return a Unicode-safe OCR alignment key.

    v2.8.1 accidentally reduced alignment to ASCII letters/digits, which made
    every Han headword collapse to the empty key.  That could mis-pair Chinese
    OCR rows and, in turn, leave two review candidates for one physical glyph.
    Preserve all Unicode alphanumeric characters while still discarding
    punctuation/spacing and combining marks.
    """
    value = unicodedata.normalize("NFKD", word or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return "".join(ch for ch in value if ch.isalnum()).casefold()


def _lemma_similarity(left: str, right: str) -> float:
    a = _alignment_key(left)
    b = _alignment_key(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _orthographic_similarity(left: str, right: str) -> float:
    """Compare final spellings while preserving meaningful Spanish diacritics."""
    a = re.sub(r"[^\wáéíóúüñ]+", "", unicodedata.normalize("NFC", left or "").casefold(), flags=re.UNICODE)
    b = re.sub(r"[^\wáéíóúüñ]+", "", unicodedata.normalize("NFC", right or "").casefold(), flags=re.UNICODE)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _eligible_alignment_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in _candidate_rows(rows):
        features = item.get("features", {}) or {}
        # Every left-edge OCR row is retained for v2.0 manual review, even if the
        # grammar parser rejected it. Accepted candidates are always retained.
        if item.get("accepted") or features.get("at_left"):
            result.append(item)
    return sorted(result, key=lambda x: _candidate_axis_v(x) or 0)


def _candidate_pair_score(p: dict[str, Any], t: dict[str, Any], tolerance: int) -> float:
    sim = _lemma_similarity(str(p.get("normalized_headword", "")), str(t.get("normalized_headword", "")))
    dy = abs((_candidate_axis_v(p) or 0) - (_candidate_axis_v(t) or 0))
    y_score = max(0.0, 1.0 - dy / max(1.0, tolerance * 2.5))
    return 0.72 * sim + 0.28 * y_score


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
    paddle = _eligible_alignment_rows(paddle_diagnostics)
    tess = _eligible_alignment_rows(tess_diagnostics)
    pkeys = [_alignment_key(str(x.get("normalized_headword", ""))) for x in paddle]
    tkeys = [_alignment_key(str(x.get("normalized_headword", ""))) for x in tess]
    matcher = difflib.SequenceMatcher(None, pkeys, tkeys, autojunk=False)
    paired: list[tuple[dict[str, Any] | None, dict[str, Any] | None, str]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                paired.append((paddle[i1 + offset], tess[j1 + offset], "sequence_exact"))
            continue
        pblock = list(range(i1, i2))
        tblock = list(range(j1, j2))
        if tag == "replace" and pblock and tblock:
            options: list[tuple[float, int, int]] = []
            for pi in pblock:
                for tj in tblock:
                    score = _candidate_pair_score(paddle[pi], tess[tj], tolerance)
                    dy = abs(
                        int(_candidate_axis_v(paddle[pi]) or 0)
                        - int(_candidate_axis_v(tess[tj]) or 0)
                    )
                    sim = _lemma_similarity(
                        str(paddle[pi].get("normalized_headword", "")),
                        str(tess[tj].get("normalized_headword", "")),
                    )
                    # Very similar words may drift a little in Y; dissimilar
                    # words must be geometrically close to be considered a pair.
                    if score >= max(0.34, min_similarity * 0.76) and (dy <= tolerance * 2.5 or sim >= max(0.68, min_similarity)):
                        options.append((score, pi, tj))
            used_p: set[int] = set(); used_t: set[int] = set()
            for score, pi, tj in sorted(options, reverse=True):
                if pi in used_p or tj in used_t:
                    continue
                used_p.add(pi); used_t.add(tj)
                paired.append((paddle[pi], tess[tj], "sequence_y_similar"))
            for pi in pblock:
                if pi not in used_p:
                    paired.append((paddle[pi], None, "sequence_paddle_only"))
            for tj in tblock:
                if tj not in used_t:
                    paired.append((None, tess[tj], "sequence_tesseract_only"))
        elif tag == "delete":
            paired.extend((paddle[pi], None, "sequence_paddle_only") for pi in pblock)
        elif tag == "insert":
            paired.extend((None, tess[tj], "sequence_tesseract_only") for tj in tblock)

    result = [_make_ocr_pair(p, t, method) for p, t, method in paired]
    result.sort(key=lambda item: min(
        int(item.get("paddle_y") or 10**9), int(item.get("tesseract_y") or 10**9)
    ))
    return result


def _pairs_need_lens(pairs: list[dict[str, Any]]) -> bool:
    """Return whether the remote third opinion could change/review a decision."""
    for pair in pairs:
        pa = pair.get("paddle_accepted") is True
        ta = pair.get("tesseract_accepted") is True
        if pair.get("lemma_compare") in {"different", "similar"} and (pa or ta):
            return True
        if pair.get("status_compare") == "different":
            return True
        if (pa or ta) and (pair.get("paddle_y") is None or pair.get("tesseract_y") is None):
            return True
        confidences = [
            float(value) for value in (pair.get("paddle_conf"), pair.get("tesseract_conf"))
            if value is not None
        ]
        if (pa or ta) and confidences and min(confidences) < 0.80:
            return True
    return False


def _make_ocr_pair(
    p: dict[str, Any] | None,
    t: dict[str, Any] | None,
    alignment_method: str = "",
) -> dict[str, Any]:
    py = _candidate_axis_v(p)
    ty = _candidate_axis_v(t)
    pl = str(p.get("normalized_headword", "")) if p else ""
    tl = str(t.get("normalized_headword", "")) if t else ""
    sim = _lemma_similarity(pl, tl) if p and t else 0.0
    if p and t:
        if pl and tl and pl.casefold() == tl.casefold():
            lemma_compare = "same"
        elif pl and tl and sim >= 0.82:
            lemma_compare = "similar"
        elif pl and tl:
            lemma_compare = "different"
        else:
            lemma_compare = "missing_lemma"
        pa = bool(p.get("accepted")); ta = bool(t.get("accepted"))
        status_compare = "same" if pa == ta else "different"
        if lemma_compare == "same" and status_compare == "same":
            reason = "agree"
        elif lemma_compare in {"different", "similar"}:
            reason = "lemma_conflict" if lemma_compare == "different" else "lemma_variant"
        else:
            reason = "acceptance_conflict"
    elif p:
        lemma_compare = "paddle_only"; status_compare = "paddle_only"; reason = "paddle_only"
    else:
        lemma_compare = "tesseract_only"; status_compare = "tesseract_only"; reason = "tesseract_only"
    return {
        "paddle_y": py,
        "paddle_source_x": p.get("source_x") if p else None,
        "paddle_source_y": p.get("source_y") if p else None,
        "paddle_coarse_y": (
            int(p.get("coarse_canonical_v", py)) if p and py is not None else None
        ),
        "paddle_anchor_y": (
            int(p.get("anchor_canonical_v", py)) if p and py is not None else None
        ),
        "paddle_separator_refinement": dict(p.get("separator_refinement", {}) or {}) if p else {},
        "paddle_image_boundary_match": dict(p.get("image_boundary_match", {}) or {}) if p else {},
        "paddle_box": p.get("box") if p else None,
        "paddle_conf": p.get("confidence") if p else None,
        "paddle_accepted": bool(p.get("accepted")) if p else None,
        "paddle_score": p.get("score") if p else None,
        "paddle_lemma": pl,
        "paddle_raw": str(p.get("raw_headword", "")) if p else "",
        "paddle_corrected": str(p.get("corrected_headword", "")) if p else "",
        "paddle_pos": str(p.get("pos_cue", "")) if p else "",
        "paddle_repairs": list(p.get("ocr_repairs", []) or []) if p else [],
        "paddle_text": str(p.get("text", "")) if p else "",
        "paddle_reject_reason": str(p.get("reject_reason", "")) if p else "",
        "paddle_features": dict(p.get("features", {}) or {}) if p else {},
        "paddle_parser_trace": list(p.get("parser_trace", []) or []) if p else [],
        "paddle_bug_types": list(p.get("bug_types", []) or []) if p else [],
        "paddle_alphabetical_warning": str(p.get("alphabetical_warning", "")) if p else "",
        "tesseract_y": ty,
        "tesseract_source_x": t.get("source_x") if t else None,
        "tesseract_source_y": t.get("source_y") if t else None,
        "tesseract_coarse_y": (
            int(t.get("coarse_canonical_v", ty)) if t and ty is not None else None
        ),
        "tesseract_anchor_y": (
            int(t.get("anchor_canonical_v", ty)) if t and ty is not None else None
        ),
        "tesseract_separator_refinement": dict(t.get("separator_refinement", {}) or {}) if t else {},
        "tesseract_image_boundary_match": dict(t.get("image_boundary_match", {}) or {}) if t else {},
        "tesseract_box": t.get("box") if t else None,
        "tesseract_conf": t.get("confidence") if t else None,
        "tesseract_accepted": bool(t.get("accepted")) if t else None,
        "tesseract_score": t.get("score") if t else None,
        "tesseract_lemma": tl,
        "tesseract_raw": str(t.get("raw_headword", "")) if t else "",
        "tesseract_corrected": str(t.get("corrected_headword", "")) if t else "",
        "tesseract_pos": str(t.get("pos_cue", "")) if t else "",
        "tesseract_repairs": list(t.get("ocr_repairs", []) or []) if t else [],
        "tesseract_text": str(t.get("text", "")) if t else "",
        "tesseract_reject_reason": str(t.get("reject_reason", "")) if t else "",
        "tesseract_features": dict(t.get("features", {}) or {}) if t else {},
        "tesseract_parser_trace": list(t.get("parser_trace", []) or []) if t else [],
        "tesseract_bug_types": list(t.get("bug_types", []) or []) if t else [],
        "tesseract_alphabetical_warning": str(t.get("alphabetical_warning", "")) if t else "",
        "lens_y": None,
        "lens_source_x": None,
        "lens_source_y": None,
        "lens_coarse_y": None,
        "lens_anchor_y": None,
        "lens_separator_refinement": {},
        "lens_image_boundary_match": {},
        "lens_box": None,
        "lens_conf": None,
        "lens_accepted": None,
        "lens_score": None,
        "lens_lemma": "",
        "lens_raw": "",
        "lens_corrected": "",
        "lens_pos": "",
        "lens_repairs": [],
        "lens_text": "",
        "lens_reject_reason": "",
        "lens_features": {},
        "lens_parser_trace": [],
        "lens_bug_types": [],
        "lens_alphabetical_warning": "",
        "delta_y": (ty - py) if py is not None and ty is not None else None,
        "lemma_similarity": round(sim, 4) if p and t else "",
        "lemma_compare": lemma_compare,
        "status_compare": status_compare,
        "alignment_method": alignment_method,
        "reason": reason,
    }


def _copy_candidate_to_pair(pair: dict[str, Any], prefix: str, candidate: dict[str, Any]) -> None:
    canonical_v = _candidate_axis_v(candidate)
    if canonical_v is None:
        canonical_v = 0
    pair[f"{prefix}_y"] = canonical_v
    pair[f"{prefix}_coarse_y"] = int(
        candidate.get("coarse_canonical_v", canonical_v)
    )
    pair[f"{prefix}_anchor_y"] = int(
        candidate.get(
            "anchor_canonical_v",
            candidate.get("coarse_canonical_v", canonical_v),
        )
    )
    pair[f"{prefix}_source_x"] = candidate.get("source_x")
    pair[f"{prefix}_source_y"] = candidate.get("source_y")
    pair[f"{prefix}_box"] = candidate.get("box")
    pair[f"{prefix}_separator_refinement"] = dict(candidate.get("separator_refinement", {}) or {})
    pair[f"{prefix}_image_boundary_match"] = dict(candidate.get("image_boundary_match", {}) or {})
    pair[f"{prefix}_conf"] = candidate.get("confidence")
    pair[f"{prefix}_accepted"] = bool(candidate.get("accepted"))
    pair[f"{prefix}_score"] = candidate.get("score")
    pair[f"{prefix}_lemma"] = str(candidate.get("normalized_headword", ""))
    pair[f"{prefix}_raw"] = str(candidate.get("raw_headword", ""))
    pair[f"{prefix}_corrected"] = str(candidate.get("corrected_headword", ""))
    pair[f"{prefix}_pos"] = str(candidate.get("pos_cue", ""))
    pair[f"{prefix}_repairs"] = list(candidate.get("ocr_repairs", []) or [])
    pair[f"{prefix}_text"] = str(candidate.get("text", ""))
    pair[f"{prefix}_reject_reason"] = str(candidate.get("reject_reason", ""))
    pair[f"{prefix}_features"] = dict(candidate.get("features", {}) or {})
    pair[f"{prefix}_parser_trace"] = list(candidate.get("parser_trace", []) or [])
    pair[f"{prefix}_bug_types"] = list(candidate.get("bug_types", []) or [])
    pair[f"{prefix}_alphabetical_warning"] = str(candidate.get("alphabetical_warning", ""))


def _pair_with_lens_candidates(
    pairs: list[dict[str, Any]],
    lens_diagnostics: list[dict[str, Any]],
    tolerance: int,
    min_similarity: float,
) -> list[dict[str, Any]]:
    """Attach Lens rows to the existing Paddle/Tesseract sequence alignment."""
    lens_rows = _eligible_alignment_rows(lens_diagnostics)
    used: set[int] = set()
    for pair in pairs:
        base_y_values = [pair.get("paddle_y"), pair.get("tesseract_y")]
        base_y_values = [int(value) for value in base_y_values if value is not None]
        if not base_y_values:
            continue
        base_y = round(sum(base_y_values) / len(base_y_values))
        base_words = [str(pair.get("paddle_lemma") or ""), str(pair.get("tesseract_lemma") or "")]
        options: list[tuple[float, int]] = []
        for index, candidate in enumerate(lens_rows):
            if index in used:
                continue
            cy = _candidate_axis_v(candidate) or 0
            lemma = str(candidate.get("normalized_headword", ""))
            similarity = max((_lemma_similarity(lemma, word) for word in base_words if word), default=0.0)
            dy = abs(cy - base_y)
            y_score = max(0.0, 1.0 - dy / max(1.0, tolerance * 2.5))
            score = 0.72 * similarity + 0.28 * y_score
            if score >= max(0.34, min_similarity * 0.76) and (dy <= tolerance * 2.5 or similarity >= 0.68):
                options.append((score, index))
        if options:
            _, index = max(options)
            used.add(index)
            _copy_candidate_to_pair(pair, "lens", lens_rows[index])
            pair["lens_alignment_method"] = "sequence_y_similar"

    for index, candidate in enumerate(lens_rows):
        if index in used:
            continue
        pair = _make_ocr_pair(None, None, "sequence_lens_only")
        _copy_candidate_to_pair(pair, "lens", candidate)
        pair.update({
            "lemma_compare": "lens_only",
            "status_compare": "lens_only",
            "reason": "lens_only",
            "lens_alignment_method": "sequence_lens_only",
        })
        pairs.append(pair)
    pairs.sort(key=lambda item: min(
        int(value) for value in (item.get("paddle_y"), item.get("tesseract_y"), item.get("lens_y"))
        if value is not None
    ))
    return pairs


def _engine_quality(pair: dict[str, Any], prefix: str) -> float:
    accepted = pair.get(f"{prefix}_accepted") is True
    score = float(pair.get(f"{prefix}_score") or 0.0)
    conf = float(pair.get(f"{prefix}_conf") or 0.0)
    features = pair.get(f"{prefix}_features", {}) or {}
    repairs = pair.get(f"{prefix}_repairs", []) or []
    q = score + 2.0 * conf + (1.0 if accepted else 0.0)
    if features.get("structural_cue"):
        q += 1.0
    if features.get("strong_visual_fallback"):
        q += 0.35
    if features.get("forced_accept"):
        q += 1.2
    if features.get("forced_reject"):
        q -= 5.0
    q -= min(0.9, 0.08 * len(repairs))
    return q


def _stable_candidate_id(column: int, y: int, ptext: str, ttext: str) -> str:
    # Manual checkbox choices should survive small OCR spelling/bbox changes on
    # a forced refresh. Dictionary rows are far more than 10 source pixels apart,
    # so a quantized Y + column is stable without relying on OCR text.
    qy = int(round(int(y) / 10.0) * 10)
    return f"c{column+1}-y{qy}"


def _issues_for_pair(pair: dict[str, Any], chosen: str, needs_review: bool) -> list[str]:
    issues: list[str] = []
    reason = str(pair.get("reason", ""))
    if reason == "paddle_only": issues.append("PADDLE_ONLY")
    if reason == "tesseract_only": issues.append("TESSERACT_ONLY")
    if reason == "lens_only": issues.append("LENS_ONLY")
    if pair.get("lemma_compare") == "different": issues.append("OCR_CONFLICT")
    elif pair.get("lemma_compare") == "similar": issues.append("OCR_VARIANT")
    if pair.get("status_compare") == "different": issues.append("ACCEPTANCE_CONFLICT")
    if pair.get("lens_y") is not None:
        lens_word = str(pair.get("lens_lemma") or "")
        other_words = [str(pair.get(f"{engine}_lemma") or "") for engine in ("paddle", "tesseract")]
        similarities = [_lemma_similarity(lens_word, word) for word in other_words if word]
        if similarities and max(similarities) < 0.82:
            issues.append("LENS_DISAGREEMENT")
    repairs = list(pair.get(f"{chosen}_repairs", []) or []) if chosen else []
    bug_types = list(pair.get(f"{chosen}_bug_types", []) or []) if chosen else []
    issues.extend(str(x) for x in bug_types)
    for repair in repairs:
        if repair == "MULTILINE_POS" or repair.startswith("MULTILINE_STATE_JOIN"):
            issues.append("MULTILINE_POS")
        if repair == "RIGHT_FRAGMENT_ABSORBED":
            issues.append("SPLIT_OCR_BOX")
    if repairs:
        issues.append("OCR_REPAIR")
    conf = float(pair.get(f"{chosen}_conf") or 0.0) if chosen else 0.0
    if chosen and conf < 0.80:
        issues.append("LOW_CONFIDENCE")
    warning = str(pair.get(f"{chosen}_alphabetical_warning", "")) if chosen else ""
    if warning:
        issues.append("ALPHABETICAL_WARNING")
    reject_reason = str(pair.get(f"{chosen}_reject_reason", "")) if chosen else ""
    reject_map = {
        "lemma_parse_failed": "LEMMA_PARSE_FAILED",
        "missing_pos_inflection_descriptor_or_symbol": "MISSING_STRUCTURE",
        "continuation_fragment": "CONTINUATION_FRAGMENT",
        "marker_glyph_ocr_noise": "MARKER_GLYPH_NOISE",
        "internal_article_symbol": "INTERNAL_ARTICLE_STRUCTURE",
        "internal_relation_label": "INTERNAL_ARTICLE_STRUCTURE",
        "score_below_threshold": "LOW_PARSER_SCORE",
        "not_at_column_left": "NOT_AT_LEFT",
        "internal_locution": "INTERNAL_LOCUTION",
    }
    if reject_reason in reject_map:
        issues.append(reject_map[reject_reason])
    score = float(pair.get(f"{chosen}_score") or 0.0) if chosen else 0.0
    if chosen and score < 5.5:
        issues.append("LOW_PARSER_SCORE")
    if needs_review:
        issues.append("NEEDS_REVIEW")
    return list(dict.fromkeys(issues))


def _arbitrate_pair(
    pair: dict[str, Any],
    column: int,
    canonical_u: int,
    settings: AppSettings,
    *,
    geometry: "Geometry" | None = None,
) -> dict[str, Any]:
    has_p = pair.get("paddle_y") is not None
    has_t = pair.get("tesseract_y") is not None
    has_l = pair.get("lens_y") is not None
    lens_can_vote = str(settings.paddle_lens_mode or "off").lower() != "diagnostic"
    pq = _engine_quality(pair, "paddle") if has_p else -999.0
    tq = _engine_quality(pair, "tesseract") if has_t else -999.0
    lq = _engine_quality(pair, "lens") if has_l else -999.0
    pa = pair.get("paddle_accepted") is True
    ta = pair.get("tesseract_accepted") is True
    sim = float(pair.get("lemma_similarity") or 0.0)
    chosen = ""
    needs_review = False
    decision_reason = ""

    if has_p and has_t:
        if pair.get("lemma_compare") == "same":
            chosen = "paddle" if pq >= tq else "tesseract"
            decision_reason = "dual_agree_higher_quality"
        elif pair.get("lemma_compare") == "similar":
            chosen = "paddle" if pq >= tq else "tesseract"
            decision_reason = "dual_similar_higher_quality"
            needs_review = abs(pq - tq) < settings.paddle_conflict_review_margin
        else:
            if pa != ta:
                chosen = "paddle" if pa else "tesseract"
                decision_reason = "acceptance_wins_conflict"
            else:
                chosen = "paddle" if pq >= tq else "tesseract"
                decision_reason = "conflict_higher_quality"
                needs_review = bool(pa and ta) or abs(pq - tq) < settings.paddle_conflict_review_margin
    elif has_p:
        chosen = "paddle"; decision_reason = "paddle_only"
    elif has_t:
        chosen = "tesseract"; decision_reason = "tesseract_only"
    elif has_l:
        if lens_can_vote:
            chosen = "lens"; decision_reason = "lens_only"
        else:
            decision_reason = "lens_diagnostic_only"

    # Lens acts as a third vote. When it agrees with one side of a real P/T
    # conflict, the agreement cluster wins; when all three agree, quality picks
    # the cleanest spelling. A lone Lens disagreement never silently overturns
    # two agreeing local engines.
    if has_l and lens_can_vote and (has_p or has_t):
        lens_word = str(pair.get("lens_lemma") or "")
        local_engines = [engine for engine, present in (("paddle", has_p), ("tesseract", has_t)) if present]
        agreeing_local = [
            engine for engine in local_engines
            if _orthographic_similarity(lens_word, str(pair.get(f"{engine}_lemma") or "")) >= 0.94
        ]
        if agreeing_local:
            # If both local engines agree with Lens, this is full consensus. If
            # only one agrees, Lens resolves the local conflict in its favour.
            cluster = agreeing_local + ["lens"]
            qualities = {"paddle": pq, "tesseract": tq, "lens": lq}
            chosen = max(cluster, key=lambda engine_name: qualities[engine_name])
            decision_reason = (
                "three_engine_agree_higher_quality"
                if len(agreeing_local) == len(local_engines) and len(local_engines) == 2
                else "lens_breaks_local_conflict"
            )
            if decision_reason == "lens_breaks_local_conflict":
                needs_review = False
        elif len(local_engines) >= 2 and _orthographic_similarity(
            str(pair.get("paddle_lemma") or ""), str(pair.get("tesseract_lemma") or "")
        ) >= 0.94:
            # Two agreeing local engines outweigh a disagreeing remote result.
            needs_review = bool(pair.get("lens_accepted") is True and lq >= max(pq, tq) - settings.paddle_conflict_review_margin)
            decision_reason = "local_consensus_over_lens"
        else:
            needs_review = bool(pair.get("lens_accepted") is True or needs_review)

    selected = bool(pair.get(f"{chosen}_accepted") is True) if chosen else False
    # When both OCR engines independently agree on the same/similar left-edge
    # lemma, a lost POS glyph should not automatically erase the entry.  Permit
    # a conservative visual-consensus rescue only for high-confidence rows whose
    # rejection reason is specifically missing structure.
    if has_p and has_t and not selected and sim >= 0.90:
        preasons = {str(pair.get("paddle_reject_reason", "")), str(pair.get("tesseract_reject_reason", ""))}
        pfeat = pair.get("paddle_features", {}) or {}; tfeat = pair.get("tesseract_features", {}) or {}
        high_conf = min(float(pair.get("paddle_conf") or 0.0), float(pair.get("tesseract_conf") or 0.0)) >= 0.85
        visual = bool(pfeat.get("strong_visual_fallback") or tfeat.get("strong_visual_fallback"))
        if preasons <= {"missing_pos_inflection_descriptor_or_symbol", ""} and high_conf and visual:
            selected = True
            decision_reason = "dual_consensus_visual_rescue"
            needs_review = True
    # Arbitration may accept a strong Tesseract-only entry without the legacy
    # rescue switch; this is the core v2.0 dual-engine behaviour.
    features = pair.get(f"{chosen}_features", {}) or {} if chosen else {}
    if chosen in {"tesseract", "lens"} and features.get("structural_cue"):
        selected = bool(pair.get(f"{chosen}_accepted") is True)

    y = int(pair.get(f"{chosen}_y") or pair.get("paddle_y") or pair.get("tesseract_y") or pair.get("lens_y") or 0)
    lemma = str(pair.get(f"{chosen}_lemma") or pair.get("paddle_lemma") or pair.get("tesseract_lemma") or pair.get("lens_lemma") or "")
    conf = float(pair.get(f"{chosen}_conf") or 0.0) if chosen else 0.0
    score = float(pair.get(f"{chosen}_score") or 0.0) if chosen else 0.0
    box = pair.get(f"{chosen}_box") or pair.get("paddle_box") or pair.get("tesseract_box") or pair.get("lens_box")
    coarse_y = int(
        pair.get(f"{chosen}_coarse_y")
        or pair.get("paddle_coarse_y")
        or pair.get("tesseract_coarse_y")
        or pair.get("lens_coarse_y")
        or y
    )
    anchor_y = int(
        pair.get(f"{chosen}_anchor_y")
        or pair.get("paddle_anchor_y")
        or pair.get("tesseract_anchor_y")
        or pair.get("lens_anchor_y")
        or coarse_y
    )
    separator_refinement = dict(
        pair.get(f"{chosen}_separator_refinement")
        or pair.get("paddle_separator_refinement")
        or pair.get("tesseract_separator_refinement")
        or pair.get("lens_separator_refinement")
        or {}
    )
    image_boundary_match = dict(
        pair.get(f"{chosen}_image_boundary_match")
        or pair.get("paddle_image_boundary_match")
        or pair.get("tesseract_image_boundary_match")
        or pair.get("lens_image_boundary_match")
        or {}
    )
    issues = _issues_for_pair(pair, chosen, needs_review)
    if decision_reason == "dual_consensus_visual_rescue" and "DUAL_CONSENSUS_RESCUE" not in issues:
        issues.append("DUAL_CONSENSUS_RESCUE")
    candidate_id = _stable_candidate_id(
        column, y, str(pair.get("paddle_text", "")), str(pair.get("tesseract_text", ""))
    )
    if geometry is not None:
        refined_u = int(geometry.x_at(column, y))
        source_x, source_y = geometry.canonical_to_source(refined_u, y)
        coarse_u = int(geometry.x_at(column, coarse_y))
        coarse_source_x, coarse_source_y = geometry.canonical_to_source(
            coarse_u, coarse_y
        )
        anchor_u = int(geometry.x_at(column, anchor_y))
        anchor_source_x, anchor_source_y = geometry.canonical_to_source(
            anchor_u, anchor_y
        )
    else:
        refined_u = int(canonical_u)
        source_x, source_y = int(canonical_u), int(y)
        coarse_u = int(canonical_u)
        coarse_source_x, coarse_source_y = int(canonical_u), int(coarse_y)
        anchor_u = int(canonical_u)
        anchor_source_x, anchor_source_y = int(canonical_u), int(anchor_y)

    return {
        "candidate_id": candidate_id,
        "column": column,
        "coordinate_space": "source_image_pixels",
        "canonical_coordinate_space": "canonical_full_resolution_pixels",
        "canonical_u": int(refined_u),
        "canonical_v": int(y),
        "coarse_canonical_v": int(coarse_y),
        "anchor_canonical_v": int(anchor_y),
        "source_x": int(source_x),
        "source_y": int(source_y),
        "refined_source_y": int(source_y),
        "coarse_source_x": int(coarse_source_x),
        "coarse_source_y": int(coarse_source_y),
        "anchor_source_x": int(anchor_source_x),
        "anchor_source_y": int(anchor_source_y),
        "box": box,
        "original_box": list(box) if isinstance(box, (list, tuple)) and len(box) == 4 else box,
        "separator_refinement": separator_refinement,
        "image_boundary_match": image_boundary_match,
        "position_variant": "refined",
        "selected": selected,
        "word": lemma,
        "final_engine": chosen,
        "confidence": round(conf, 6),
        "score": round(score, 3),
        "quality_paddle": round(pq, 3) if has_p else None,
        "quality_tesseract": round(tq, 3) if has_t else None,
        "quality_lens": round(lq, 3) if has_l else None,
        "needs_review": needs_review,
        "issue_types": issues,
        "decision_reason": decision_reason,
        "alphabetical_warning": str(pair.get(f"{chosen}_alphabetical_warning", "")) if chosen else "",
        "lemma_similarity": sim,
        "paddle": {
            "canonical_v": pair.get("paddle_y"),
            "source_x": pair.get("paddle_source_x"),
            "source_y": pair.get("paddle_source_y"),
            "y": pair.get("paddle_y"),
            "box": pair.get("paddle_box"), "confidence": pair.get("paddle_conf"),
            "accepted": pair.get("paddle_accepted"), "score": pair.get("paddle_score"), "lemma": pair.get("paddle_lemma"),
            "raw": pair.get("paddle_raw"), "corrected": pair.get("paddle_corrected"), "POS": pair.get("paddle_pos"),
            "repairs": pair.get("paddle_repairs"), "text": pair.get("paddle_text"), "reason": pair.get("paddle_reject_reason"),
            "parser_trace": pair.get("paddle_parser_trace"),
        },
        "tesseract": {
            "canonical_v": pair.get("tesseract_y"),
            "source_x": pair.get("tesseract_source_x"),
            "source_y": pair.get("tesseract_source_y"),
            "y": pair.get("tesseract_y"),
            "box": pair.get("tesseract_box"), "confidence": pair.get("tesseract_conf"),
            "accepted": pair.get("tesseract_accepted"), "score": pair.get("tesseract_score"), "lemma": pair.get("tesseract_lemma"),
            "raw": pair.get("tesseract_raw"), "corrected": pair.get("tesseract_corrected"), "POS": pair.get("tesseract_pos"),
            "repairs": pair.get("tesseract_repairs"), "text": pair.get("tesseract_text"), "reason": pair.get("tesseract_reject_reason"),
            "parser_trace": pair.get("tesseract_parser_trace"),
        },
        "lens": {
            "canonical_v": pair.get("lens_y"),
            "source_x": pair.get("lens_source_x"),
            "source_y": pair.get("lens_source_y"),
            "y": pair.get("lens_y"),
            "box": pair.get("lens_box"), "confidence": pair.get("lens_conf"),
            "accepted": pair.get("lens_accepted"), "score": pair.get("lens_score"), "lemma": pair.get("lens_lemma"),
            "raw": pair.get("lens_raw"), "corrected": pair.get("lens_corrected"), "POS": pair.get("lens_pos"),
            "repairs": pair.get("lens_repairs"), "text": pair.get("lens_text"), "reason": pair.get("lens_reject_reason"),
            "parser_trace": pair.get("lens_parser_trace"),
        },
        "alignment_method": pair.get("alignment_method", ""),
        "pair_reason": pair.get("reason", ""),
    }


def _apply_pair_engine_position(
    item: dict[str, Any],
    pair: dict[str, Any],
    prefix: str,
    column: int,
    canonical_u: int,
    geometry: "Geometry" | None,
) -> None:
    """Apply one engine's position without mixing canonical V and source Y."""
    raw_v = pair.get(f"{prefix}_y")
    if raw_v is None:
        return
    canonical_v = int(raw_v)
    coarse_v = int(pair.get(f"{prefix}_coarse_y") or canonical_v)
    anchor_v = int(pair.get(f"{prefix}_anchor_y") or coarse_v)

    if geometry is not None:
        refined_u = int(geometry.x_at(column, canonical_v))
        source_x, source_y = geometry.canonical_to_source(refined_u, canonical_v)
        coarse_u = int(geometry.x_at(column, coarse_v))
        coarse_source_x, coarse_source_y = geometry.canonical_to_source(
            coarse_u, coarse_v
        )
        anchor_u = int(geometry.x_at(column, anchor_v))
        anchor_source_x, anchor_source_y = geometry.canonical_to_source(
            anchor_u, anchor_v
        )
    else:
        refined_u = int(canonical_u)
        source_x = pair.get(f"{prefix}_source_x")
        source_y = pair.get(f"{prefix}_source_y")
        source_x = refined_u if source_x is None else int(source_x)
        source_y = canonical_v if source_y is None else int(source_y)
        coarse_u = refined_u
        coarse_source_x, coarse_source_y = source_x, coarse_v
        anchor_u = refined_u
        anchor_source_x, anchor_source_y = source_x, anchor_v

    item.update({
        "canonical_u": int(refined_u),
        "canonical_v": int(canonical_v),
        "coarse_canonical_v": int(coarse_v),
        "anchor_canonical_v": int(anchor_v),
        "source_x": int(source_x),
        "source_y": int(source_y),
        "refined_source_y": int(source_y),
        "coarse_source_x": int(coarse_source_x),
        "coarse_source_y": int(coarse_source_y),
        "anchor_source_x": int(anchor_source_x),
        "anchor_source_y": int(anchor_source_y),
    })


def _agreement_summary(review_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    exact = similar = conflict = paddle_only = tesseract_only = 0
    both = 0
    lens_used = lens_only = triple_exact = majority_agree = 0
    for row in review_candidates:
        # Original-Y fallback rows are editing alternatives for the same physical
        # headword, not additional OCR observations. Exclude them from page
        # agreement/quality statistics so preserving a fallback cannot lower the
        # reported page confidence.
        if str(row.get("position_variant", "refined")) == "original":
            continue
        p = row.get("paddle", {}) or {}; t = row.get("tesseract", {}) or {}; lens = row.get("lens", {}) or {}
        # Agreement is a headword-quality metric, not a whole-page text metric.
        # Ignore ordinary rejected body rows that are kept only to power the
        # manual checkbox overlay.
        if not (row.get("selected") or p.get("accepted") or t.get("accepted") or row.get("needs_review")):
            continue
        if p.get("y") is not None and t.get("y") is not None:
            both += 1
            pl = str(p.get("lemma") or ""); tl = str(t.get("lemma") or "")
            if pl and tl and pl.casefold() == tl.casefold(): exact += 1
            elif _lemma_similarity(pl, tl) >= 0.82: similar += 1
            else: conflict += 1
        elif p.get("y") is not None:
            paddle_only += 1
        elif t.get("y") is not None:
            tesseract_only += 1
        if lens.get("y") is not None:
            lens_used += 1
            if p.get("y") is None and t.get("y") is None:
                lens_only += 1
            words = [
                str(side.get("lemma") or "")
                for side in (p, t, lens) if side.get("y") is not None and side.get("lemma")
            ]
            if len(words) == 3 and all(_lemma_similarity(words[0], value) >= 0.82 for value in words[1:]):
                triple_exact += 1
            if len(words) >= 2 and max(
                (_lemma_similarity(words[i], words[j]) for i in range(len(words)) for j in range(i + 1, len(words))),
                default=0.0,
            ) >= 0.82:
                majority_agree += 1
    union = max(1, exact + similar + conflict + paddle_only + tesseract_only)
    agreement = (exact + 0.65 * similar) / union
    return {
        "candidate_union": union, "paired": both, "exact": exact, "similar": similar,
        "conflict": conflict, "paddle_only": paddle_only, "tesseract_only": tesseract_only,
        "agreement": round(agreement, 4),
        "lens_used": lens_used, "lens_only": lens_only,
        "triple_agree": triple_exact, "multi_engine_majority": majority_agree,
    }


_QUALITY_SUMMARY_LOCK = threading.Lock()


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Publish OCR/cache text atomically and remove failed temporary files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding=encoding, dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_text(
        path, json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def _tsv_clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = ",".join(str(x) for x in value)
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _candidate_reason(cand: dict[str, Any]) -> str:
    reasons = []
    if cand.get("reject_reason"):
        reasons.append(str(cand.get("reject_reason")))
    if cand.get("parser_stage"):
        reasons.append("stage=" + str(cand.get("parser_stage")))
    bugs = list(cand.get("bug_types", []) or [])
    if bugs:
        reasons.append("bug=" + ",".join(str(x) for x in bugs))
    trace = list(cand.get("parser_trace", []) or [])
    if trace:
        reasons.append("trace=" + ">".join(str(x) for x in trace[:8]))
    if cand.get("alphabetical_warning"):
        reasons.append("WARN:" + str(cand.get("alphabetical_warning")))
    return ";".join(reasons)


def _candidate_tsv_row(
    column: int,
    cand: dict[str, Any],
    raw_status: str | None = None,
    engine: str = "",
    extra_reason: str = "",
) -> str:
    """Return one strict 12-column TSV row.

    ``*_ocr_diagnostics.txt`` is deliberately rectangular: it has exactly one
    header and every following physical line has exactly the same 12 fields.
    Engine/record provenance is kept in the final ``reason`` field so the
    user-requested column order remains unchanged.
    """
    status = raw_status if raw_status is not None else ("accept" if cand.get("accepted") else "reject")
    reason_parts: list[str] = []
    if engine:
        reason_parts.append(f"engine={engine}")
    if raw_status == "raw":
        reason_parts.append("record=raw")
    elif raw_status == "rescued":
        reason_parts.append("record=rescued")
    elif raw_status == "error":
        reason_parts.append("record=error")
    else:
        reason_parts.append("record=candidate")
    candidate_reason = _candidate_reason(cand)
    if candidate_reason:
        reason_parts.append(candidate_reason)
    if extra_reason:
        reason_parts.append(extra_reason)
    values = [
        column,
        cand.get("box", ""),
        f"{float(cand.get('confidence', 0.0)):.4f}" if cand.get("confidence") is not None else "",
        cand.get("text", ""),
        status,
        cand.get("score", ""),
        cand.get("normalized_headword", ""),
        cand.get("raw_headword", ""),
        cand.get("corrected_headword", ""),
        cand.get("pos_cue", ""),
        ";".join(str(x) for x in cand.get("ocr_repairs", []) or []),
        ";".join(reason_parts),
    ]
    return "\t".join(_tsv_clean(v) for v in values)


_DIAGNOSTIC_HEADER = "column\tbox_band_xyxy\tconf\ttext\taccept/reject\tscore\tlemma\traw\tcorrected\tPOS\trepairs\treason"
_COMPARISON_HEADER = (
    "column\tpaddle_canonical_v\tpaddle_box_band_xyxy\tpaddle_conf\tpaddle_accept/reject\tpaddle_score\t"
    "paddle_lemma\tpaddle_raw\tpaddle_corrected\tpaddle_POS\tpaddle_repairs\tpaddle_text\t"
    "tesseract_canonical_v\ttesseract_box_band_xyxy\ttesseract_conf\ttesseract_accept/reject\ttesseract_score\t"
    "tesseract_lemma\ttesseract_raw\ttesseract_corrected\ttesseract_POS\ttesseract_repairs\t"
    "tesseract_text\tdelta_v_canonical\tlemma_compare\tstatus_compare\treason"
)


def _diagnostic_text(report_columns: list[dict[str, Any]]) -> str:
    """Return a strict rectangular 12-column TSV diagnostics table.

    There are no section-title lines, repeated headers, or blank separator
    lines. This lets strict TSV editors/importers open the file directly.
    Paddle/Tesseract provenance is stored in ``reason`` as ``engine=...``.
    The wider Y-paired table is written separately by ``_comparison_text``.
    """
    rows: list[str] = [_DIAGNOSTIC_HEADER]
    for col in report_columns:
        n = int(col.get("column", 0)) + 1

        for rec in col.get("ocr_records", []):
            raw = {
                "box": rec.get("box"),
                "confidence": rec.get("confidence"),
                "text": rec.get("text", ""),
            }
            rows.append(_candidate_tsv_row(n, raw, raw_status="raw", engine="PADDLE"))
        for cand in _candidate_rows(col.get("candidates", [])):
            rows.append(_candidate_tsv_row(n, cand, engine="PADDLE"))

        tess = col.get("tesseract", {}) or {}
        if tess.get("error"):
            rows.append(_candidate_tsv_row(
                n,
                {"text": ""},
                raw_status="error",
                engine="TESSERACT",
                extra_reason="error=" + _tsv_clean(tess.get("error")),
            ))
        else:
            for rec in tess.get("records", []):
                raw = {
                    "box": rec.get("box"),
                    "confidence": rec.get("confidence"),
                    "text": rec.get("text", ""),
                }
                rows.append(_candidate_tsv_row(n, raw, raw_status="raw", engine="TESSERACT"))
        for cand in _candidate_rows(tess.get("candidates", [])):
            rows.append(_candidate_tsv_row(n, cand, engine="TESSERACT"))

        lens = col.get("lens", {}) or {}
        if lens.get("error"):
            rows.append(_candidate_tsv_row(
                n, {"text": ""}, raw_status="error", engine="GOOGLE_LENS",
                extra_reason="error=" + _tsv_clean(lens.get("error")),
            ))
        else:
            for rec in lens.get("records", []):
                raw = {"box": rec.get("box"), "confidence": rec.get("confidence"), "text": rec.get("text", "")}
                rows.append(_candidate_tsv_row(n, raw, raw_status="raw", engine="GOOGLE_LENS"))
        for cand in _candidate_rows(lens.get("candidates", [])):
            rows.append(_candidate_tsv_row(n, cand, engine="GOOGLE_LENS"))

        for item in col.get("tesseract_rescued", []) or []:
            if isinstance(item, dict):
                rescue = {
                    "box": item.get("box", ""),
                    "confidence": item.get("confidence"),
                    "text": item.get("word", ""),
                    "score": item.get("score", ""),
                    "normalized_headword": item.get("word", ""),
                    "raw_headword": item.get("raw_headword", ""),
                    "corrected_headword": item.get("corrected_headword", ""),
                    "pos_cue": item.get("pos_cue", ""),
                    "ocr_repairs": item.get("ocr_repairs", []),
                }
            else:
                rescue = {"text": str(item)}
            rows.append(_candidate_tsv_row(n, rescue, raw_status="rescued", engine="TESSERACT"))

    return "\n".join(rows) + "\n"


def _comparison_text(report_columns: list[dict[str, Any]]) -> str:
    """Return a strict rectangular 27-column Y-paired OCR comparison TSV."""
    rows: list[str] = [_COMPARISON_HEADER]
    for col in report_columns:
        n = int(col.get("column", 0)) + 1
        for pair in col.get("ocr_y_comparison", []) or []:
            values = [
                n,
                pair.get("paddle_y"), pair.get("paddle_box"), pair.get("paddle_conf"),
                "accept" if pair.get("paddle_accepted") is True else ("reject" if pair.get("paddle_accepted") is False else ""),
                pair.get("paddle_score"), pair.get("paddle_lemma"), pair.get("paddle_raw"),
                pair.get("paddle_corrected"), pair.get("paddle_pos"), pair.get("paddle_repairs"), pair.get("paddle_text"),
                pair.get("tesseract_y"), pair.get("tesseract_box"), pair.get("tesseract_conf"),
                "accept" if pair.get("tesseract_accepted") is True else ("reject" if pair.get("tesseract_accepted") is False else ""),
                pair.get("tesseract_score"), pair.get("tesseract_lemma"), pair.get("tesseract_raw"),
                pair.get("tesseract_corrected"), pair.get("tesseract_pos"), pair.get("tesseract_repairs"), pair.get("tesseract_text"),
                pair.get("delta_y"), pair.get("lemma_compare"), pair.get("status_compare"), pair.get("reason"),
            ]
            rows.append("\t".join(_tsv_clean(v) for v in values))
    return "\n".join(rows) + "\n"


_ENGINES_LONG_HEADER = (
    "pair_id\tcolumn\tcanonical_v\tengine\tconf\ttext\tlemma\tPOS\tscore\trepairs\tparser_trace\taccepted\treason"
)


def _engines_long_text(report_columns: list[dict[str, Any]]) -> str:
    """Engine-normalized long table; adding another OCR never changes its schema."""
    rows = [_ENGINES_LONG_HEADER]
    for col in report_columns:
        column = int(col.get("column", 0)) + 1
        for candidate in col.get("review_candidates", []) or []:
            pair_id = candidate.get("candidate_id", "")
            for engine in ("paddle", "tesseract", "lens"):
                side = candidate.get(engine, {}) or {}
                if side.get("y") is None:
                    continue
                values = [
                    pair_id, column, side.get("y"), engine, side.get("confidence"),
                    side.get("text", ""), side.get("lemma", ""), side.get("POS", ""),
                    side.get("score", ""), side.get("repairs", []), side.get("parser_trace", []),
                    "1" if side.get("accepted") else "0", side.get("reason", ""),
                ]
                rows.append("\t".join(_tsv_clean(value) for value in values))
    return "\n".join(rows) + "\n"


_FUSION_HEADER = (
    "pair_id\tcolumn\tsource_y\tengines\tselected\tfinal_lemma\tfinal_engine\tconfidence\t"
    "score\tneeds_review\tissues\tdecision_reason"
)


def _fusion_text(review_candidates: list[dict[str, Any]]) -> str:
    rows = [_FUSION_HEADER]
    for item in review_candidates:
        engines = [engine for engine in ("paddle", "tesseract", "lens") if (item.get(engine, {}) or {}).get("y") is not None]
        values = [
            item.get("candidate_id", ""), int(item.get("column", 0)) + 1, item.get("source_y", ""),
            ",".join(engines), "1" if item.get("selected") else "0", item.get("word", ""),
            item.get("final_engine", ""), item.get("confidence", ""), item.get("score", ""),
            "1" if item.get("needs_review") else "0", item.get("issue_types", []),
            item.get("decision_reason", ""),
        ]
        rows.append("\t".join(_tsv_clean(value) for value in values))
    return "\n".join(rows) + "\n"



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
    rows = [_ISSUES_HEADER]
    for item in review_candidates:
        issues = list(item.get("issue_types", []) or [])
        if not issues:
            continue
        p = item.get("paddle", {}) or {}; t = item.get("tesseract", {}) or {}; lens = item.get("lens", {}) or {}
        values = [
            item.get("candidate_id"), int(item.get("column", 0)) + 1, item.get("source_y"),
            "1" if item.get("selected") else "0", item.get("word"), item.get("final_engine"),
            item.get("confidence"), item.get("score"), ",".join(issues),
            p.get("lemma"), t.get("lemma"), lens.get("lemma"),
            p.get("text"), t.get("text"), lens.get("text"), item.get("decision_reason"),
        ]
        rows.append("\t".join(_tsv_clean(v) for v in values))
    return "\n".join(rows) + "\n"


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
            refined_v = int(item.get("canonical_v", refined_y))
            coarse_v = int(item.get("coarse_canonical_v", refined_v))
            anchor_v = int(item.get("anchor_canonical_v", coarse_v))
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
        fallback["canonical_v"] = anchor_v
        fallback["refined_source_y"] = refined_y
        fallback["coarse_source_x"] = coarse_x
        fallback["coarse_source_y"] = coarse_y
        fallback["coarse_canonical_v"] = coarse_v
        fallback["anchor_source_x"] = anchor_x
        fallback["anchor_source_y"] = anchor_y
        fallback["anchor_canonical_v"] = anchor_v
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


def _review_candidate_box_height(item: dict[str, Any]) -> int:
    box = item.get("box") or []
    if isinstance(box, (list, tuple)) and len(box) == 4:
        try:
            return max(1, int(box[3]) - int(box[1]))
        except Exception:
            pass
    return 1


def _review_candidates_same_cjk_glyph(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return True when two selected rows are duplicate detections of one Han glyph."""
    if int(left.get("column", -1)) != int(right.get("column", -2)):
        return False
    lw = str(left.get("word", "")).strip()
    rw = str(right.get("word", "")).strip()
    if not (_is_single_cjk_ideograph(lw) and _is_single_cjk_ideograph(rw)):
        return False

    lbox = left.get("box") or []
    rbox = right.get("box") or []
    lh = _review_candidate_box_height(left)
    rh = _review_candidate_box_height(right)
    max_h = max(lh, rh, 1)
    dy = abs(
        int(left.get("canonical_v", left.get("source_y", 0)))
        - int(right.get("canonical_v", right.get("source_y", 0)))
    )

    box_same_row = False
    if isinstance(lbox, (list, tuple)) and len(lbox) == 4 and isinstance(rbox, (list, tuple)) and len(rbox) == 4:
        ly0, ly1 = int(lbox[1]), int(lbox[3])
        ry0, ry1 = int(rbox[1]), int(rbox[3])
        overlap = max(0, min(ly1, ry1) - max(ly0, ry0))
        center_delta = abs(((ly0 + ly1) / 2.0) - ((ry0 + ry1) / 2.0))
        box_same_row = (
            overlap >= min(lh, rh) * 0.20
            or center_delta <= max_h * 0.58
        )

    # Same recognized character gets a slightly wider marker-Y allowance; OCR
    # disagreements still merge when their boxes clearly cover the same glyph.
    if lw == rw and dy <= max(8, round(max_h * 0.95)):
        return True
    return box_same_row and dy <= max(10, round(max_h * 1.10))


def _review_candidate_priority(item: dict[str, Any]) -> tuple[float, float, float, float]:
    manual = 1.0 if item.get("manual_override") else 0.0
    engine_votes = 0.0
    for engine in ("paddle", "tesseract", "lens"):
        side = item.get(engine, {}) or {}
        if side.get("y") is not None:
            engine_votes += 1.0
        if side.get("accepted") is True:
            engine_votes += 0.35
    return (
        manual,
        engine_votes,
        float(item.get("score") or 0.0),
        float(item.get("confidence") or 0.0),
    )


def _normalize_cjk_review_word(word: str) -> str:
    """Return a Unicode-safe normalized review word for CJK duplicate checks."""
    normalized = unicodedata.normalize("NFKC", str(word or "")).strip()
    normalized = re.sub(r"^[【〔［\[]\s*", "", normalized)
    normalized = re.sub(r"\s*[】〕］\]]$", "", normalized)
    normalized = re.sub(r"(?<=[㐀-鿿])\s+(?=[㐀-鿿])", "", normalized)
    return normalized.strip()


def _looks_like_multi_cjk_headword(word: str) -> bool:
    normalized = _normalize_cjk_review_word(word)
    if not normalized or _is_single_cjk_ideograph(normalized):
        return False
    chars = [ch for ch in normalized if _is_single_cjk_ideograph(ch)]
    return len(chars) >= 2 and len(normalized) <= 16


def _review_candidates_same_cjk_compound(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return True when two selected rows are duplicate detections of one CJK compound headword.

    This handles ordinary-size Chinese bracketed compounds such as 【並肩】 that
    can be emitted twice by slightly different OCR pairings.  To avoid merging
    neighbouring real entries, require the normalized lemma to match exactly and
    the physical boxes to overlap strongly or have almost identical centres.
    """
    if int(left.get("column", -1)) != int(right.get("column", -2)):
        return False
    lw = _normalize_cjk_review_word(str(left.get("word", "")))
    rw = _normalize_cjk_review_word(str(right.get("word", "")))
    if not lw or lw != rw:
        return False
    if not (_looks_like_multi_cjk_headword(lw) and _looks_like_multi_cjk_headword(rw)):
        return False

    lbox = left.get("box") or []
    rbox = right.get("box") or []
    lh = _review_candidate_box_height(left)
    rh = _review_candidate_box_height(right)
    max_h = max(lh, rh, 1)
    dy = abs(
        int(left.get("canonical_v", left.get("source_y", 0)))
        - int(right.get("canonical_v", right.get("source_y", 0)))
    )

    if not (isinstance(lbox, (list, tuple)) and len(lbox) == 4 and isinstance(rbox, (list, tuple)) and len(rbox) == 4):
        return dy <= max(6, round(max_h * 0.42))

    ly0, ly1 = int(lbox[1]), int(lbox[3])
    ry0, ry1 = int(rbox[1]), int(rbox[3])
    overlap = max(0, min(ly1, ry1) - max(ly0, ry0))
    center_delta = abs(((ly0 + ly1) / 2.0) - ((ry0 + ry1) / 2.0))
    min_h = max(1, min(lh, rh))
    strong_same_row = (
        overlap >= min_h * 0.45
        or center_delta <= max_h * 0.35
    )
    return strong_same_row and dy <= max(8, round(max_h * 0.55))


def _candidate_has_single_cjk_identity(item: dict[str, Any]) -> bool:
    """Return True when review metadata identifies a large single-Han headword.

    Do not rely only on the final OCR word: the two OCR engines can disagree on
    the glyph while still pointing at the same oversized dictionary headword.
    Parser traces and each engine's lemma/raw/corrected forms are therefore also
    inspected.
    """
    values = [str(item.get("word", ""))]
    for engine in ("paddle", "tesseract", "lens"):
        side = item.get(engine, {}) or {}
        values.extend(str(side.get(key, "")) for key in ("lemma", "raw", "corrected"))
        trace = side.get("parser_trace", []) or []
        if any("chinese_single_character" in str(step) for step in trace):
            return True
    return any(_is_single_cjk_ideograph(_normalize_cjk_review_word(value)) for value in values if value)


def _candidate_line_height(item: dict[str, Any]) -> float:
    try:
        value = float(item.get("line_height_reference") or 0.0)
    except Exception:
        value = 0.0
    if value > 0:
        return value
    # Legacy/manual rows do not carry the normal-line reference.  Their box is
    # still useful as a conservative fallback, but avoid treating a huge glyph
    # height as the normal line height.
    return float(max(1, _review_candidate_box_height(item)))


def _boxes_same_large_cjk_region(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Check whether two candidates plausibly cover the same oversized glyph."""
    lbox = left.get("box") or []
    rbox = right.get("box") or []
    if not (isinstance(lbox, (list, tuple)) and len(lbox) == 4 and isinstance(rbox, (list, tuple)) and len(rbox) == 4):
        return True
    lh = _review_candidate_box_height(left)
    rh = _review_candidate_box_height(right)
    ly0, ly1 = int(lbox[1]), int(lbox[3])
    ry0, ry1 = int(rbox[1]), int(rbox[3])
    overlap = max(0, min(ly1, ry1) - max(ly0, ry0))
    center_delta = abs(((ly0 + ly1) / 2.0) - ((ry0 + ry1) / 2.0))
    return (
        overlap >= max(1, min(lh, rh) * 0.18)
        or center_delta <= max(lh, rh) * 0.62
    )


def _single_cjk_duplicate_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Use a wider Y tolerance for duplicate large single-character entries.

    OCR and visual-projection channels can refine the separator independently,
    leaving two lines farther apart than the ordinary 0.22-line threshold.  A
    single-character pair may therefore use 0.55 of a normal text line, but only
    when geometry still says both candidates belong to the same large glyph.
    """
    if int(left.get("column", -1)) != int(right.get("column", -2)):
        return False
    if not (_candidate_has_single_cjk_identity(left) and _candidate_has_single_cjk_identity(right)):
        return False
    normal_line = max(_candidate_line_height(left), _candidate_line_height(right), 1.0)
    dy = abs(
        int(left.get("canonical_v", left.get("source_y", 0)))
        - int(right.get("canonical_v", right.get("source_y", 0)))
    )
    tolerance = max(4, round(normal_line * _SINGLE_CJK_LINE_DEDUP_RATIO))
    return dy <= tolerance and _boxes_same_large_cjk_region(left, right)


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
    merged = 0
    by_column: dict[int, list[dict[str, Any]]] = {}
    for item in review_candidates:
        if item.get("selected"):
            by_column.setdefault(int(item.get("column", 0)), []).append(item)

    def _threshold(left: dict[str, Any], right: dict[str, Any]) -> int:
        values: list[int] = []
        for item in (left, right):
            try:
                value = int(item.get("line_dedup_tolerance") or 0)
            except Exception:
                value = 0
            if value > 0:
                values.append(value)
        if values:
            return max(2, max(values))
        # Compatibility fallback for manually constructed/legacy cached rows.
        # Box height is in source-image pixels, so 0.22 of the smaller box is a
        # conservative approximation of one fifth of a normal text line.
        approx_line = min(_review_candidate_box_height(left), _review_candidate_box_height(right))
        return max(2, round(approx_line * _FINAL_LINE_DEDUP_RATIO))

    def _merge_selected_rows(
        left: dict[str, Any], right: dict[str, Any], *, single_cjk_special: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        keeper, loser = (left, right) if _review_candidate_priority(left) >= _review_candidate_priority(right) else (right, left)
        # Copy one complete canonical+source point; never mix individual
        # coordinates after rotation. Ordinary duplicates keep the lower/closer
        # marker, but oversized single-CJK duplicates keep the upper entry-start
        # boundary so a lower visual confirmation cannot move the separator into
        # pronunciation/radical metadata inside the same entry.
        left_v = int(left.get("canonical_v", left.get("source_y", 0)))
        right_v = int(right.get("canonical_v", right.get("source_y", 0)))
        if single_cjk_special:
            position_row = left if left_v <= right_v else right
        else:
            position_row = left if left_v >= right_v else right
        for key in (
            "canonical_u", "canonical_v", "source_x", "source_y",
            "refined_source_y", "coarse_canonical_v", "coarse_source_x",
            "coarse_source_y", "anchor_canonical_v", "anchor_source_x",
            "anchor_source_y",
        ):
            if position_row.get(key) is not None:
                keeper[key] = position_row.get(key)
        for engine in ("paddle", "tesseract", "lens"):
            if not (keeper.get(engine, {}) or {}).get("y") and (loser.get(engine, {}) or {}).get("y") is not None:
                keeper[engine] = dict(loser.get(engine, {}) or {})
        issues = list(keeper.get("issue_types", []) or [])
        if "NEAR_Y_DUPLICATE_MERGED" not in issues:
            issues.append("NEAR_Y_DUPLICATE_MERGED")
        if single_cjk_special and "SINGLE_CJK_DUPLICATE_MERGED" not in issues:
            issues.append("SINGLE_CJK_DUPLICATE_MERGED")
        keeper["issue_types"] = issues
        reason = "+single_cjk_duplicate_merge" if single_cjk_special else "+near_y_duplicate_merge"
        keeper["decision_reason"] = str(keeper.get("decision_reason", "")) + reason
        loser["selected"] = False
        loser["needs_review"] = False
        loser_issues = list(loser.get("issue_types", []) or [])
        if "NEAR_Y_DUPLICATE_SUPPRESSED" not in loser_issues:
            loser_issues.append("NEAR_Y_DUPLICATE_SUPPRESSED")
        loser["issue_types"] = loser_issues
        loser["decision_reason"] = "near_y_duplicate_suppressed"
        return keeper, loser

    for rows in by_column.values():
        rows.sort(
            key=lambda item: int(
                item.get("canonical_v", item.get("source_y", 0))
            )
        )
        i = 0
        while i < len(rows) - 1:
            left, right = rows[i], rows[i + 1]
            dy = abs(
        int(left.get("canonical_v", left.get("source_y", 0)))
        - int(right.get("canonical_v", right.get("source_y", 0)))
    )
            single_cjk_special = _single_cjk_duplicate_pair(left, right)
            tolerance = _threshold(left, right)
            if not single_cjk_special and dy > tolerance:
                i += 1
                continue
            _keeper, loser = _merge_selected_rows(
                left, right, single_cjk_special=single_cjk_special,
            )
            merged += 1
            rows.remove(loser)
            rows.sort(
            key=lambda item: int(
                item.get("canonical_v", item.get("source_y", 0))
            )
        )
            i = max(0, i - 1)
    return merged


def _entries_from_review_candidates(review_candidates: list[dict[str, Any]]) -> list[Entry]:
    entries: list[Entry] = []
    selected = [item for item in review_candidates if item.get("selected")]
    selected.sort(key=lambda item: (
        int(item.get("column", 0)),
        int(item.get("canonical_v", item.get("source_y", 0))),
        int(item.get("canonical_u", item.get("source_x", 0))),
    ))
    for item in selected:
        entries.append(Entry(
            word=str(item.get("word", "")),
            x=int(item.get("source_x", 0)),
            y=int(item.get("source_y", 0)),
            confidence=(float(item.get("confidence")) if item.get("confidence") is not None else None),
            ocr_source=str(item.get("final_engine", "")),
            alphabetical_warning=str(item.get("alphabetical_warning", "")),
            candidate_id=str(item.get("candidate_id", "")),
            final_engine=str(item.get("final_engine", "")),
            issue_type=",".join(str(x) for x in item.get("issue_types", []) or []),
            parser_score=(float(item.get("score")) if item.get("score") is not None else None),
            manually_selected=bool(item.get("manual_override", False)),
        ))
    return entries


def _update_project_quality_summary(
    cache_path: Path, summary: dict[str, Any], review_candidates: list[dict[str, Any]],
) -> None:
    path = cache_path.parent / "_quality_summary.tsv"
    with _QUALITY_SUMMARY_LOCK:
        rows: dict[str, list[str]] = {}
        if path.exists():
            try:
                for line in path.read_text(encoding="utf-8-sig").splitlines()[1:]:
                    cols = line.split("\t")
                    if cols and cols[0]:
                        rows[cols[0]] = cols
            except Exception:
                rows = {}
        page = cache_path.stem
        issues = sum(1 for x in review_candidates if x.get("issue_types"))
        needs_review = sum(1 for x in review_candidates if x.get("needs_review"))
        selected = sum(1 for x in review_candidates if x.get("selected"))
        vals = [
            page, f"{float(summary.get('agreement', 0.0)):.4f}", summary.get("candidate_union", 0),
            summary.get("paired", 0), summary.get("exact", 0), summary.get("similar", 0),
            summary.get("conflict", 0), summary.get("paddle_only", 0), summary.get("tesseract_only", 0),
            summary.get("lens_used", 0), summary.get("lens_only", 0), summary.get("triple_agree", 0),
            summary.get("multi_engine_majority", 0),
            selected, issues, needs_review,
        ]
        rows[page] = [_tsv_clean(v) for v in vals]
        output = [_QUALITY_HEADER] + ["\t".join(rows[key]) for key in sorted(rows)]
        _atomic_write_text(path, "\n".join(output) + "\n", encoding="utf-8")


def detect_paddle_headwords(
    image: Image.Image,
    geometry: "Geometry",
    settings: AppSettings,
    cache_path: Path | None = None,
    force_refresh: bool = False,
    engine: Any | None = None,
    filter_rules_path: Path | None = None,
    page_sections: list[PageSection] | None = None,
) -> list[Entry]:
    """v2.1 multi-OCR dictionary headword pipeline.

    Pipeline:
      Paddle/Tesseract/Google Lens -> normalized OCR lines -> dictionary profile ->
      structured grammar parser -> sequence+Y alignment -> arbitration ->
      alphabetical sanity warning ->
      manual selection overrides -> final entries / issues / quality report.

    Raw Paddle boxes remain cacheable independently of parser settings. Tesseract
    failures never abort the primary Paddle pass; arbitration falls back to the
    Paddle candidate sequence when the secondary engine is unavailable.
    """
    signature = _cache_signature(image, geometry, settings)
    canonical_width = geometry.transform.canonical_size(image.size)[0]
    reference_to_canonical_scale = (
        canonical_width / REFERENCE_CANONICAL_WIDTH
    )
    canonical_character_height = stored_geometry_to_canonical(
        settings.character_height, canonical_width, settings,
    )
    user_rules = load_headword_filter_rules(filter_rules_path)
    profile_path = filter_rules_path.parent / PROFILE_FILENAME if filter_rules_path else None
    profile = load_dictionary_profile(
        profile_path,
        preset=effective_project_profile_id(settings, profile_path),
        language=settings.ocr_language,
    )
    cached_columns: list[dict[str, Any]] | None = None
    if cache_path and cache_path.exists() and not force_refresh:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("signature") == signature:
                cached_columns = list(cached.get("columns") or [])
        except (OSError, ValueError, TypeError):
            cached_columns = None

    report_columns: list[dict[str, Any]] = []
    # Main-window engine checkboxes are authoritative. Arbitration is applied
    # only among engines that the user explicitly enabled.
    use_paddle = bool(getattr(settings, "paddle_use_paddleocr", True))
    use_tesseract = bool(settings.paddle_compare_tesseract or settings.paddle_tesseract_rescue)
    tess_language = resolved_tesseract_language(settings)
    tess_availability = tesseract_status(settings.ocr_executable, tess_language) if use_tesseract else {}
    lens_mode = str(settings.paddle_lens_mode or "off").strip().lower()
    if not bool(getattr(settings, "paddle_enable_lens", False)):
        lens_mode = "off"
    if lens_mode not in {"off", "diagnostic", "conflict", "full"}:
        lens_mode = "off"
    if not (use_paddle or use_tesseract or lens_mode != "off"):
        raise RuntimeError("至少选择一个 OCR 引擎后才能运行 OCR 画线。")

    # Build the full-page RGB array once per OCR invocation.  Column-band
    # extraction used to reconvert the whole page for every band, which raised
    # peak memory substantially on high-resolution scans.  This object is local
    # to the current page/call, so zoom changes, page changes, or later parameter
    # edits can never reuse pixels from another page.
    oriented = normalize_page_rgb(image)
    shared_source_rgb = np.asarray(oriented)

    for col, canonical_u in enumerate(geometry.column_starts):
        band, source_top, left_margin = unwrap_column_band(
            image, geometry, col, settings, source_rgb=shared_source_rgb,
        )
        separator_width = max(24, int(geometry.column_widths[col] + left_margin))
        separator_band, _, _ = unwrap_column_band(
            image, geometry, col, settings, source_width=separator_width,
            source_rgb=shared_source_rgb,
        )
        transform_kind = geometry.transform.kind
        analysis_band = geometry.transform.canonical_image_for_analysis(band)
        analysis_separator_band = geometry.transform.canonical_image_for_analysis(separator_band)

        if cached_columns is not None and col < len(cached_columns):
            records = [OCRRecord(
                text=str(item["text"]), confidence=float(item["confidence"]),
                box=tuple(int(value) for value in item["box"]),  # type: ignore[arg-type]
            ) for item in cached_columns[col].get("ocr_records", [])]
        elif use_paddle:
            source_records = run_paddle_band(band, settings, engine=engine)
            records = _records_to_canonical_band(source_records, band.size, transform_kind)
        else:
            records = []

        paddle_lines = _records_as_merged_lines(records, settings)
        paddle_full_text = "\n".join(line.text for line in paddle_lines)
        paddle_entries, diagnostics = filter_headword_records(
            records, analysis_band, source_top, canonical_u, settings,
            separator_band=analysis_separator_band, user_rules=user_rules, engine_name="paddle", profile=profile,
            reference_to_canonical_scale=reference_to_canonical_scale,
        )
        _attach_source_candidate_coordinates(diagnostics, geometry, col)
        for entry in paddle_entries:
            entry.x, entry.y = geometry.canonical_to_source(entry.x, entry.y)

        tess_payload: dict[str, Any] = {
            "enabled": use_tesseract,
            "rescue_enabled": bool(settings.paddle_tesseract_rescue),
            "arbitration_enabled": bool(settings.paddle_dual_ocr_arbitration),
            "language": tess_language,
            "psm": settings.paddle_tesseract_psm,
            "auto_psm": bool(settings.paddle_tesseract_auto_psm),
            "availability": tess_availability,
            "variants": [],
            "full_text": "",
            "records": [],
            "candidates": [],
            "accepted_count": 0,
            "error": "",
        }
        tess_entries: list[Entry] = []
        tess_diagnostics: list[dict[str, Any]] = []
        if use_tesseract:
            if str(getattr(settings, "layout_writing_mode", "horizontal-tb")).startswith("vertical"):
                psm_values = [5]
            else:
                psm_values = [4, 6] if settings.paddle_tesseract_auto_psm else [max(3, int(settings.paddle_tesseract_psm))]
            variants: list[tuple[tuple[float, ...], int, list[OCRRecord], str, list[Entry], list[dict[str, Any]]]] = []
            errors: list[str] = []
            for psm in dict.fromkeys(psm_values):
                try:
                    source_candidate_records, candidate_text = run_tesseract_band_records(
                        band, settings, psm_override=psm
                    )
                    candidate_records = _records_to_canonical_band(
                        source_candidate_records, band.size, transform_kind
                    )
                    candidate_entries, candidate_diagnostics = filter_headword_records(
                        candidate_records, analysis_band, source_top, canonical_u, settings,
                        separator_band=analysis_separator_band, user_rules=user_rules,
                        engine_name="tesseract", profile=profile,
                        reference_to_canonical_scale=reference_to_canonical_scale,
                    )
                    _attach_source_candidate_coordinates(
                        candidate_diagnostics, geometry, col,
                    )
                    for entry in candidate_entries:
                        entry.x, entry.y = geometry.canonical_to_source(entry.x, entry.y)
                    structural = sum(
                        1 for row in _candidate_rows(candidate_diagnostics)
                        if (row.get("features", {}) or {}).get("structural_cue")
                    )
                    mean_conf = (
                        sum(record.confidence for record in candidate_records) / len(candidate_records)
                        if candidate_records else 0.0
                    )
                    rank = (float(len(candidate_entries)), float(structural), mean_conf, float(len(candidate_records)))
                    variants.append((rank, psm, candidate_records, candidate_text, candidate_entries, candidate_diagnostics))
                    tess_payload["variants"].append({
                        "psm": psm, "records": len(candidate_records),
                        "accepted": len(candidate_entries), "structural": structural,
                        "mean_confidence": round(mean_conf, 4),
                    })
                except Exception as exc:
                    errors.append(f"PSM {psm}: {exc}")
                    tess_payload["variants"].append({"psm": psm, "error": str(exc)})
            if variants:
                _rank, chosen_psm, tess_records, tess_full_text, tess_entries, tess_diagnostics = max(variants, key=lambda item: item[0])
                tess_payload.update({
                    "psm": chosen_psm,
                    "full_text": tess_full_text,
                    "records": [asdict(record) for record in tess_records],
                    "candidates": tess_diagnostics,
                    "accepted_count": len(tess_entries),
                })
            else:
                tess_payload["error"] = " | ".join(errors) or str(tess_availability.get("error") or "Tesseract 不可用")

        compare_tolerance = max(
            4,
            round(
                canonical_character_height
                * max(0.35, settings.paddle_alignment_y_tolerance_ratio)
            ),
        )
        pre_pairs = (
            _pair_ocr_candidates(diagnostics, tess_diagnostics, compare_tolerance, settings.paddle_alignment_min_similarity)
            if tess_diagnostics else [
                _make_ocr_pair(item, None, "paddle_only_no_secondary")
                for item in _eligible_alignment_rows(diagnostics)
            ]
        )
        lens_attempted = lens_mode in {"diagnostic", "full"} or (
            lens_mode == "conflict" and (_pairs_need_lens(pre_pairs) or not pre_pairs)
        )
        # Lens language is deliberately derived from the active headword OCR
        # language. Keep the persisted legacy field only for compatibility.
        lens_language = str(
            getattr(settings, "ocr_language", "")
            or getattr(settings, "paddle_lens_language", "")
            or ""
        )
        lens_payload: dict[str, Any] = {
            "enabled": lens_mode != "off", "mode": lens_mode, "attempted": lens_attempted,
            "language": lens_language, "version": "", "full_text": "",
            "records": [], "candidates": [], "accepted_count": 0, "error": "",
            "confidence_source": "neutral_default; typography_from_original_bbox",
        }
        if lens_attempted:
            try:
                raw_lens_records, lens_full_text, lens_version = run_google_lens(
                    band, language=lens_language,
                    timeout=settings.paddle_lens_timeout,
                    default_confidence=settings.paddle_lens_default_confidence,
                )
                source_lens_records = [
                    OCRRecord(text, confidence, box) for text, confidence, box in raw_lens_records
                ]
                lens_records = _records_to_canonical_band(
                    source_lens_records, band.size, transform_kind
                )
                lens_entries, lens_diagnostics = filter_headword_records(
                    lens_records, analysis_band, source_top, canonical_u, settings,
                    separator_band=analysis_separator_band, user_rules=user_rules,
                    engine_name="lens", profile=profile,
                )
                _attach_source_candidate_coordinates(
                    lens_diagnostics, geometry, col,
                )
                lens_payload.update({
                    "version": lens_version, "full_text": lens_full_text,
                    "records": [asdict(record) for record in lens_records],
                    "candidates": lens_diagnostics, "accepted_count": len(lens_entries),
                })
            except Exception as exc:
                lens_payload["error"] = str(exc)

        report_columns.append({
            "column": col,
            "canonical_column_u": int(canonical_u),
            "canonical_top_v": int(source_top),
            "column_coordinate_space": "canonical_full_resolution_pixels",
            "band_size": list(band.size),
            "ocr_records": [asdict(record) for record in records],
            "paddle_full_text": paddle_full_text,
            "paddle_merged_lines": [
                {
                    "text": line.text,
                    "confidence": round(line.confidence, 6),
                    "box": list(line.box),
                    "members": [asdict(member) for member in line.records],
                    "logical_repairs": list(line.logical_repairs),
                }
                for line in paddle_lines
            ],
            "candidates": diagnostics,
            "paddle_accepted_count": len(paddle_entries),
            "tesseract": tess_payload,
            "lens": lens_payload,
            # v2 fills these after alphabetical annotation so arbitration sees
            # the warning metadata from both engines.
            "ocr_y_comparison": [],
            "review_candidates": [],
        })

    # Alphabetical order remains a weak warning only. It is computed before OCR
    # arbitration so a suspicious engine result can contribute to review issues.
    alphabetical_warnings = _annotate_alphabetical_warnings(
        report_columns, page_sections,
        top_v=geometry.top, bottom_v=geometry.bottom,
    )

    review_candidates: list[dict[str, Any]] = []
    for col in report_columns:
        col_index = int(col.get("column", 0))
        canonical_u = int(col.get("canonical_column_u", 0))
        band_width = max(
            1,
            int((col.get("band_size") or [settings.paddle_band_width])[0]),
        )
        source_line_height = max(1.0, float(canonical_character_height))
        compare_tolerance = max(
            4,
            round(source_line_height * max(0.35, settings.paddle_alignment_y_tolerance_ratio)),
        )
        final_line_dedup_tolerance = max(2, round(source_line_height * _FINAL_LINE_DEDUP_RATIO))
        tess = col.get("tesseract", {}) or {}
        tess_rows = list(tess.get("candidates", []) or []) if use_tesseract and not tess.get("error") else []
        if tess_rows:
            pairs = _pair_ocr_candidates(
                col.get("candidates", []), tess_rows, compare_tolerance,
                settings.paddle_alignment_min_similarity,
            )
        else:
            pairs = [
                _make_ocr_pair(item, None, "paddle_only_no_secondary")
                for item in _eligible_alignment_rows(col.get("candidates", []))
            ]
        lens = col.get("lens", {}) or {}
        lens_rows = list(lens.get("candidates", []) or []) if lens.get("attempted") and not lens.get("error") else []
        if lens_rows:
            pairs = _pair_with_lens_candidates(
                pairs, lens_rows, compare_tolerance,
                settings.paddle_alignment_min_similarity,
            )
        col["ocr_y_comparison"] = pairs

        column_review: list[dict[str, Any]] = []
        if settings.paddle_dual_ocr_arbitration or not tess_rows:
            for pair in pairs:
                column_review.append(_arbitrate_pair(pair, col_index, canonical_u, settings, geometry=geometry))
        else:
            # Compatibility mode: Paddle remains authoritative; optional legacy
            # Tesseract rescue can still promote structurally strong missing rows.
            paddle_selected_v = {
                int(_candidate_axis_v(c) or 0)
                for c in _candidate_rows(col.get("candidates", [])) if c.get("accepted")
            }
            for pair in pairs:
                item = _arbitrate_pair(pair, col_index, canonical_u, settings, geometry=geometry)
                py = pair.get("paddle_y")
                if py is not None:
                    item["selected"] = int(py) in paddle_selected_v
                    item["final_engine"] = "paddle"
                    item["word"] = str(pair.get("paddle_lemma", ""))
                    _apply_pair_engine_position(
                        item, pair, "paddle", col_index, canonical_u, geometry,
                    )
                    item["confidence"] = pair.get("paddle_conf")
                    item["score"] = pair.get("paddle_score")
                    item["decision_reason"] = "compat_paddle_authoritative"
                elif settings.paddle_tesseract_rescue and pair.get("tesseract_accepted"):
                    features = pair.get("tesseract_features", {}) or {}
                    if features.get("structural_cue"):
                        item["selected"] = True
                        item["decision_reason"] = "compat_tesseract_rescue"
                else:
                    item["selected"] = False
                # Recompute issue list after compatibility selection.
                chosen = str(item.get("final_engine", ""))
                item["issue_types"] = _issues_for_pair(pair, chosen, bool(item.get("needs_review")))
                column_review.append(item)
        for item in column_review:
            item["line_dedup_tolerance"] = final_line_dedup_tolerance
            item["line_height_reference"] = round(source_line_height, 3)
        col["review_candidates"] = column_review
        review_candidates.extend(column_review)

    # Preserve the pre-refinement marker Y as an unchecked fallback candidate.
    # This is added only after OCR arbitration so it cannot influence engine
    # pairing or candidate scoring.
    original_y_fallbacks = _expand_original_y_fallback_candidates(review_candidates)

    # Manual checkbox/review choices have the highest final-selection priority,
    # while parser/OCR data stays untouched for reproducibility.
    overrides = _load_manual_selection_overrides(cache_path)
    _apply_manual_selection_overrides(review_candidates, overrides)
    _enforce_position_variant_exclusivity(review_candidates)
    cjk_duplicates_merged = _deduplicate_selected_cjk_review_candidates(review_candidates)
    all_entries = _entries_from_review_candidates(review_candidates)
    _apply_alphabetical_warnings_to_entries(report_columns, all_entries)

    agreement = _agreement_summary(review_candidates)
    if not use_tesseract and lens_mode == "off":
        agreement["agreement"] = 1.0
    agreement["selected"] = sum(1 for item in review_candidates if item.get("selected"))
    agreement["cjk_duplicates_merged"] = cjk_duplicates_merged
    agreement["original_y_fallbacks"] = original_y_fallbacks
    agreement["issues"] = sum(
        1 for item in review_candidates
        if str(item.get("position_variant", "refined")) != "original" and item.get("issue_types")
    )
    agreement["needs_review"] = sum(
        1 for item in review_candidates
        if str(item.get("position_variant", "refined")) != "original" and item.get("needs_review")
    )

    # Keep per-column selected count for readers/tools that used the v1 format.
    for col in report_columns:
        col["accepted_count"] = sum(1 for item in col.get("review_candidates", []) if item.get("selected"))

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "picture-capture-headwords-v3",
            "signature": signature,
            "coordinate_spaces": {
                "final_entries": "source_image_pixels",
                "candidate_source": "source_image_pixels",
                "candidate_canonical": "canonical_full_resolution_pixels",
                "ocr_record_box": "ocr_band_local_pixels",
                "layout_transform": geometry.transform.kind,
            },
            "filter_rules_path": str(filter_rules_path) if filter_rules_path else "",
            "filter_rule_count": len(user_rules),
            "dictionary_profile": {
                "key": profile.key,
                "name": profile.name,
                "family": profile.family,
                "parser_modes": list(profile.parser_modes),
                "path": str(profile_path) if profile_path and profile_path.exists() else "bundled",
                "pos_labels": len(profile.pos_labels),
                "metadata_labels": len(profile.metadata_labels),
            },
            "dual_ocr": {
                "paddleocr": use_paddle,
                "tesseract_compare": use_tesseract,
                "tesseract_rescue": bool(settings.paddle_tesseract_rescue),
                "arbitration": bool(settings.paddle_dual_ocr_arbitration),
                "tesseract_language": tess_language,
                "tesseract_psm": settings.paddle_tesseract_psm,
                "tesseract_auto_psm": bool(settings.paddle_tesseract_auto_psm),
                "tesseract_status": tess_availability,
                "google_lens_mode": lens_mode,
                "google_lens_language": lens_language,
            },
            "alphabetical_warnings": alphabetical_warnings,
            "page_quality": agreement,
            "review_candidates": review_candidates,
            "manual_override_count": len(overrides),
            "final_entries": [asdict(entry) for entry in all_entries],
            "columns": report_columns,
        }
        _atomic_write_json(cache_path, payload)
        _atomic_write_text(
            cache_path.with_name(f"{cache_path.stem}_ocr_diagnostics.txt"),
            _diagnostic_text(report_columns), encoding="utf-8",
        )
        _atomic_write_text(
            cache_path.with_name(f"{cache_path.stem}_ocr_comparison.txt"),
            _comparison_text(report_columns), encoding="utf-8",
        )
        _atomic_write_text(
            cache_path.with_name(f"{cache_path.stem}_issues.tsv"),
            _issues_text(review_candidates), encoding="utf-8",
        )
        _atomic_write_text(
            cache_path.with_name(f"{cache_path.stem}_ocr_engines.tsv"),
            _engines_long_text(report_columns), encoding="utf-8",
        )
        _atomic_write_text(
            cache_path.with_name(f"{cache_path.stem}_fusion.tsv"),
            _fusion_text(review_candidates), encoding="utf-8",
        )
        _update_project_quality_summary(cache_path, agreement, review_candidates)

    return all_entries
