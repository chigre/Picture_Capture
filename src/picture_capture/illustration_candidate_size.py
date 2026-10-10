"""Compute minimum connected-component dimensions for illustration detection."""
from __future__ import annotations

from .models import AppSettings


def illustration_candidate_min_dimensions(
    settings: AppSettings, analysis_width: int, analysis_height: int
) -> tuple[int, int]:
    """Return minimum width and height in analysis pixels.

    Percentages are relative to the corresponding analysis-crop dimension.
    Pixel values refer to the analysis image, not the original source scan.
    """
    width = max(0.0, float(settings.illustration_detect_min_width))
    height = max(0.0, float(settings.illustration_detect_min_height))
    if str(settings.illustration_detect_size_unit).strip().lower() != "px":
        width *= max(0, analysis_width) / 100.0
        height *= max(0, analysis_height) / 100.0
    return max(0, round(width)), max(0, round(height))
