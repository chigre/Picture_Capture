from __future__ import annotations

"""OCR CJK row association, selected grammar evidence and visual rescue policy.

Keeps existing Profile v0 legacy thresholds vs saved Profile v1 explicit
controls. This module neither accepts/rejects review rows nor persists them.
"""

from collections.abc import Callable
from typing import Any
from ..models import AppSettings
from .headword_models import HeadwordParse


def accepted_cjk_row_for_visual_run(
    diagnostics: list[dict[str, Any]],
    run_start: int,
    run_end: int,
    word: str, *, single_cjk_fn: Callable[[str], bool],
) -> dict[str, Any] | None:
    """Find an already accepted CJK row that belongs to the same visual glyph.

    The OCR/grammar path stores the *refined separator Y* as the entry marker,
    while visual projection starts from the glyph's ink run.  Comparing those
    two marker Y values directly is therefore unreliable.  Compare the original
    OCR box against the visual run instead; this is the physical evidence that
    both candidates describe the same printed character.
    """
    run_h = max(1, run_end - run_start)
    run_center = (run_start + run_end) / 2.0
    for row in diagnostics:
        if "meta" in row or not row.get("accepted"):
            continue
        lemma = str(row.get("normalized_headword", ""))
        features = row.get("features", {}) or {}
        if not (single_cjk_fn(lemma) or features.get("cjk_single_visual")):
            continue
        box = row.get("box") or []
        if not isinstance(box, list) or len(box) != 4:
            continue
        y0, y1 = int(box[1]), int(box[3])
        box_h = max(1, y1 - y0)
        overlap = max(0, min(y1, run_end) - max(y0, run_start))
        center_distance = abs(((y0 + y1) / 2.0) - run_center)
        same_word = bool(word and lemma and word == lemma)
        same_physical_row = (
            overlap >= min(box_h, run_h) * 0.22
            or center_distance <= max(box_h, run_h) * 0.62
        )
        # OCR sometimes places the accepted single-Han box on the pinyin/baseline
        # rather than around the full display glyph.  If the normalized lemma is
        # the same, allow a wider vertical association so the later visual rescue
        # confirms the existing candidate instead of creating a second separator
        # inside the same entry.  Nearby repeated homographs remain distinct
        # because this relaxed window is still bounded to roughly one glyph.
        same_word_shifted_box = bool(
            same_word
            and center_distance <= max(run_h * 1.45, box_h * 1.6)
        )
        if (
            (same_physical_row and (same_word or features.get("cjk_single_visual")))
            or same_word_shifted_box
        ):
            return row
    return None


def selected_tail_structure_evidence(
    settings: AppSettings,
    parsed: HeadwordParse | None,
    *,
    pos_allowed_by_rules: bool = True,
) -> tuple[tuple[str, ...], dict[str, bool]]:
    """Return only the post-lemma evidence families selected by the user.

    Version 0 mirrors the historical hidden gate (POS / inflection /
    descriptor). Version 1 makes each family explicit in Project Profile.
    """
    pronunciation = bool(
        parsed
        and any(
            str(item).startswith("pronunciation:")
            for item in parsed.parser_trace
        )
    )
    available = {
        "pos": bool(parsed and parsed.has_pos and pos_allowed_by_rules),
        "inflection": bool(parsed and parsed.has_inflection),
        "variant": bool(parsed and parsed.variants),
        "pronunciation": pronunciation,
        "descriptor": bool(parsed and parsed.has_descriptor),
    }
    if int(getattr(settings, "profile_tail_structure_version", 0) or 0) < 1:
        selected = {
            "pos": available["pos"],
            "inflection": available["inflection"],
            "variant": False,
            "pronunciation": False,
            "descriptor": available["descriptor"],
        }
    else:
        selected = {
            "pos": available["pos"] and bool(
                getattr(settings, "profile_tail_allow_pos", True)
            ),
            "inflection": available["inflection"] and bool(
                getattr(settings, "profile_tail_allow_inflection", True)
            ),
            "variant": available["variant"] and bool(
                getattr(settings, "profile_tail_allow_variant", True)
            ),
            "pronunciation": available["pronunciation"] and bool(
                getattr(settings, "profile_tail_allow_pronunciation", False)
            ),
            "descriptor": available["descriptor"] and bool(
                getattr(settings, "profile_tail_allow_descriptor", True)
            ),
        }
    names = tuple(name for name, present in selected.items() if present)
    diagnostics = {
        **{f"available_{name}": value for name, value in available.items()},
        **{f"selected_{name}": value for name, value in selected.items()},
    }
    return names, diagnostics


def ordinary_visual_rescue_thresholds(
    settings: AppSettings,
) -> dict[str, float | str]:
    """Resolve thresholds used by ordinary left-edge visual rescue.

    Saved Project Profile tail controls (version >= 1) are fully explicit:
    rescue uses the same visible boldness threshold shown in the headword
    specificity panel. Left-edge tolerance and candidate-score thresholds are
    already applied by the ordinary candidate gate. No extra hidden height,
    boldness, or confidence threshold is added for saved explicit Profiles.

    Version 0 keeps the historical thresholds only for backward compatibility
    with projects that have not yet saved the new Profile controls.
    """
    explicit = int(
        getattr(settings, "profile_tail_structure_version", 0) or 0
    ) >= 1
    if explicit:
        return {
            "source": "visible_profile_specificity",
            "boldness": float(settings.paddle_boldness_ratio),
            "height": 0.0,
            "confidence": float(settings.paddle_rec_score_threshold),
        }
    return {
        "source": "legacy_hidden_thresholds",
        "boldness": max(
            float(getattr(settings, "paddle_strong_edge_visual_boldness_ratio", 1.22) or 1.22),
            float(settings.paddle_boldness_ratio) * 1.03,
        ),
        "height": max(
            0.75,
            float(getattr(settings, "paddle_strong_edge_visual_height_ratio", 0.90) or 0.90),
        ),
        "confidence": max(
            float(settings.paddle_rec_score_threshold),
            float(getattr(settings, "paddle_strong_edge_visual_min_confidence", 0.55) or 0.55),
        ),
    }


def ordinary_strong_edge_visual_rescue(
    settings: AppSettings,
    parsed: HeadwordParse | None,
    *,
    at_left: bool,
    below_header: bool,
    boldness_ratio: float,
    height_ratio: float,
    confidence: float,
    looks_like_continuation: bool,
    marker_noise: bool,
    thresholds_fn: Callable[[AppSettings], dict[str, float | str]],
) -> bool:
    """Recover a left-edge head when selected post-lemma OCR evidence fails.

    For saved explicit Profiles this path obeys the user-visible specificity
    controls instead of layering another hidden strong-edge threshold on top.
    Semantic guards remain: parsed lemma, strict left edge, body region, and
    no continuation/noise signal.
    """
    tail_controls_active = int(
        getattr(settings, "profile_tail_structure_version", 0) or 0
    ) >= 1
    rescue_enabled = (
        bool(getattr(settings, "profile_tail_allow_visual_rescue", False))
        if tail_controls_active
        else bool(getattr(settings, "paddle_allow_strong_edge_visual_rescue", False))
    )
    if not rescue_enabled:
        return False
    if (
        parsed is None
        or not parsed.normalized
        or len(parsed.normalized.strip("-")) < 3
        or not at_left
        or not below_header
        or looks_like_continuation
        or marker_noise
    ):
        return False

    thresholds = thresholds_fn(settings)
    return bool(
        boldness_ratio >= float(thresholds["boldness"])
        and height_ratio >= float(thresholds["height"])
        and confidence >= float(thresholds["confidence"])
    )
