from __future__ import annotations

"""Dictionary headword language/script validation; callback-injected core bridge."""

from collections.abc import Callable
from typing import Any
import unicodedata

from ..models import AppSettings
from .headword_models import HeadwordParse


def _ocr_language_parts(settings: AppSettings) -> set[str]:
    """Return the user-selected semantic OCR language components.

    ocr_language is authoritative. paddle_language is only a fallback for older
    callers with no semantic language, because a stale backend model name must
    not silently disable the script guard.
    """
    raw = str(getattr(settings, "ocr_language", "") or "").strip()
    if not raw:
        raw = str(getattr(settings, "paddle_language", "") or "").strip()
    return {
        part.strip()
        for part in raw.lower().replace(",", "+").split("+")
        if part.strip()
    }


def _leading_script_family(text: str, *, unicode_data: Any = unicodedata) -> str:
    """Classify the first meaningful headword character into a script family."""
    normalized = unicode_data.normalize("NFKC", str(text or "")).lstrip()
    if not normalized:
        return ""
    for char in normalized:
        if char.isspace() or char in "-'’·•∙‧":
            continue
        code = ord(char)
        if (
            0x3400 <= code <= 0x4DBF
            or 0x4E00 <= code <= 0x9FFF
            or 0xF900 <= code <= 0xFAFF
            or 0x20000 <= code <= 0x2FA1F
        ):
            return "han"
        if (
            0x3040 <= code <= 0x309F
            or 0x30A0 <= code <= 0x30FF
            or 0x31F0 <= code <= 0x31FF
        ):
            return "kana"
        if (
            0x1100 <= code <= 0x11FF
            or 0x3130 <= code <= 0x318F
            or 0xAC00 <= code <= 0xD7AF
        ):
            return "hangul"
        return "other"
    return ""


def _headword_script_compatibility(
    settings: AppSettings, parsed: HeadwordParse | None,
    *,
    script_family_fn: Callable[[str], str] = _leading_script_family,
    language_parts_fn: Callable[[AppSettings], set[str]] = _ocr_language_parts,
) -> tuple[bool, str]:
    """Reject CJK-script headwords when the selected OCR language cannot use them.

    This is deliberately language/script compatibility rather than the naive
    rule "non-Chinese => reject Han": Japanese headwords legitimately begin
    with Kanji, and Korean dictionaries may contain Hanja. The guard therefore
    allows Han for Chinese/Japanese/Korean OCR, Kana only for Japanese OCR, and
    Hangul only for Korean OCR. Other scripts are left unchanged here.
    """
    active = int(
        getattr(settings, "profile_headword_script_guard_version", 0) or 0
    ) >= 1 and bool(
        getattr(settings, "profile_headword_script_guard_enabled", True)
    )
    if not active or parsed is None or not parsed.normalized:
        return True, ""

    family = script_family_fn(parsed.normalized)
    if family not in {"han", "kana", "hangul"}:
        return True, family

    parts = language_parts_fn(settings)
    chinese = bool(
        parts.intersection({"chi_sim", "chi_tra", "ch", "chinese_cht", "zh", "zho"})
    )
    japanese = bool(
        parts.intersection({"jpn", "jpn_vert", "japan", "ja", "japanese"})
    )
    korean = bool(
        parts.intersection({"kor", "korean", "ko"})
    )

    if family == "han":
        return bool(chinese or japanese or korean), family
    if family == "kana":
        return bool(japanese), family
    if family == "hangul":
        return bool(korean), family
    return True, family

