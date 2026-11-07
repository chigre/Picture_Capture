from __future__ import annotations

"""Pure visual-positive/hard-negative review signals and latent row coordinates.

These helpers do not arbitrate, save or reject any Entry themselves.
Historical core forwards live positive/negative/column callbacks.
"""

from collections.abc import Callable, Collection
from typing import Any


def has_strong_positive_visual(candidate: dict) -> bool:
    for engine in ("paddle", "tesseract", "lens"):
        side = candidate.get(engine, {}) or {}
        if not isinstance(side, dict):
            continue
        features = side.get("features", {}) or {}
        if not isinstance(features, dict):
            continue
        if any(bool(features.get(key)) for key in (
            "visual_entry_marker",
            "configured_marker_evidence",
            "numbered_prefix_evidence",
            "cjk_single_strong_visual",
            "cjk_visual_projection_rescue",
            "cjk_visual_projection_confirmed",
            "strong_visual_fallback",
        )):
            return True
    return False


def hard_negative_level(
    candidate: dict, *, positive_fn: Callable[[dict], bool],
    hard_reasons: Collection[str],
) -> str:
    """Return '', 'single', or 'dual' for specific negative OCR evidence.

    A dual verdict means both local OCR engines independently agree on the same
    internal/continuation class. A single verdict is allowed only for an
    exceptionally confident engine with a matching semantic feature.
    """
    if candidate.get("selected") or candidate.get("manual_override"):
        return ""
    if str(candidate.get("position_variant", "refined")) != "refined":
        return ""
    if positive_fn(candidate):
        return ""

    votes = 0
    strong_single = False
    for engine in ("paddle", "tesseract"):
        side = candidate.get(engine, {}) or {}
        if not isinstance(side, dict) or side.get("y") is None:
            continue
        reason = str(side.get("reason") or "")
        if reason not in hard_reasons:
            continue
        try:
            confidence = float(side.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < 0.84:
            continue
        votes += 1
        features = side.get("features", {}) or {}
        if not isinstance(features, dict):
            features = {}
        matching_feature = bool(
            (reason == "continuation_fragment" and features.get("looks_like_continuation"))
            or (reason == "internal_article_symbol" and features.get("internal_article_symbol"))
            or (reason == "internal_relation_label" and features.get("internal_relation_label"))
            or (reason == "internal_locution" and features.get("internal_locution"))
        )
        if confidence >= 0.94 and matching_feature:
            strong_single = True
    if votes >= 2:
        return "dual"
    if strong_single:
        return "single"
    return ""


def hard_negative_consensus(candidate: dict, *, level_fn: Callable[[dict], str]) -> bool:
    return bool(level_fn(candidate))

def latent_review_rows(
    review_candidates: list[dict] | None,
    geometry: Any, *, column_fn: Callable[[int, Any, int], int],
) -> list[tuple[dict, int, int]]:
    rows: list[tuple[dict, int, int]] = []
    for candidate in review_candidates or []:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("selected") or candidate.get("manual_override"):
            continue
        if str(candidate.get("position_variant", "refined")) != "refined":
            continue
        try:
            x = int(candidate.get("source_x"))
            y = int(candidate.get("source_y"))
        except (TypeError, ValueError):
            continue
        if y <= 0:
            continue
        _u, v = geometry.source_to_canonical(x, y)
        col = int(candidate.get("column", column_fn(x, geometry, y)))
        rows.append((candidate, col, int(v)))
    return rows
