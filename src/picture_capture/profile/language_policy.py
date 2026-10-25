"""Project index-language vocabulary and OCR-language normalization policy.

Pure policy: importing this module never initializes Tk, OCR engines, or projects.
The historical app entrypoint supplies its live mapping at call time.
"""
from __future__ import annotations

from collections.abc import Mapping

# ISO 639-1; common languages first, then alphabetical.
PROJECT_LANGUAGE_CODES = (
    "en", "zh", "es", "fr", "de", "it", "pt", "ja", "ko", "ru",
    "ar", "nl", "pl", "tr", "vi",
    "af", "am", "az", "be", "bg", "bn", "bs", "ca", "cs", "cy",
    "da", "el", "eo", "et", "eu", "fa", "fi", "ga", "gl", "gu",
    "he", "hi", "hr", "hu", "hy", "id", "is", "ka", "kk", "km",
    "kn", "la", "lt", "lv", "mk", "ml", "mn", "mr", "ms", "mt",
    "ne", "no", "pa", "ro", "sk", "sl", "sq", "sr", "sv", "sw",
    "ta", "te", "th", "tl", "uk", "ur", "uz",
)

OCR_TO_PROJECT_LANGUAGE = {
    "eng": "en", "spa": "es", "fra": "fr", "fre": "fr", "deu": "de", "ger": "de",
    "ita": "it", "por": "pt", "chi_sim": "zh", "chi_tra": "zh", "ch": "zh",
    "jpn": "ja", "japan": "ja", "kor": "ko", "korean": "ko", "rus": "ru",
}


def project_language_from_ocr(
    ocr_language: str, *, mapping: Mapping[str, str] | None = None,
) -> str:
    """Map the first configured OCR language to an ISO 639-1 code."""
    first = next((part.strip().lower() for part in str(ocr_language or "").split("+") if part.strip()), "")
    aliases = OCR_TO_PROJECT_LANGUAGE if mapping is None else mapping
    return aliases.get(first, first if len(first) == 2 and first.isalpha() else "")
