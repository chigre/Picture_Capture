from __future__ import annotations

"""Pure OCR text normalization and voting without headword/layout semantics.

Channel model dataclasses remain defined in picture_capture.ocr_channel to
preserve their historical runtime and pickle identities. This leaf depends on
those types for static checking only; it never imports the OCR runtime.
"""

import unicodedata
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from ..ocr_channel import OcrChannelPlan, OcrTextChoice


def channel_text_key(value: object) -> str:
    """Low-level OCR agreement key; consumers may still apply richer parsing."""

    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return " ".join(text.split())


def choose_ocr_text(
    plan: OcrChannelPlan,
    choices: Iterable[OcrTextChoice],
) -> tuple[OcrTextChoice | None, bool]:
    """Choose text without embedding any separator/headword drawing policy.

    Exact normalized agreement between two enabled voting engines wins. When
    engines disagree, deterministic channel order is used instead of inventing a
    geometry/parser score here; higher-level consumers remain free to perform a
    richer arbitration before calling this helper. Diagnostic-only engines never
    become the selected text source, even when all voting engines fail.
    """

    by_engine = {
        item.engine: item
        for item in choices
        if str(item.text or "").strip()
    }
    voting = [
        by_engine[name]
        for name in plan.voting_engines
        if name in by_engine
    ]
    if not voting:
        return None, False

    groups: dict[str, list[OcrTextChoice]] = {}
    for item in voting:
        key = channel_text_key(item.text)
        if key:
            groups.setdefault(key, []).append(item)
    agreeing = [items for items in groups.values() if len(items) >= 2]
    if agreeing:
        agreeing.sort(
            key=lambda items: (
                -len(items),
                min(plan.enabled_engines.index(item.engine) for item in items),
            )
        )
        group = agreeing[0]
        group.sort(key=lambda item: plan.enabled_engines.index(item.engine))
        return group[0], True

    return voting[0], False

