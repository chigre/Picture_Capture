from __future__ import annotations

"""Stateless OCR display-headword normalization (no GUI or engine imports).

The historical paddle_headwords_core entrypoint injects its patchable regex
module and configured separators at call time.
"""

import re
from typing import Any


def normalize_headword(
    text: str,
    remove_syllable_separators: bool = True,
    *,
    syllable_separators: str,
    re_module: Any = re,
) -> str:
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
        value = re_module.sub(
            rf"(?<={letter})\s*(?:[·•∙‧.:+]+\s*-+|-+\s*[·•∙‧.:+]+)\s*(?={letter})",
            "·", value, flags=re_module.UNICODE,
        )
        separators = re_module.escape(syllable_separators)
        had_unambiguous_separator = bool(re_module.search(
            rf"(?<={letter})\s*[{separators}]\s*(?={letter})",
            value, flags=re_module.UNICODE,
        ))
        value = re_module.sub(
            rf"(?<={letter})\s*[{separators}]\s*(?={letter})",
            "", value, flags=re_module.UNICODE,
        )
        internal_hyphens = re_module.findall(
            rf"(?<={letter})\s*-\s*(?={letter})",
            value, flags=re_module.UNICODE,
        )
        remove_hyphens = had_unambiguous_separator or len(internal_hyphens) >= 2
        if not remove_hyphens and len(internal_hyphens) == 1:
            compact = re_module.sub(r"\s+", "", value)
            # Do not count leading/trailing bound-morpheme hyphens here.
            inner = compact.strip("-")
            parts = inner.split("-")
            if len(parts) == 2:
                left_letters = len(re_module.findall(letter, parts[0], flags=re_module.UNICODE))
                right_letters = len(re_module.findall(letter, parts[1], flags=re_module.UNICODE))
                remove_hyphens = min(left_letters, right_letters) <= 2 and max(left_letters, right_letters) <= 8
        if remove_hyphens:
            value = re_module.sub(
                rf"(?<={letter})\s*-\s*(?={letter})",
                "", value, flags=re_module.UNICODE,
            )
    value = re_module.sub(r"\s*([-\u2019'])\s*", r"\1", value)
    return value.strip()

