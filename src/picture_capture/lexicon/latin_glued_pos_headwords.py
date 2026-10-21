"""Independent lemma+POS evidence from OCR-glued Latin dictionary headings.

OCR commonly joins printed headword and grammar tag (abaluartarv.t.,
abanillom., aals. m., Abigaíln. pr.). The existing continuation heuristic
mistakes these real entry starts for body text. Detect the exact leading
lemma/tag shape; *only* the caller can rescue it, after image-boundary, lane,
confidence and user-rule checks.

No dictionary-specific word lists or hidden training-page coordinates.
"""
from __future__ import annotations

import re

_LEMMA_AND_POS = re.compile(
    r"^\s*(?P<lemma>[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ\-’¹²³⁴⁵()]{2,38}?)"
    r"(?P<space>\s?)"
    r"(?P<pos>v\.?\s?[tir]\.\s*|s\.?\s*[mf]\.\s*|m\.|f\.|adj\.|adv\.|n\.\s*pr\.|pref\.)",
    re.IGNORECASE,
)


def glued_lemma_and_pos(text: str) -> tuple[str, str] | None:
    """Require a real, immediately adjacent grammar tag after a Latin lemma."""
    match = _LEMMA_AND_POS.search(str(text or ""))
    if match is None or match.group("space"):
        return None
    lemma = match.group("lemma").strip()
    if len(lemma.strip("-()'’¹²³⁴⁵")) < 3:
        return None
    return lemma, match.group("pos").strip()
