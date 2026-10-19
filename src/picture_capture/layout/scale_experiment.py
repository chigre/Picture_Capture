"""Opt-in, source-size-aware full-page Layout estimate experiment.

Source Page Understanding, illustration PPP, and PDIC stay in source pixels.
Only the reliability detector's temporary image is downsampled.
"""
from __future__ import annotations

from dataclasses import replace
import os

from PIL import Image

FLAG = "PICTURE_CAPTURE_LAYOUT_SCALE_EXPERIMENT"
SCALES = {"off", "auto", "75", "50"}


def choose_layout_scale(size: tuple[int, int], *, mode: str | None = None) -> float:
    mode = str(mode if mode is not None else os.environ.get(FLAG, "off")).strip().lower()
    if mode not in SCALES:
        return 1.0
    width, height = size
    longest = max(width, height)
    if mode == "off" or longest < 3000:
        return 1.0
    if mode == "75":
        return 0.75
    if mode == "50":
        return 0.50 if longest >= 4000 else 0.75
    return 0.50 if longest >= 4000 else 0.75


def scaled_layout_settings(settings, factor: float):
    updated = replace(settings)
    for name in (
        "start_y", "bottom_y", "manual_x", "column_width", "gutter",
        "character_height", "row_padding",
    ):
        value = getattr(updated, name, None)
        if isinstance(value, (int, float)):
            scaled = round(value * factor)
            setattr(updated, name, max(1, scaled) if name in {
                "column_width", "character_height",
            } else max(0, scaled))
    return updated


def restore_source_estimate(estimate, factor: float, source_width: int):
    """Return fresh detector estimate with *all* geometry back in source pixels."""
    def restored(value):
        return int(round(value / factor))
    coordinates = {
        "start_y", "column_width", "gutter", "manual_x", "bottom_y",
        "character_height", "row_padding",
    }
    changes = {name: restored(getattr(estimate, name)) for name in coordinates}
    if estimate.separator_x is not None:
        changes["separator_x"] = restored(estimate.separator_x)
    changes["canonical_width"] = source_width
    changes["column_starts"] = tuple(restored(x) for x in estimate.column_starts)
    changes["column_rights"] = tuple(restored(x) for x in estimate.column_rights)
    return replace(estimate, **changes)


def detect_at_scale(image: Image.Image, settings, backend, detector):
    configured = os.environ.get(FLAG)
    if configured is None:
        configured = "auto" if bool(getattr(settings, "layout_scale_enabled", False)) else "off"
    factor = choose_layout_scale(image.size, mode=configured)
    if factor == 1.0 or str(getattr(settings, "layout_transform", "identity")) != "identity":
        return detector(image, settings, backend), 1.0
    # Keep downsampling confined to this temporary detector image. The rest
    # of Layout Core must keep the full-resolution source-space analysis.
    reduced = image.resize(
        (max(1, round(image.width * factor)),
         max(1, round(image.height * factor))),
        Image.Resampling.BILINEAR,
    )
    try:
        estimate = detector(reduced, scaled_layout_settings(settings, factor), backend)
    finally:
        reduced.close()
    original = restore_source_estimate(estimate, factor, image.width)
    # Only approved macroscopic fields may come from the reduced estimate.
    # The remaining scalar fields retain the original-resolution project
    # priors; fine line/role analysis already uses the original image.
    values = {}
    for field, enabled_name in (
        ("columns", "layout_scale_columns"),
        ("column_width", "layout_scale_column_width"),
        ("gutter", "layout_scale_gutter"),
        ("start_y", "layout_scale_start_y"),
        ("manual_x", "layout_scale_manual_x"),
        ("character_height", "layout_scale_character_height"),
        ("row_padding", "layout_scale_row_padding"),
    ):
        if not bool(getattr(settings, enabled_name, False)):
            values[field] = getattr(settings, field)
    if not bool(getattr(settings, "layout_scale_manual_x", False)):
        # The returned detected lane boundaries must not carry downsampled
        # horizontal offsets into a manually anchored layout.
        values["column_starts"] = ()
        values["column_rights"] = ()
        values["separator_x"] = None
    original = replace(original, **values)
    return original, factor
