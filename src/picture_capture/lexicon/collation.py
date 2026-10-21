from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class CollationProfile:
    key: str
    label: str
    order: str | None = None
    fold_accents: bool = True


LATIN_ORDER = "a b c d e f g h i j k l m n o p q r s t u v w x y z"
SPANISH_MODERN_ORDER = "a b c d e f g h i j k l m n ñ o p q r s t u v w x y z"
SPANISH_TRADITIONAL_ORDER = "a b c ch d e f g h i j k l ll m n ñ o p q r s t u v w x y z"

PROFILES: dict[str, CollationProfile] = {
    "eng": CollationProfile("eng", "英语（A–Z）", LATIN_ORDER),
    "spa_modern": CollationProfile("spa_modern", "西班牙语（现代）", SPANISH_MODERN_ORDER),
    "spa_traditional": CollationProfile("spa_traditional", "西班牙语（传统：ch / ll 为整体字母）", SPANISH_TRADITIONAL_ORDER),
    "fra": CollationProfile("fra", "法语", LATIN_ORDER),
    "ita": CollationProfile("ita", "意大利语", LATIN_ORDER),
    "por": CollationProfile("por", "葡萄牙语", LATIN_ORDER),
    "deu": CollationProfile("deu", "德语", LATIN_ORDER),
    "latin": CollationProfile("latin", "通用拉丁字母（A–Z）", LATIN_ORDER),
    "unicode": CollationProfile("unicode", "通用 Unicode", None, fold_accents=False),
    "custom": CollationProfile("custom", "自定义排序规则", None),
}

LANGUAGE_PROFILE_KEYS = {
    "eng": ("eng",),
    "spa": ("spa_modern", "spa_traditional"),
    "fra": ("fra",),
    "ita": ("ita",),
    "por": ("por",),
    "deu": ("deu",),
    "chi_sim": ("unicode",),
    "chi_tra": ("unicode",),
}


def primary_ocr_language(language: str) -> str:
    text = (language or "").strip().lower()
    if not text:
        return "eng"
    # Tesseract language strings can be eng+spa, spa_vert, etc. Use the first
    # component that looks like a language code.
    for token in re.split(r"[+,;\s]+", text):
        if token:
            return token
    return "eng"


def auto_profile_key(language: str) -> str:
    lang = primary_ocr_language(language)
    if lang == "spa":
        return "spa_modern"
    if lang in PROFILES:
        return lang
    if lang.startswith("chi"):
        return "unicode"
    return "latin"


def available_profiles(language: str) -> list[CollationProfile]:
    lang = primary_ocr_language(language)
    keys = list(LANGUAGE_PROFILE_KEYS.get(lang, (auto_profile_key(lang),)))
    # Always expose a stable generic fallback and customization, but avoid
    # duplicate Unicode entries for CJK profiles.
    for key in ("unicode", "custom"):
        if key not in keys:
            keys.append(key)
    return [PROFILES[key] for key in keys]


def profile_label(key: str, language: str) -> str:
    if key == "auto":
        actual = auto_profile_key(language)
        return f"自动（随 OCR 语言：{PROFILES[actual].label}）"
    return PROFILES.get(key, PROFILES["unicode"]).label


def available_profile_labels(language: str) -> dict[str, str]:
    result = {profile_label("auto", language): "auto"}
    for profile in available_profiles(language):
        result[profile.label] = profile.key
    return result


def parse_custom_order(text: str) -> list[str]:
    # Space/comma/newline separated. Tokens may contain multiple letters such
    # as ch or ll; greedy matching then treats them as one collation element.
    tokens = [token.casefold() for token in re.split(r"[\s,;]+", text.strip()) if token.strip()]
    if not tokens:
        raise ValueError("自定义排序规则不能为空。请用空格分隔排序单元，例如：a b c ch d … n ñ o …")
    if len(tokens) != len(set(tokens)):
        raise ValueError("自定义排序规则包含重复排序单元。")
    return tokens


def _clean_text(word: str) -> str:
    text = unicodedata.normalize("NFC", (word or "").casefold().strip())
    translate = str.maketrans({
        "’": "'", "‘": "'", "`": "'", "´": "'",
        "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
        "·": "", "•": "", "∙": "", "‧": "",
    })
    return text.translate(translate)


def _fold_char(ch: str, keep_chars: set[str], fold_accents: bool) -> str:
    if ch in keep_chars or not fold_accents:
        return ch
    if ch == "ß":
        return "ss"
    decomposed = unicodedata.normalize("NFD", ch)
    base = "".join(c for c in decomposed if not unicodedata.combining(c))
    return base or ch


def _normalized_for_tokens(word: str, tokens: list[str], fold_accents: bool) -> str:
    text = _clean_text(word)
    keep_chars = {token for token in tokens if len(token) == 1}
    pieces: list[str] = []
    for ch in text:
        if ch.isalpha() or ch.isdigit():
            pieces.append(_fold_char(ch, keep_chars, fold_accents))
    return "".join(pieces)


def collation_key(
    word: str,
    mode: str,
    language: str,
    custom_order: str = LATIN_ORDER,
    custom_fold_accents: bool = True,
) -> tuple:
    actual = auto_profile_key(language) if mode == "auto" else mode
    if actual == "unicode":
        text = "".join(ch for ch in _clean_text(word) if ch.isalpha() or ch.isdigit())
        return tuple((0, ord(ch)) for ch in text), text

    if actual == "custom":
        tokens = parse_custom_order(custom_order)
        fold_accents = bool(custom_fold_accents)
    else:
        profile = PROFILES.get(actual, PROFILES["latin"])
        tokens = parse_custom_order(profile.order or LATIN_ORDER)
        fold_accents = profile.fold_accents

    # Longest token first lets custom multi-character units (ch, ll, dz, etc.)
    # behave as a single alphabet element.
    token_rank = {token: index + 1 for index, token in enumerate(tokens)}
    candidates = sorted(tokens, key=lambda token: (-len(token), token))
    normalized = _normalized_for_tokens(word, tokens, fold_accents)
    result: list[tuple[int, int]] = []
    i = 0
    while i < len(normalized):
        matched = None
        for token in candidates:
            if normalized.startswith(token, i):
                matched = token
                break
        if matched is not None:
            result.append((token_rank[matched], 0))
            i += len(matched)
            continue
        ch = normalized[i]
        if ch.isdigit():
            result.append((10_000, ord(ch)))
        else:
            result.append((20_000, ord(ch)))
        i += 1
    return tuple(result), unicodedata.normalize("NFC", _clean_text(word))


def display_key(
    word: str,
    mode: str,
    language: str,
    custom_order: str = LATIN_ORDER,
    custom_fold_accents: bool = True,
) -> str:
    actual = auto_profile_key(language) if mode == "auto" else mode
    if actual == "unicode":
        return "".join(ch for ch in _clean_text(word) if ch.isalpha() or ch.isdigit())
    if actual == "custom":
        tokens = parse_custom_order(custom_order)
        fold_accents = bool(custom_fold_accents)
    else:
        profile = PROFILES.get(actual, PROFILES["latin"])
        tokens = parse_custom_order(profile.order or LATIN_ORDER)
        fold_accents = profile.fold_accents
    normalized = _normalized_for_tokens(word, tokens, fold_accents)
    multi = sorted((token for token in tokens if len(token) > 1), key=lambda token: -len(token))
    out: list[str] = []
    i = 0
    while i < len(normalized):
        matched = next((token for token in multi if normalized.startswith(token, i)), None)
        if matched:
            out.append(f"<{matched}>")
            i += len(matched)
        else:
            out.append(normalized[i])
            i += 1
    return "".join(out)
