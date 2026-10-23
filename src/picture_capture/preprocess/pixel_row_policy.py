"""Assess candidate pixel rows and re-audit the retained orthogonal result.

Candidate retention and final convergence keep their separate existing gates.
The owner measures supplied images but never applies or replaces a transform.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from PIL import Image

from ..models import AppSettings
from .orthogonal_dewarp import PixelRowProfileAudit


@dataclass(frozen=True, slots=True)
class CandidatePixelAssessment:
    row_available: bool
    row_safe: bool
    row_improved: bool
    tail_available: bool
    tail_retainable: bool
    row_verdict: str
    tail_verdict: str


@dataclass(frozen=True, slots=True)
class RetainedPixelDiagnostics:
    """Final row/tail measurements, including partial updates on audit failure."""

    row_sample_count: int
    before_row_p90_px: float
    after_row_p90_px: float
    before_row_worst_px: float
    after_row_worst_px: float
    row_verdict: str
    tail_sample_count: int
    before_tail_p90_px: float
    after_tail_p90_px: float
    before_tail_worst_px: float
    after_tail_worst_px: float
    tail_verdict: str
    alignment_verdict: str


def assess_candidate_pixels(
    candidate_pixel_rows: PixelRowProfileAudit,
    baseline_pixel_rows: PixelRowProfileAudit,
    *,
    row_p90_max_px: float,
    row_worst_max_px: float,
    tail_p90_max_px: float,
    tail_worst_max_px: float,
    tail_progress_ratio: float,
    tail_max_regression_px: float,
) -> CandidatePixelAssessment:
    pixel_row_available = bool(candidate_pixel_rows.sample_count >= 8 and candidate_pixel_rows.valid_column_count >= 1)
    pixel_row_safe = bool(
        pixel_row_available
        and candidate_pixel_rows.p90_shift_px <= row_p90_max_px
        and candidate_pixel_rows.worst_shift_px <= row_worst_max_px
    )
    pixel_row_improved = bool(
        pixel_row_available
        and baseline_pixel_rows.sample_count >= 8
        and baseline_pixel_rows.p90_shift_px > 1e-6
        and candidate_pixel_rows.p90_shift_px <= baseline_pixel_rows.p90_shift_px * 0.70
        and candidate_pixel_rows.worst_shift_px
        <= max(
            row_worst_max_px,
            baseline_pixel_rows.worst_shift_px * 0.80,
        )
    )
    if pixel_row_safe:
        orthogonal_pixel_row_verdict = "passed"
    elif pixel_row_improved:
        orthogonal_pixel_row_verdict = "improved_review"
    elif pixel_row_available:
        orthogonal_pixel_row_verdict = "failed"
    else:
        orthogonal_pixel_row_verdict = "insufficient"

    pixel_tail_available = bool(
        candidate_pixel_rows.bottom_tail_sample_count >= 2 and candidate_pixel_rows.bottom_tail_valid_column_count >= 1
    )
    pixel_tail_safe = bool(
        pixel_tail_available
        and candidate_pixel_rows.bottom_tail_p90_shift_px <= tail_p90_max_px
        and candidate_pixel_rows.bottom_tail_worst_shift_px <= tail_worst_max_px
    )
    baseline_tail_available = bool(
        baseline_pixel_rows.bottom_tail_sample_count >= 2 and baseline_pixel_rows.bottom_tail_valid_column_count >= 1
    )
    pixel_tail_improved = bool(
        pixel_tail_available
        and baseline_tail_available
        and baseline_pixel_rows.bottom_tail_p90_shift_px > 1e-6
        and candidate_pixel_rows.bottom_tail_p90_shift_px
        <= baseline_pixel_rows.bottom_tail_p90_shift_px * tail_progress_ratio
        and candidate_pixel_rows.bottom_tail_worst_shift_px
        <= baseline_pixel_rows.bottom_tail_worst_shift_px + tail_max_regression_px
    )
    # Candidate retention and loop convergence are intentionally
    # different decisions. A pass that dramatically fixes the body
    # must not be discarded merely because a tiny page-tail residual
    # needs another pass. Keep it when the physical tail has not
    # meaningfully regressed; only the caller's stop gate requires tail
    # PASS. This prevents the v23 0014 regression (body 5→1 px,
    # tail 6→4.3 px) from rolling the whole page back to deskew.
    pixel_tail_retainable = bool(
        not pixel_tail_available
        or pixel_tail_safe
        or pixel_tail_improved
        or (
            baseline_tail_available
            and candidate_pixel_rows.bottom_tail_p90_shift_px
            <= baseline_pixel_rows.bottom_tail_p90_shift_px + tail_max_regression_px
            and candidate_pixel_rows.bottom_tail_worst_shift_px
            <= baseline_pixel_rows.bottom_tail_worst_shift_px + tail_max_regression_px
        )
    )
    if pixel_tail_safe:
        orthogonal_bottom_tail_verdict = "passed"
    elif pixel_tail_improved:
        orthogonal_bottom_tail_verdict = "improved_review"
    elif pixel_tail_available:
        orthogonal_bottom_tail_verdict = "failed"
    else:
        orthogonal_bottom_tail_verdict = "insufficient"

    return CandidatePixelAssessment(
        row_available=pixel_row_available,
        row_safe=pixel_row_safe,
        row_improved=pixel_row_improved,
        tail_available=pixel_tail_available,
        tail_retainable=pixel_tail_retainable,
        row_verdict=orthogonal_pixel_row_verdict,
        tail_verdict=orthogonal_bottom_tail_verdict,
    )


def reaudit_retained_pixels(
    image: Image.Image,
    polygons: list[np.ndarray],
    settings: AppSettings,
    *,
    applied: bool,
    current: RetainedPixelDiagnostics,
    warnings: list[str],
    pixel_auditor: Callable,
    initial_row_available: bool,
    initial_row_p90_px: float,
    initial_row_worst_px: float,
    initial_tail_available: bool,
    initial_tail_p90_px: float,
    initial_tail_worst_px: float,
    row_p90_max_px: float,
    row_worst_max_px: float,
    tail_p90_max_px: float,
    tail_worst_max_px: float,
    tail_progress_ratio: float,
    tail_max_regression_px: float,
) -> RetainedPixelDiagnostics:
    orthogonal_pixel_row_sample_count = current.row_sample_count
    orthogonal_before_pixel_row_p90_px = current.before_row_p90_px
    orthogonal_after_pixel_row_p90_px = current.after_row_p90_px
    orthogonal_before_pixel_row_worst_px = current.before_row_worst_px
    orthogonal_after_pixel_row_worst_px = current.after_row_worst_px
    orthogonal_pixel_row_verdict = current.row_verdict
    orthogonal_bottom_tail_sample_count = current.tail_sample_count
    orthogonal_before_bottom_tail_p90_px = current.before_tail_p90_px
    orthogonal_after_bottom_tail_p90_px = current.after_tail_p90_px
    orthogonal_before_bottom_tail_worst_px = current.before_tail_worst_px
    orthogonal_after_bottom_tail_worst_px = current.after_tail_worst_px
    orthogonal_bottom_tail_verdict = current.tail_verdict
    orthogonal_alignment_verdict = current.alignment_verdict
    # Re-audit the actual retained pixels after all accepted/rejected
    # attempts. A later rejected residual pass must not overwrite diagnostics
    # for the earlier accepted page.
    if applied and polygons:
        try:
            retained_pixel_rows = pixel_auditor(
                image,
                polygons,
                settings,
            )
            if retained_pixel_rows.sample_count >= 8:
                orthogonal_pixel_row_sample_count = int(retained_pixel_rows.sample_count)
                if initial_row_available:
                    orthogonal_before_pixel_row_p90_px = float(initial_row_p90_px)
                    orthogonal_before_pixel_row_worst_px = float(initial_row_worst_px)
                orthogonal_after_pixel_row_p90_px = float(retained_pixel_rows.p90_shift_px)
                orthogonal_after_pixel_row_worst_px = float(retained_pixel_rows.worst_shift_px)
                orthogonal_bottom_tail_sample_count = int(retained_pixel_rows.bottom_tail_sample_count)
                if initial_tail_available:
                    orthogonal_before_bottom_tail_p90_px = float(initial_tail_p90_px)
                    orthogonal_before_bottom_tail_worst_px = float(initial_tail_worst_px)
                orthogonal_after_bottom_tail_p90_px = float(retained_pixel_rows.bottom_tail_p90_shift_px)
                orthogonal_after_bottom_tail_worst_px = float(retained_pixel_rows.bottom_tail_worst_shift_px)
                retained_safe = bool(
                    retained_pixel_rows.p90_shift_px <= row_p90_max_px
                    and retained_pixel_rows.worst_shift_px <= row_worst_max_px
                )
                retained_improved = bool(
                    initial_row_available
                    and initial_row_p90_px > 1e-6
                    and retained_pixel_rows.p90_shift_px <= initial_row_p90_px * 0.70
                    and retained_pixel_rows.worst_shift_px
                    <= max(
                        row_worst_max_px,
                        initial_row_worst_px * 0.80,
                    )
                )
                if retained_safe:
                    orthogonal_pixel_row_verdict = "passed"
                elif retained_improved:
                    orthogonal_pixel_row_verdict = "improved_review"
                else:
                    orthogonal_pixel_row_verdict = "failed"

                retained_tail_available = bool(
                    retained_pixel_rows.bottom_tail_sample_count >= 2
                    and retained_pixel_rows.bottom_tail_valid_column_count >= 1
                )
                retained_tail_safe = bool(
                    retained_tail_available
                    and retained_pixel_rows.bottom_tail_p90_shift_px <= tail_p90_max_px
                    and retained_pixel_rows.bottom_tail_worst_shift_px <= tail_worst_max_px
                )
                retained_tail_improved = bool(
                    retained_tail_available
                    and initial_tail_available
                    and initial_tail_p90_px > 1e-6
                    and retained_pixel_rows.bottom_tail_p90_shift_px <= initial_tail_p90_px * tail_progress_ratio
                    and retained_pixel_rows.bottom_tail_worst_shift_px <= initial_tail_worst_px + tail_max_regression_px
                )
                if retained_tail_safe:
                    orthogonal_bottom_tail_verdict = "passed"
                elif retained_tail_improved:
                    orthogonal_bottom_tail_verdict = "improved_review"
                elif retained_tail_available:
                    orthogonal_bottom_tail_verdict = "failed"
                else:
                    orthogonal_bottom_tail_verdict = "insufficient"

                if orthogonal_pixel_row_verdict == "passed" and (
                    not retained_tail_available or orthogonal_bottom_tail_verdict == "passed"
                ):
                    orthogonal_alignment_verdict = "passed"
                elif orthogonal_pixel_row_verdict in {"passed", "improved_review"} and (
                    not retained_tail_available or orthogonal_bottom_tail_verdict in {"passed", "improved_review"}
                ):
                    orthogonal_alignment_verdict = "improved_review"
                else:
                    orthogonal_alignment_verdict = "failed"
        except Exception as exc:
            warnings.append(f"最终正交像素行复检不可用：{exc}")

    return RetainedPixelDiagnostics(
        row_sample_count=orthogonal_pixel_row_sample_count,
        before_row_p90_px=orthogonal_before_pixel_row_p90_px,
        after_row_p90_px=orthogonal_after_pixel_row_p90_px,
        before_row_worst_px=orthogonal_before_pixel_row_worst_px,
        after_row_worst_px=orthogonal_after_pixel_row_worst_px,
        row_verdict=orthogonal_pixel_row_verdict,
        tail_sample_count=orthogonal_bottom_tail_sample_count,
        before_tail_p90_px=orthogonal_before_bottom_tail_p90_px,
        after_tail_p90_px=orthogonal_after_bottom_tail_p90_px,
        before_tail_worst_px=orthogonal_before_bottom_tail_worst_px,
        after_tail_worst_px=orthogonal_after_bottom_tail_worst_px,
        tail_verdict=orthogonal_bottom_tail_verdict,
        alignment_verdict=orthogonal_alignment_verdict,
    )
