"""Conservative page-local headword style consistency evidence.

A candidate that looks like a continuation is NOT rescued merely because other
OCR rows are bold or share an indent. Only independent separator ink, explicit
lexical grammar, and nearby accepted headword style jointly permit rescue.
This operates per OCR column/band and never learns from rejected rows.
"""
from __future__ import annotations

from statistics import median
from typing import Any


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if 0 <= result < float("inf") else None


def peer_style_continuation_evidence(
    candidate: dict[str, Any], diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return evidence only; caller handles entry insertion/diagnostic promotion.

    Constraints require a near, independent accepted anchor above AND below,
    at least three trusted anchors, consistent left-edge/height/ink boldness,
    a confirmed actual image gap and explicit lexical structure. Early/late
    candidates and sparse pages deliberately abstain rather than hallucinate.
    """
    def no(reason: str, count: int = 0) -> dict[str, Any]:
        return {"supported": False, "reason": reason, "peer_count": count}

    if str(candidate.get("reject_reason", "") or "") != "continuation_fragment":
        return no("not_continuation")
    feat = candidate.get("features", {}) or {}
    rule = candidate.get("user_rule", {}) or {}
    if not isinstance(feat, dict) or not isinstance(rule, dict):
        return no("malformed_features")
    if rule.get("rejected") or rule.get("pos_excluded") or feat.get("forced_reject"):
        return no("explicit_reject")
    if any(feat.get(key) for key in (
        "marker_noise", "internal_article_symbol", "internal_relation_label",
        "internal_locution", "cjk_single_visual", "cjk_oversized_recovery",
    )):
        return no("hard_negative")
    if not feat.get("at_left") or not feat.get("below_header", True):
        return no("not_left_edge")
    structure = bool(
        candidate.get("pos_cue") or candidate.get("inflection_cue")
        or feat.get("front_structure_cue") or feat.get("tail_structure_satisfied")
    )
    if not structure:
        return no("no_explicit_grammar")
    gap = candidate.get("image_boundary_match", {}) or {}
    strength = _number(gap.get("strength")) if isinstance(gap, dict) else None
    if not feat.get("image_boundary_supported") or strength is None or strength < 0.55:
        return no("no_strong_image_gap")

    conf = _number(candidate.get("confidence"))
    bold = _number(feat.get("boldness_ratio"))
    height_ratio = _number(feat.get("height_ratio"))
    box = candidate.get("box") or []
    if (
        conf is None or conf < 0.90 or bold is None or bold < 0.90
        or height_ratio is None or not 0.70 <= height_ratio <= 1.60
        or not isinstance(box, (list, tuple)) or len(box) != 4
    ):
        return no("weak_candidate")
    cy = _number(candidate.get("source_y"))
    cx = _number(box[0])
    ch = _number(box[3] - box[1])
    if cy is None or cx is None or ch is None or ch < 2:
        return no("missing_geometry")
    window = max(220.0, 11.0 * ch)
    peers: list[tuple[float, float, float, float]] = []
    for row in diagnostics:
        if row is candidate or not row.get("accepted") or "meta" in row:
            continue
        other = row.get("features", {}) or {}
        if not isinstance(other, dict) or not other.get("at_left", False):
            continue
        if not (
            other.get("structural_cue")
            or other.get("front_structure_cue")
            or other.get("tail_structure_satisfied")
            or row.get("pos_cue")
        ):
            continue
        py = _number(row.get("source_y"))
        pb = _number(other.get("boldness_ratio"))
        ph = _number(other.get("height_ratio"))
        pc = _number(row.get("confidence"))
        pbox = row.get("box") or []
        if (
            py is None or abs(py - cy) > window or pb is None
            or ph is None or pc is None or pc < 0.85
            or not isinstance(pbox, (tuple, list)) or len(pbox) != 4
        ):
            continue
        px = _number(pbox[0])
        if px is None:
            continue
        peers.append((py, px, pb, ph))
    if len(peers) < 3:
        return no("insufficient_trusted_peers", len(peers))
    if not any(p[0] < cy for p in peers) or not any(p[0] > cy for p in peers):
        return no("not_bracketed_by_peers", len(peers))
    peer_x = float(median(p[1] for p in peers))
    peer_bold = float(median(p[2] for p in peers))
    peer_height = float(median(p[3] for p in peers))
    if abs(cx - peer_x) > max(5.0, ch * 0.35):
        return no("left_edge_differs", len(peers))
    if (
        bold < max(0.95, peer_bold * 0.91)
        or bold > peer_bold * 1.50
        or not peer_height * 0.77 <= height_ratio <= peer_height * 1.30
    ):
        return no("typography_differs", len(peers))

    return {
        "supported": True, "reason": "bracketed_local_headword_style_and_gap",
        "peer_count": len(peers), "peer_boldness": round(peer_bold, 4),
        "peer_height": round(peer_height, 4), "peer_left_x": round(peer_x, 3),
        "gap_strength": round(strength, 4),
    }
