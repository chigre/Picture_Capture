from __future__ import annotations

"""Percent/pixel conversion helpers for persisted source-image geometry."""

from PIL import Image

from .models import AppSettings


# User-facing layout geometry is expressed as percentages of the current source
# image. Algorithms and persisted legacy fields remain in source-image pixels.
# Horizontal measurements use image width; vertical measurements use image height.
LAYOUT_PERCENT_AXES = {
    "start_y": "height",
    "manual_x": "width",
    "column_width": "width",
    "gutter": "width",
    "character_height": "height",
    "row_padding": "height",
    "body_indent": "width",
    "horizontal_tolerance": "width",
    "analysis_left": "width",
    "analysis_right": "width",
    "paddle_header_search_height": "height",
}


def _layout_percent_denominator(image: Image.Image | None, name: str) -> float | None:
    if image is None or name not in LAYOUT_PERCENT_AXES:
        return None
    axis = LAYOUT_PERCENT_AXES[name]
    return float(max(1, image.width if axis == "width" else image.height))


def _layout_pixels_to_percent(image: Image.Image | None, name: str, pixels: int | float) -> float:
    denominator = _layout_percent_denominator(image, name)
    if denominator is None:
        return float(pixels)
    return float(pixels) * 100.0 / denominator


def _layout_percent_to_pixels(image: Image.Image | None, name: str, percent: int | float) -> int:
    denominator = _layout_percent_denominator(image, name)
    if denominator is None:
        return int(round(float(percent)))
    return int(round(float(percent) * denominator / 100.0))


def _format_layout_percent(value: int | float) -> str:
    rendered = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return rendered or "0"


def _column_pixels_to_percent(settings: AppSettings, pixels: int | float) -> float:
    """Convert a source-pixel horizontal distance to % of configured column width."""
    denominator = float(max(1, int(getattr(settings, "column_width", 1) or 1)))
    return float(pixels) * 100.0 / denominator


def _column_percent_to_pixels(settings: AppSettings, percent: int | float) -> int:
    """Convert % of configured column width back to source-image pixels."""
    denominator = float(max(1, int(getattr(settings, "column_width", 1) or 1)))
    return int(round(float(percent) * denominator / 100.0))


def _review_height_pixels_to_percent(
    image: Image.Image | None, pixels: int | float,
) -> float:
    """Convert a proofreading vertical source-pixel distance to % image height."""
    return _layout_pixels_to_percent(image, "character_height", pixels)


def _review_height_percent_to_pixels(
    image: Image.Image | None, percent: int | float,
) -> int:
    """Convert a proofreading % image-height value back to source pixels."""
    return _layout_percent_to_pixels(image, "character_height", percent)


def _format_review_height_percent(
    image: Image.Image | None, pixels: int | float,
) -> str:
    return _format_layout_percent(_review_height_pixels_to_percent(image, pixels))
