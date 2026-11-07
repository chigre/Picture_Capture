"""Source file illustration detection and batch PPP update work.

Historical processing_core entrypoints supply the live callbacks and preserve
serializable model identity, pixel coordinates and output file contracts.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from pathlib import Path
    from ..models import AppSettings, PolygonRegion


def detect_illustration_regions_impl(
    image_path: Path,
    settings: AppSettings,
    *,
    analysis_column_width: int = 520,
    profile_page_index: int = 0,
    deps: dict[str, Any],
) -> list[PolygonRegion]:
    """Historical path API backed by the shared in-memory detector."""
    Image = deps["Image"]
    Path = deps["Path"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    detect_illustration_regions_from_image = deps["detect_illustration_regions_from_image"]
    with Image.open(Path(image_path)) as opened:
        image = normalize_page_rgb(opened)
    try:
        return detect_illustration_regions_from_image(
            image,
            settings,
            analysis_column_width=int(analysis_column_width),
            profile_page_index=int(profile_page_index),
        )
    finally:
        image.close()


def detect_illustrations_job_impl(
    image_path: str, settings: AppSettings, profile_page_index: int = 0,
    *, deps: dict[str, Any],
) -> dict[str, int]:
    """Background-safe one-page illustration detector used by the GUI batch runner."""
    Path = deps["Path"]
    detect_illustrations_to_ppp = deps["detect_illustrations_to_ppp"]
    return detect_illustrations_to_ppp(
        Path(image_path), settings, profile_page_index=profile_page_index,
    )
