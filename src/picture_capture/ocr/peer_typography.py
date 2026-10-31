from __future__ import annotations

"""Page-local font-prototype diagnostics for rejected OCR candidates.

This is annotation-only: does not switch rejected rows to accepted. The core
supplies current robust median/MAD calculation for existing patch hooks.
"""

from collections.abc import Callable
from typing import Any
import numpy as np


def median_and_mad(values: list[float], *, np_module: Any = np) -> tuple[float, float]:
    """Return robust center/spread for page-local typography evidence."""
    if not values:
        return 0.0, 0.0
    array = np_module.asarray(values, dtype=float)
    median = float(np_module.median(array))
    mad = float(np_module.median(np_module.abs(array - median)))
    return median, mad


def annotate_peer_typography_matches(
    diagnostics: list[dict[str, Any]], *,
    median_mad_fn: Callable[[list[float]], tuple[float, float]],
) -> int:
    """Mark soft rejects that match the page's accepted headword typography.

    This is deliberately an annotation pass, not a direct acceptance pass.
    High-confidence accepted rows establish a page-local visual prototype.
    Borderline rows can then contribute this *independent* typography evidence
    to later multi-engine arbitration, which still requires an image boundary
    and the usual semantic safety guards before rescue.
    """
    anchors: list[dict[str, Any]] = []
    for row in diagnostics:
        if "meta" in row or not row.get("accepted"):
            continue
        features = row.get("features", {}) or {}
        if not isinstance(features, dict):
            continue
        try:
            confidence = float(row.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < 0.88:
            continue
        if features.get("forced_accept") or features.get("marker_noise"):
            continue
        if features.get("looks_like_continuation"):
            continue
        if not features.get("at_left", True):
            continue
        anchors.append(row)

    if len(anchors) < 4:
        return 0

    def feature_values(name: str) -> list[float]:
        values: list[float] = []
        for row in anchors:
            features = row.get("features", {}) or {}
            try:
                values.append(float(features.get(name)))
            except (TypeError, ValueError):
                pass
        return values

    height_center, height_mad = median_mad_fn(feature_values("height_ratio"))
    bold_center, bold_mad = median_mad_fn(feature_values("boldness_ratio"))
    gap_center, gap_mad = median_mad_fn(feature_values("preceding_gap"))

    soft_reasons = {
        "missing_pos_inflection_descriptor_or_symbol",
        "missing_selected_tail_structure",
        "score_below_threshold",
        "missing_structure_or_visual_cue",
        "candidate_rejected",
        "cjk_single_needs_stronger_visual_evidence",
        "cjk_single_not_visually_prominent",
        "cjk_bracket_needs_visual_evidence",
    }
    hard_flags = {
        "forced_reject",
        "marker_noise",
        "looks_like_continuation",
        "internal_article_symbol",
        "internal_relation_label",
        "internal_locution",
    }

    matched = 0
    for row in diagnostics:
        if "meta" in row or row.get("accepted"):
            continue
        reason = str(row.get("reject_reason", "") or "")
        if reason not in soft_reasons:
            continue
        if not str(row.get("normalized_headword", "") or "").strip():
            continue
        try:
            confidence = float(row.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < 0.68:
            continue
        features = row.get("features", {}) or {}
        if not isinstance(features, dict):
            continue
        if any(bool(features.get(name)) for name in hard_flags):
            continue
        if not features.get("at_left", False) or not features.get("below_header", True):
            continue
        if not features.get("image_boundary_supported", False):
            continue

        votes = 0
        details: dict[str, float | int] = {}

        def close_vote(
            name: str,
            center: float,
            mad: float,
            absolute_floor: float,
            *,
            lower_ratio: float | None = None,
        ) -> None:
            nonlocal votes
            try:
                value = float(features.get(name))
            except (TypeError, ValueError):
                return
            tolerance = max(float(absolute_floor), 3.5 * float(mad))
            if lower_ratio is not None and center > 0 and value < center * lower_ratio:
                details[f"peer_{name}_delta"] = round(value - center, 4)
                return
            if abs(value - center) <= tolerance:
                votes += 1
            details[f"peer_{name}_delta"] = round(value - center, 4)
            details[f"peer_{name}_tolerance"] = round(tolerance, 4)

        close_vote("height_ratio", height_center, height_mad, 0.14, lower_ratio=0.78)
        close_vote("boldness_ratio", bold_center, bold_mad, 0.12, lower_ratio=0.72)

        # Gap is useful only when the accepted typography has a stable rhythm.
        # On heterogeneous pages a large MAD automatically makes this cue weak.
        if gap_center > 0:
            gap_floor = max(2.0, gap_center * 0.20)
            close_vote("preceding_gap", gap_center, gap_mad, gap_floor)

        if votes < 2:
            continue

        features["peer_typography_match"] = True
        features["peer_typography_votes"] = int(votes)
        features["peer_typography_anchor_count"] = int(len(anchors))
        features["peer_typography_height_center"] = round(height_center, 4)
        features["peer_typography_boldness_center"] = round(bold_center, 4)
        features["peer_typography_gap_center"] = round(gap_center, 3)
        features.update(details)
        trace = row.setdefault("parser_trace", [])
        if "peer_typography_match" not in trace:
            trace.append("peer_typography_match")
        bugs = row.setdefault("bug_types", [])
        if "PEER_TYPOGRAPHY_MATCH" not in bugs:
            bugs.append("PEER_TYPOGRAPHY_MATCH")
        matched += 1
    return matched
