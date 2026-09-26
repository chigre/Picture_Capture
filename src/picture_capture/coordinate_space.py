from __future__ import annotations

from typing import Any

from .layout_transform import LayoutTransform


# Public/persisted coordinate contract: one coordinate space only.
SOURCE_COORDINATE_SPACE = "source_image_pixels"

# Internal processing may rotate/resize/crop an image temporarily. Those
# coordinates are implementation details and are never persisted as settings.
CANONICAL_COORDINATE_SPACE = "canonical_full_resolution_pixels"
ANALYSIS_COORDINATE_SPACE = "analysis_resized_pixels"
BAND_COORDINATE_SPACE = "ocr_band_local_pixels"
LEGACY_PARAMETER_SPACE = "legacy_display_pixels"
LEGACY_REFERENCE_SPACE = "canonical_reference_page_pixels"

GEOMETRY_COORDINATE_VERSION = 3

# Project geometry settings are literal full-resolution image-pixel values.
# With the ordinary identity layout these are exactly original-image X/Y pixels.
# No runtime scaling by viewer width, page width, or a fixed reference width is
# permitted for version-3 settings.
SOURCE_GEOMETRY_FIELDS = (
    "gutter",
    "column_width",
    "start_y",
    "bottom_y",
    "manual_x",
    "manual_y",
    "body_indent",
    "character_height",
    "row_padding",
    "horizontal_tolerance",
    "column_track_radius",
    "column_track_block_height",
    "column_track_max_step",
    "illustration_detect_padding",
    "illustration_detect_right_padding",
    "review_single_cjk_line_height",
    "review_regular_crop_height",
)
# Compatibility import name for extensions that used the pre-v3 symbol.
CANONICAL_GEOMETRY_FIELDS = SOURCE_GEOMETRY_FIELDS


def _coordinate_version(settings: Any) -> int:
    try:
        return int(getattr(settings, "geometry_coordinate_version", 0) or 0)
    except (TypeError, ValueError):
        return 0


def geometry_uses_source_pixels(settings: Any) -> bool:
    """True when persisted geometry is already direct full-resolution pixels."""
    return _coordinate_version(settings) >= GEOMETRY_COORDINATE_VERSION


def geometry_uses_canonical_pixels(settings: Any) -> bool:
    """Compatibility predicate for old full-resolution layout code.

    v2 values were reference-page pixels but layout detection itself already ran
    at full resolution. Keep this predicate true for v2 so a not-yet-migrated
    object never falls back to GUI-display scaling.
    """
    return _coordinate_version(settings) >= 2


def legacy_parameter_scale(current_width: int, settings: Any) -> float:
    """Legacy GUI-display scale used only while opening pre-v2 projects.

    There is deliberately no 1400px fallback. If an old project did not save a
    display width, migration uses 1:1 instead of inventing another coordinate
    system.
    """
    width = max(1, int(current_width))
    try:
        display_width = int(getattr(settings, "parameter_display_width", 0) or 0)
    except (TypeError, ValueError):
        display_width = 0
    return max(0.01, display_width / width) if display_width > 0 else 1.0


def _legacy_reference_scale(current_width: int, settings: Any) -> float:
    """Read a v2 reference-page width only for one-time migration."""
    width = max(1, int(current_width))
    try:
        reference_width = int(getattr(settings, "geometry_reference_width", 0) or 0)
    except (TypeError, ValueError):
        reference_width = 0
    return width / reference_width if reference_width > 0 else 1.0


def setting_pixels(value: int | float, current_width: int, settings: Any) -> int:
    """Resolve one saved geometry value to full-resolution pixels.

    Version-3 values are already direct pixels and return unchanged. Older
    coordinate systems are converted only for backward compatibility.
    """
    numeric = float(value)
    version = _coordinate_version(settings)
    if version >= GEOMETRY_COORDINATE_VERSION:
        return round(numeric)
    if version == 2:
        return round(numeric * _legacy_reference_scale(current_width, settings))
    return round(numeric / legacy_parameter_scale(current_width, settings))


def pixels_to_setting(value: int | float, current_width: int, settings: Any) -> int:
    """Convert runtime pixels back to the saved setting representation.

    For version 3 this is intentionally an identity conversion.
    """
    numeric = float(value)
    version = _coordinate_version(settings)
    if version >= GEOMETRY_COORDINATE_VERSION:
        return round(numeric)
    if version == 2:
        return round(numeric / _legacy_reference_scale(current_width, settings))
    return round(numeric * legacy_parameter_scale(current_width, settings))


# Compatibility aliases: old imports now inherit the v3 identity semantics.
stored_geometry_to_canonical = setting_pixels
canonical_geometry_to_stored = pixels_to_setting


def canonical_to_analysis_scale(canonical_width: int, analysis_width: int) -> float:
    """Temporary processing scale only; never a settings-coordinate scale."""
    return max(1, int(analysis_width)) / max(1, int(canonical_width))


def migrate_legacy_geometry_settings(
    settings: Any,
    source_size: tuple[int, int],
) -> bool:
    """Migrate pre-v3 geometry once to direct full-resolution image pixels.

    v2 projects stored geometry against an explicit reference-page width; v1
    projects used GUI/display pixels. Both are resolved once using the first
    real project page. After migration neither legacy width participates in
    runtime behavior.
    """
    version = _coordinate_version(settings)
    if version >= GEOMETRY_COORDINATE_VERSION:
        if hasattr(settings, "geometry_coordinate_space"):
            settings.geometry_coordinate_space = SOURCE_COORDINATE_SPACE
        if hasattr(settings, "geometry_reference_width"):
            settings.geometry_reference_width = 0
        if hasattr(settings, "parameter_display_width"):
            settings.parameter_display_width = 0
        return False

    transform = LayoutTransform(
        str(getattr(settings, "layout_transform", "identity") or "identity")
    )
    current_width, _current_height = transform.canonical_size(
        (max(1, int(source_size[0])), max(1, int(source_size[1])))
    )
    if version == 2:
        factor = _legacy_reference_scale(current_width, settings)
    else:
        factor = 1.0 / max(legacy_parameter_scale(current_width, settings), 1e-9)

    for name in SOURCE_GEOMETRY_FIELDS:
        if not hasattr(settings, name):
            continue
        raw = getattr(settings, name)
        try:
            numeric = float(raw)
        except (TypeError, ValueError):
            continue
        if numeric == 0:
            continue
        setattr(settings, name, round(numeric * factor))

    raw_offsets = list(getattr(settings, "column_start_offsets", []) or [])
    if raw_offsets:
        migrated_offsets: list[int] = []
        for raw in raw_offsets:
            try:
                migrated_offsets.append(round(float(raw) * factor))
            except (TypeError, ValueError):
                migrated_offsets.append(0)
        settings.column_start_offsets = migrated_offsets

    settings.geometry_coordinate_version = GEOMETRY_COORDINATE_VERSION
    if hasattr(settings, "geometry_coordinate_space"):
        settings.geometry_coordinate_space = SOURCE_COORDINATE_SPACE
    if hasattr(settings, "geometry_reference_width"):
        settings.geometry_reference_width = 0
    if hasattr(settings, "parameter_display_width"):
        settings.parameter_display_width = 0
    return True


def coordinate_contract() -> dict[str, str | int]:
    """Machine-readable public/persisted coordinate contract."""
    return {
        "version": GEOMETRY_COORDINATE_VERSION,
        "coordinates": SOURCE_COORDINATE_SPACE,
        "annotations": SOURCE_COORDINATE_SPACE,
        "settings_geometry": SOURCE_COORDINATE_SPACE,
        "tuning_distances": SOURCE_COORDINATE_SPACE,
        "temporary_processing": "internal_only_not_persisted",
    }
