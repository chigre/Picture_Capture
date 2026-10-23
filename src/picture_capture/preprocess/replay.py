"""Replay accepted preprocessing geometry through explicitly supplied operations."""
from __future__ import annotations

from typing import Callable
from PIL import Image

from .models import PreprocessAnalysis
from .orthogonal_dewarp import OrthogonalWarpEstimate


def geometry_corrected_image(
    image: Image.Image,
    analysis: PreprocessAnalysis,
    *, deskewer: Callable, homography_warper: Callable,
    document_unwarper: Callable, orthogonal_warper: Callable,
    step_decoder: Callable,
) -> Image.Image:
    """Apply the saved geometric correction without cropping.

    Export/preview reuse the exact analysis transform; they do not run Paddle
    again, so a reviewed result remains deterministic.
    """
    corrected = deskewer(image, analysis.applied_angle_deg)
    if analysis.perspective_matrix is not None:
        corrected = homography_warper(
            corrected, analysis.perspective_matrix,
        )
    if analysis.geometry_mode == "uvdoc":
        corrected = document_unwarper(corrected)
    if analysis.orthogonal_applied and analysis.orthogonal_steps:
        for step_payload in analysis.orthogonal_steps:
            estimate, row_gain = step_decoder(
                dict(step_payload)
            )
            corrected = orthogonal_warper(
                corrected,
                estimate,
                row_gain=row_gain,
                separator_gain=1.0,
            )
    elif (
        analysis.orthogonal_applied
        and analysis.orthogonal_y_knots
        and analysis.orthogonal_angle_knots_deg
    ):
        # Compatibility fallback for pre-v22 in-memory objects.
        estimate = OrthogonalWarpEstimate(
            y_knots=tuple(analysis.orthogonal_y_knots),
            angle_knots_deg=tuple(analysis.orthogonal_angle_knots_deg),
            x_knots=tuple(analysis.orthogonal_x_knots),
            row_grid_rows=int(analysis.orthogonal_row_grid_rows),
            row_grid_cols=int(analysis.orthogonal_row_grid_cols),
            row_angle_grid_deg=tuple(
                analysis.orthogonal_row_angle_grid_deg
            ),
            row_displacement_grid_px=tuple(
                analysis.orthogonal_row_displacement_grid_px
            ),
            separator_y_knots=tuple(analysis.orthogonal_separator_y_knots),
            separator_shift_knots_px=tuple(
                analysis.orthogonal_separator_shift_knots_px
            ),
            reference_x=float(analysis.orthogonal_reference_x),
            active=True,
        )
        corrected = orthogonal_warper(
            corrected,
            estimate,
            row_gain=float(analysis.orthogonal_row_gain),
            separator_gain=1.0,
        )
    return corrected
