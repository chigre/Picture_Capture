"""Profile-to-source-pixel geometry runtime resolver.

Historical processing_core entrypoints supply the live callbacks and preserve
serializable model identity, pixel coordinates and output file contracts.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from PIL import Image
    from ..models import AppSettings
    from ..processing_core import Geometry


def page_geometry_context(
    image: Image.Image,
    settings: AppSettings,
    profile_page_index: int = 0,
    *, deps: dict[str, Any],
) -> tuple[Image.Image, AppSettings, Image.Image, Geometry]:
    """Resolve one page through the single Profile -> geometry boundary.

    Persisted project geometry remains in reference-page canonical pixels.
    Physical Profile percentages are resolved against this source page, and
    page-edge exclusions are applied only to a disposable analysis copy.
    Every downstream consumer can therefore share the same runtime geometry
    while crops/PDIC/PPP continue to use untouched source pixels.
    """
    normalize_page_rgb = deps["normalize_page_rgb"]
    effective_page_settings = deps["effective_page_settings"]
    page_template_analysis_image = deps["page_template_analysis_image"]
    derive_geometry = deps["derive_geometry"]
    source = normalize_page_rgb(image)
    effective = effective_page_settings(settings, source.size, profile_page_index)
    analysis_source = page_template_analysis_image(
        source, effective, profile_page_index,
    )
    geometry = derive_geometry(analysis_source, effective)
    return source, effective, analysis_source, geometry
