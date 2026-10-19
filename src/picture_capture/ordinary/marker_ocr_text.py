"""Conservative bracket-boundary cleanup for established-marker OCR text.

This is not a global OCR replacement regex. Only callers whose dictionary
Profile explicitly admits CJK bracketed headwords may use it; line detection
and generic Latin/Japanese text remain unchanged.
"""
from __future__ import annotations

import re
import unicodedata


_HAN = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_HAN_SPAN = re.compile(rf"[{_HAN}]+")
_HAN_WITH_INTERNAL_SPACE = re.compile(rf"(?<=[{_HAN}])\s+(?=[{_HAN}])")


def bracketed_ocr_lemma(text: str, *, enabled: bool) -> str | None:
    """Find an OCR lemma even when only one of 【/】 was recognized.

    A matched pair is strong evidence and permits an entire short Han phrase.
    Without the closing bracket, accept only the immediate contiguous Han run
    after 【, to avoid swallowing the definition. Without the opening bracket,
    take the final bounded Han token before 】. We deliberately do NOT try to
    manufacture a lemma if neither delimiter is visible.
    """
    if not enabled:
        return None
    line = next((part.strip() for part in str(text or "").splitlines() if part.strip()), "")
    if not line:
        return None
    left = line.find("【")
    right = line.find("】", left + 1) if left >= 0 else -1
    if left >= 0:
        remainder = line[left + 1:]
        if right >= 0:
            inner = remainder[:right - left - 1].strip()
            inner = _HAN_WITH_INTERNAL_SPACE.sub("", inner)
            value = unicodedata.normalize("NFKC", inner)
            if 1 <= len(value) <= 32 and _HAN_SPAN.search(value):
                return value
            return None
        match = re.match(rf"\s*([{_HAN}]{{1,24}})", remainder)
        return unicodedata.normalize("NFKC", match.group(1)) if match else None

    right = line.find("】")
    if right < 0:
        return None
    # With no 【, a lemma boundary cannot be inferred from arbitrary prose.
    # Only a short final Han token before 】 is accepted.
    prefix = line[:right].rstrip()
    matches = list(_HAN_SPAN.finditer(prefix))
    if not matches:
        return None
    last = matches[-1]
    if last.end() != len(prefix) or len(last.group()) > 16:
        return None
    return unicodedata.normalize("NFKC", last.group())
