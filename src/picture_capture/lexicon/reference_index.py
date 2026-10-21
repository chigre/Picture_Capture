from __future__ import annotations

import unicodedata
from functools import lru_cache


_CJK_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2FA1F),
)


def contains_cjk(text: object) -> bool:
    value = unicodedata.normalize("NFKC", str(text or ""))
    for ch in value:
        code = ord(ch)
        if any(lo <= code <= hi for lo, hi in _CJK_RANGES):
            return True
    return False


def _fold_latin(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold().strip())
    return "".join(ch for ch in value if not unicodedata.combining(ch) and ch.isalnum())


@lru_cache(maxsize=200_000)
def reference_sort_key(text: str) -> tuple[str, str]:
    """Return a stable page-less index key.

    Chinese indexes are commonly ordered by Hanyu Pinyin.  pypinyin is used
    when available; the function deliberately keeps a Unicode fallback so an
    old installation can still open projects before its dependencies are
    refreshed.  The normalized original text is appended as a deterministic
    tie-breaker because homophones are common in Chinese indexes.
    """
    raw = unicodedata.normalize("NFKC", str(text or "")).strip()
    if not raw:
        return "", ""
    if contains_cjk(raw):
        try:
            from pypinyin import Style, lazy_pinyin  # type: ignore

            parts = lazy_pinyin(
                raw,
                style=Style.NORMAL,
                strict=False,
                errors=lambda chunk: [
                    _fold_latin(ch) or f"u{ord(ch):06x}" for ch in chunk
                ],
            )
            primary = "\x1f".join(str(part).casefold() for part in parts)
            return primary, raw.casefold()
        except Exception:
            # Dependency may be absent on an old environment or a rare input may
            # defeat romanisation.  Unicode order is only a fallback; exact
            # matches still work independently of this key.
            return "".join(f"u{ord(ch):06x}" for ch in raw), raw.casefold()
    return _fold_latin(raw), raw.casefold()
