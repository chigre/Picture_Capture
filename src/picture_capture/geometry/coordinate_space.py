from __future__ import annotations

SOURCE_COORDINATE_SPACE = "source_image_pixels"


def coordinate_contract() -> dict[str, str]:
    """The only public/persisted coordinate contract used by Picture Capture."""
    return {
        "coordinates": SOURCE_COORDINATE_SPACE,
        "annotations": SOURCE_COORDINATE_SPACE,
        "settings_geometry": SOURCE_COORDINATE_SPACE,
        "tuning_distances": SOURCE_COORDINATE_SPACE,
        "page_sections": SOURCE_COORDINATE_SPACE,
    }
