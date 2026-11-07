"""Profile-aware ordinary / OCR / combined marker dispatch with source-coordinate filtering.

Core implementation is delegated here, with live historical collaborators
injected at invocation and with persisted classes remaining in their owners.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import Entry, AppSettings
    from ..processing_core import Geometry
    from ..persistence.page_sections import PageSection


def detect_entries_impl(
    image: Image.Image,
    settings: AppSettings,
    paddle_cache_path: Path | None = None,
    force_paddle_refresh: bool = False,
    paddle_filter_rules_path: Path | None = None,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
    left_edge_detector: Any | None = None,
    *, deps: dict[str, Any],
) -> tuple[list[Entry], Geometry]:
    """Detect markers with the active Project Profile page template applied."""
    _detect_entries_left_edge = deps["_detect_entries_left_edge"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    effective_page_settings = deps["effective_page_settings"]
    page_template_analysis_image = deps["page_template_analysis_image"]
    derive_geometry = deps["derive_geometry"]
    ordinary_page_layout_settings = deps["ordinary_page_layout_settings"]
    _fuse_detection_entries = deps["_fuse_detection_entries"]
    entry_allowed_by_page_template = deps["entry_allowed_by_page_template"]
    v_is_inside_sections = deps["v_is_inside_sections"]
    sort_entries_reading_order = deps["sort_entries_reading_order"]
    json = deps["json"]
    detect_left_edge = left_edge_detector or _detect_entries_left_edge
    source = normalize_page_rgb(image)
    effective = effective_page_settings(settings, source.size, profile_page_index)
    analysis_source = page_template_analysis_image(source, effective, profile_page_index)
    method = effective.detection_method.strip().lower()
    if method in {"paddleocr", "combined"}:
        geometry = derive_geometry(analysis_source, effective)
        from ..paddle_headwords import detect_paddle_headwords
        ocr_entries = detect_paddle_headwords(
            analysis_source, geometry, effective,
            cache_path=paddle_cache_path,
            force_refresh=force_paddle_refresh,
            filter_rules_path=paddle_filter_rules_path,
            page_sections=page_sections,
        )
        if method == "combined":
            # Run the restored ordinary detector unchanged, including its
            # page-specific auto-layout and VB separator chain.  The OCR path
            # likewise keeps its own existing geometry/parser/refinement logic;
            # only their final entry observations are fused.
            ordinary_effective, _applied_layout = ordinary_page_layout_settings(
                analysis_source, effective
            )
            ordinary_entries, _ordinary_geometry = detect_left_edge(
                analysis_source, ordinary_effective, page_sections=page_sections
            )
            review_candidates: list[dict] = []
            if paddle_cache_path is not None and paddle_cache_path.exists():
                try:
                    cached_payload = json.loads(
                        paddle_cache_path.read_text(encoding="utf-8")
                    )
                    if isinstance(cached_payload, dict):
                        review_candidates = [
                            item for item in list(
                                cached_payload.get("review_candidates") or []
                            )
                            if isinstance(item, dict)
                        ]
                except (OSError, ValueError, TypeError):
                    review_candidates = []
            entries = _fuse_detection_entries(
                ordinary_entries, ocr_entries, geometry, effective, page_sections,
                review_candidates=review_candidates,
                image=analysis_source,
            )
        else:
            entries = ocr_entries
    else:
        ordinary_effective, _applied_layout = ordinary_page_layout_settings(
            analysis_source, effective
        )
        entries, geometry = detect_left_edge(
            analysis_source, ordinary_effective, page_sections=page_sections
        )

    entries = [
        entry for entry in entries
        if entry_allowed_by_page_template(
            entry.x, entry.y, source.size, effective, profile_page_index,
        )
        and (
            not page_sections
            or v_is_inside_sections(
                geometry.source_to_canonical(entry.x, entry.y)[1],
                page_sections, geometry.top, geometry.bottom,
            )
        )
    ]
    return sort_entries_reading_order(entries, geometry, page_sections), geometry
