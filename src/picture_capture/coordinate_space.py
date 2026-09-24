from __future__ import annotations

from typing import Any

from .layout_transform import LayoutTransform


SOURCE_COORDINATE_SPACE = "source_image_pixels"
CANONICAL_COORDINATE_SPACE = "canonical_full_resolution_pixels"
CANONICAL_REFERENCE_SPACE = "canonical_reference_page_pixels"
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
    "horizontal_tolerance",
    "column_track_radius",
    "column_track_block_height",
    "column_track_max_step",
    "illustration_detect_padding",
    "illustration_detect_right_padding",
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


def _modern_reference_scale(canonical_width: int, settings: Any) -> float:
    """Current-page canonical pixels per persisted reference-page pixel."""
    width = max(1, int(canonical_width))
    try:
        reference = int(getattr(settings, "geometry_reference_width", 0) or 0)
    except (TypeError, ValueError):
        reference = 0
    return width / reference if reference > 0 else 1.0


def stored_geometry_to_canonical(
    value: int | float,
    canonical_width: int,
    settings: Any,
) -> int:
    """Convert persisted layout geometry to this page's canonical pixels.

    Modern projects store geometry in pixels of an explicit canonical reference
    page. This preserves the convenience of real pixel values while remaining
    stable when scans in one project have different resolutions. Legacy projects
    use their historical display-width scale until migrated.
    """
    numeric = float(value)
    if geometry_uses_canonical_pixels(settings):
        return round(numeric * _modern_reference_scale(canonical_width, settings))
    return round(numeric / legacy_parameter_scale(canonical_width, settings))


def canonical_geometry_to_stored(
    value: int | float,
    canonical_width: int,
    settings: Any,
) -> int:
    """Convert current-page canonical pixels to persisted reference-page pixels."""
    numeric = float(value)
    if geometry_uses_canonical_pixels(settings):
        return round(numeric / _modern_reference_scale(canonical_width, settings))
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
    """Upgrade old display-scaled layout geometry to canonical reference-page px.

    The conversion intentionally reproduces the old runtime interpretation using
    the saved parameter_display_width. It is idempotent and does not alter
    resolution-normalized OCR/profile tuning distances.
    """
    if geometry_uses_canonical_pixels(settings):
        if hasattr(settings, "geometry_coordinate_space"):
            settings.geometry_coordinate_space = CANONICAL_REFERENCE_SPACE
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
        settings.geometry_coordinate_space = CANONICAL_REFERENCE_SPACE
    if hasattr(settings, "geometry_reference_width"):
        settings.geometry_reference_width = int(canonical_width)
    return True


def initialize_geometry_reference(
    settings: Any,
    source_size: tuple[int, int],
    *,
    historical_1400_values: bool = False,
) -> bool:
    """Initialize an explicit canonical reference width once a real page is known.

    Fresh AppSettings uses the stable historical 1400px canonical reference so
    its shipped numeric defaults have an unambiguous physical meaning before any
    page is opened. This helper remains for older modern-format settings that
    explicitly persisted a missing/zero reference width.

    When historical_1400_values is true for such a zero-reference object, preserve
    the historical defaults' physical meaning by resolving those values to the
    first page before storing that page as the project's canonical reference.
    Existing modern JSON with a missing reference width keeps its current numeric
    values unchanged unless the caller explicitly identifies historical defaults.
    """
    if not geometry_uses_canonical_pixels(settings):
        return False
    try:
        existing = int(getattr(settings, "geometry_reference_width", 0) or 0)
    except (TypeError, ValueError):
        existing = 0
    if existing > 0:
        if hasattr(settings, "geometry_coordinate_space"):
            settings.geometry_coordinate_space = CANONICAL_REFERENCE_SPACE
        return False

    transform = LayoutTransform(
        str(getattr(settings, "layout_transform", "identity") or "identity")
    )
    canonical_width, _canonical_height = transform.canonical_size(
        (max(1, int(source_size[0])), max(1, int(source_size[1])))
    )

    if historical_1400_values:
        scale = min(1.0, REFERENCE_CANONICAL_WIDTH / max(1, canonical_width))
        for name in CANONICAL_GEOMETRY_FIELDS:
            if not hasattr(settings, name):
                continue
            raw = getattr(settings, name)
            try:
                numeric = float(raw)
            except (TypeError, ValueError):
                continue
            if numeric == 0:
                continue
            setattr(settings, name, round(numeric / max(scale, 1e-9)))

    settings.geometry_reference_width = int(canonical_width)
    if hasattr(settings, "geometry_coordinate_space"):
        settings.geometry_coordinate_space = CANONICAL_REFERENCE_SPACE
    return True

def coordinate_contract() -> dict[str, str | int]:
    """Machine-readable coordinate contract used by exports and diagnostics."""
    return {
        "version": 2,
        "annotations": SOURCE_COORDINATE_SPACE,
        "layout_geometry_runtime": CANONICAL_COORDINATE_SPACE,
        "layout_geometry_persisted": CANONICAL_REFERENCE_SPACE,
        "analysis": ANALYSIS_COORDINATE_SPACE,
        "ocr_band": BAND_COORDINATE_SPACE,
        "tuning_distances": REFERENCE_PIXEL_SPACE,
        "reference_width": REFERENCE_CANONICAL_WIDTH,
    }
