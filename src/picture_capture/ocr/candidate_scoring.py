"""Pure R5.1 candidate parser/visual scoring; never infer ground truth.

All fields are frozen, primitive bools, and JSON-serializable by asdict().
This module does not import image, GUI, OCR models, settings or the runtime.
The evaluation order and weights are the original candidate_filter expression.
The separate pairing_arbitration._engine_quality computes engine q, NOT this
candidate score.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CandidateScoreFeatures:
    parsed: bool
    left_evidence: bool
    selected_pos: bool
    selected_inflection: bool
    selected_variant: bool
    selected_pronunciation: bool
    selected_descriptor: bool
    front_structure_cue: bool
    large: bool
    bold: bool
    separated: bool
    cjk_candidate_right_sparse: bool


def score_candidate(features: CandidateScoreFeatures) -> float:
    """Exact historical scoring terms and float operation order (R5.1)."""
    return (
        (2.0 if features.parsed else 0.0)
        + (2.0 if features.left_evidence else 0.0)
        + (3.0 if features.selected_pos else 0.0)
        + (2.0 if features.selected_inflection else 0.0)
        + (1.5 if features.selected_variant else 0.0)
        + (1.5 if features.selected_pronunciation else 0.0)
        + (3.0 if features.selected_descriptor else 0.0)
        + (1.0 if features.front_structure_cue else 0.0)
        + (0.75 if features.large else 0.0)
        + (1.0 if features.bold else 0.0)
        + (0.5 if features.separated else 0.0)
        + (0.75 if features.cjk_candidate_right_sparse else 0.0)
    )
