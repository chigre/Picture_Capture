from __future__ import annotations

from typing import Any

from .layout_transform import LayoutTransform


SOURCE_COORDINATE_SPACE = "source_image_pixels"
CANONICAL_COORDINATE_SPACE = "canonical_full_resolution_pixels"
ANALYSIS_COORDINATE_SPACE = "analysis_resized_pixels"
BAND_COORDINATE_SPACE = "ocr_band_local_pixels"
REFERENCE_PIXEL_SPACE = "reference_pixels_at_1400_canonical_width"
LEGACY_PARAMETER_SPACE = "legacy_display_pixels"

GEOMETRY_COORDINATE_VERSION = 2
REFERENCE_CANONICAL_WIDTH = 1400

# These project-specific values describe full-resolution canonical page geometry.
# They are persisted in canonical pixels from geometry_coordinate_version >= 2.
CANONICAL_GEOMETRY_FIELDS = (
    "gutter",
    "column_width",
    "start_y",
    "bottom_y",
    "manual_x",
    "manual_y",
    "body_indent",
    "character_height",
    "row_padding",
    "review_single_cjk_line_height",
    "review_regular_crop_height",
)


def geometry_uses_canonical_pixels(settings: Any) -> bool:
    try:
        return int(getattr(settings, "geometry_coordinate_version", 0) or 0) >= GEOMETRY_COORDINATE_VERSION
    except (TypeError, ValueError):
        return False


def legacy_parameter_scale(canonical_width: int, settings: Any) -> float:
    """Return legacy displayed-parameter pixels per canonical full-resolution pixel.

    This exists only for migration/backward compatibility. New runtime geometry
    must not depend on GUI zoom or parameter_display_width.
    """
    width = max(1, int(canonical_width))
    try:
        reference = int(getattr(settings, "parameter_display_width", 0) or 0)
    except (TypeError, ValueError):
        reference = 0
    if reference > 0:
        return max(0.01, reference / width)
    return min(1.0, REFERENCE_CANONICAL_WIDTH / width)


def stored_geometry_to_canonical(
    value: int | float,
    canonical_width: int,
    settings: Any,
) -> int:
    """Convert one persisted geometry value to canonical full-resolution pixels."""
    numeric = float(value)
    if geometry_uses_canonical_pixels(settings):
        return round(numeric)
    return round(numeric / legacy_parameter_scale(canonical_width, settings))


def canonical_geometry_to_stored(
    value: int | float,
    canonical_width: int,
    settings: Any,
) -> int:
    """Convert canonical full-resolution pixels to the persisted geometry space."""
    numeric = float(value)
    if geometry_uses_canonical_pixels(settings):
        return round(numeric)
    return round(numeric * legacy_parameter_scale(canonical_width, settings))


def reference_to_canonical(
    value: int | float,
    canonical_width: int,
) -> int:
    """Scale one resolution-normalized tuning distance to canonical pixels.

    OCR/profile tuning distances are defined at a fixed 1400-pixel canonical
    width. This keeps their meaning independent from GUI zoom and source scan
    resolution without pretending they are page coordinates.
    """
    width = max(1, int(canonical_width))
    return round(float(value) * width / REFERENCE_CANONICAL_WIDTH)


def reference_to_analysis(
    value: int | float,
    analysis_width: int,
) -> int:
    width = max(1, int(analysis_width))
    return round(float(value) * width / REFERENCE_CANONICAL_WIDTH)


def canonical_to_analysis_scale(canonical_width: int, analysis_width: int) -> float:
    return max(1, int(analysis_width)) / max(1, int(canonical_width))


def migrate_legacy_geometry_settings(
    settings: Any,
    source_size: tuple[int, int],
) -> bool:
    """Upgrade old display-scaled layout geometry to canonical full-resolution px.

    The conversion intentionally reproduces the old runtime interpretation using
    the saved parameter_display_width. It is idempotent and does not alter
    resolution-normalized OCR/profile tuning distances.
    """
    if geometry_uses_canonical_pixels(settings):
        if hasattr(settings, "geometry_coordinate_space"):
            settings.geometry_coordinate_space = CANONICAL_COORDINATE_SPACE
        return False

    transform = LayoutTransform(
        str(getattr(settings, "layout_transform", "identity") or "identity")
    )
    canonical_width, _canonical_height = transform.canonical_size(
        (max(1, int(source_size[0])), max(1, int(source_size[1])))
    )
    scale = legacy_parameter_scale(canonical_width, settings)

    for name in CANONICAL_GEOMETRY_FIELDS:
        if not hasattr(settings, name):
            continue
        raw = getattr(settings, name)
        try:
            numeric = float(raw)
        except (TypeError, ValueError):
            continue
        # Zero is a sentinel for several optional dimensions; preserve it.
        if numeric == 0:
            continue
        setattr(settings, name, round(numeric / scale))

    settings.geometry_coordinate_version = GEOMETRY_COORDINATE_VERSION
    if hasattr(settings, "geometry_coordinate_space"):
        settings.geometry_coordinate_space = CANONICAL_COORDINATE_SPACE
    return True


def coordinate_contract() -> dict[str, str | int]:
    """Machine-readable coordinate contract used by exports and diagnostics."""
    return {
        "version": 1,
        "annotations": SOURCE_COORDINATE_SPACE,
        "layout_geometry": CANONICAL_COORDINATE_SPACE,
        "analysis": ANALYSIS_COORDINATE_SPACE,
        "ocr_band": BAND_COORDINATE_SPACE,
        "tuning_distances": REFERENCE_PIXEL_SPACE,
        "reference_width": REFERENCE_CANONICAL_WIDTH,
    }
