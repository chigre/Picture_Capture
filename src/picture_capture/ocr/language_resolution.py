from __future__ import annotations

"""Legacy OCR language selectors and Paddle model mappings.

Keep these existing model fallbacks distinct from semantic script guards.
"""

from ..models import AppSettings


def is_chinese_ocr(settings: AppSettings) -> bool:
    """Return True when the active OCR language is Simplified/Traditional Chinese."""
    lang = (settings.ocr_language or "").lower()
    paddle_lang = (settings.paddle_language or "").lower()
    parts = {part.strip() for part in lang.split("+") if part.strip()}
    return bool(
        parts.intersection({"chi_sim", "chi_tra", "ch", "chinese_cht"})
        or paddle_lang in {"ch", "chi_sim", "chi_tra", "chinese_cht"}
    )


def is_japanese_ocr(settings: AppSettings) -> bool:
    """Return True when the active OCR language is Japanese."""
    lang = (settings.ocr_language or "").lower()
    paddle_lang = (settings.paddle_language or "").lower()
    parts = {part.strip() for part in lang.split("+") if part.strip()}
    return bool(parts.intersection({"jpn", "jpn_vert", "japan"}) or paddle_lang == "japan")


def paddle_language(settings: AppSettings) -> str:
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
