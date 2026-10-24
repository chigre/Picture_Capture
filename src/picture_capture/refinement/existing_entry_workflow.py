"""Implementation owner for historical refine_existing_entries workflow.

Core supplies current collaborators per call and preserves public signatures.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from PIL import Image
    from ..models import AppSettings, Entry


def refine_existing_entries_impl(
    image: Image.Image,
    entries: list[Entry],
    settings: AppSettings,
    *,
    profile_page_index: int = 0,
    source_image_path: Path | None = None,
    fixed_half_gutter: bool = False,
    deps: dict[str, Any],
) -> tuple[list[Entry], dict[str, int]]:
    """Refine saved Y while preserving entry identity and text."""
    _page_geometry_context = deps["_page_geometry_context"]
    _refine_existing_entries_with_geometry = deps["_refine_existing_entries_with_geometry"]
    derive_geometry = deps["derive_geometry"]
    if source_image_path is None:
        source, effective, analysis_source, geometry = _page_geometry_context(
            image, settings, profile_page_index,
        )
        return _refine_existing_entries_with_geometry(
            entries, effective, analysis_source, geometry,
        )

    from .analysis import prepare_refinement_analysis

    prep_kwargs = {"fixed_half_gutter": True} if fixed_half_gutter else {}
    source, effective, analysis_source = prepare_refinement_analysis(
        image, settings, profile_page_index, source_image_path=source_image_path,
        **prep_kwargs,
    )
    try:
        geometry = derive_geometry(analysis_source, effective)
        return _refine_existing_entries_with_geometry(
            entries, effective, analysis_source, geometry,
            align_to_ink_top=True, fixed_half_gutter=fixed_half_gutter,
        )
    finally:
        analysis_source.close()
        source.close()
