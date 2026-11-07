"""R5.2 pure OCR engine arbitration quality score (q), NOT candidate score.

The historical pairing_arbitration._engine_quality retains its call-time
pair/prefix conversions, error and monkeypatch contracts, then supplies this
immutable primitive-only snapshot. Weights, addition order, tie rules and
review thresholds are unchanged; q is not an accuracy probability.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EngineQualityFeatures:
    accepted: bool
    score: float
    confidence: float
    structural_cue: bool
    strong_visual_fallback: bool
    peer_typography_match: bool
    boundary_present: bool
    boundary_strength: float
    forced_accept: bool
    forced_reject: bool
    repair_count: int


def score_engine_quality(features: EngineQualityFeatures) -> float:
    """Exact historical q expression, preserving float operation ordering."""
    q = features.score + 2.0 * features.confidence + (
        1.0 if features.accepted else 0.0
    )
    if features.structural_cue:
        q += 1.0
    if features.strong_visual_fallback:
        q += 0.35
    if features.peer_typography_match:
        q += 0.30
    if features.boundary_present:
        # OCR-independent blank-to-ink boundary: small tie-breaking reward.
        q += 0.20 + 0.35 * features.boundary_strength
    if features.forced_accept:
        q += 1.2
    if features.forced_reject:
        q -= 5.0
    q -= min(0.9, 0.08 * features.repair_count)
    return q
