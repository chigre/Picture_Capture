from __future__ import annotations

"""Make final Layout roles authoritative for ordinary drawing.

Ordinary drawing has one primary source of truth: the final Page Understanding
``LayoutLine.role`` assignment.  Historical VB detection is isolated here as a
fallback and is never fused back into a successful layout-role result.

PaddleOCR and combined modes are intentionally untouched.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from . import dictionary_page_design as page_design
from .image_utils import build_analysis_image
from .models import AppSettings, Entry
from .page_sections import PageSection
from .page_understanding import PageUnderstanding


def layout_role_entries(understanding: PageUnderstanding) -> list[Entry]:
    """Convert final ``role=entry`` rows directly into ordinary draw markers."""
    layout = understanding.layout
    reference = max(1.0, float(understanding.line_height))
    result: list[Entry] = []

    for column in list(getattr(layout, "columns", []) or []):
        lines = list(getattr(column, "lines", []) or [])
        for line in lines:
            if str(getattr(line, "role", "") or "") != "entry":
                continue
            boundary_local = int(page_design._boundary_before(
                lines,
                int(line.y0),
                reference,
            ))
            source_x, source_y = layout.transform.canonical_to_source_point(
                int(column.left),
                int(layout.body_top) + boundary_local,
                layout.source_size,
            )
            result.append(Entry(
                word="",
                x=int(source_x),
                y=int(source_y),
                confidence=None,
                ocr_source="page_understanding:ordinary_layout_role",
                issue_type="PAGE_UNDERSTANDING_ORDINARY_LAYOUT_ROLE",
            ))
    return result


def _vb_fallback(
    processing_module: Any,
    analysis_image: Image.Image,
    source: Image.Image,
    settings: AppSettings,
    effective: AppSettings,
    understanding: PageUnderstanding | None,
    *,
    profile_page_index: int,
    page_sections: list[PageSection] | None,
) -> tuple[list[Entry], Any]:
    """Run historical VB only when authoritative layout roles are unavailable."""
    if (
        understanding is not None
        and understanding.physical_reliable
        and understanding.layout.columns
    ):
        geometry = processing_module._geometry_from_page_understanding(understanding)
        vb_settings = processing_module._ordinary_settings_for_shared_geometry(
            effective,
            geometry,
            method="left_edge",
        )
        vb_image = processing_module._page_template_image(
            analysis_image,
            vb_settings,
            profile_page_index,
        )
    else:
        vb_settings = replace(effective)
        vb_settings.detection_method = "left_edge"
        vb_image = processing_module._page_template_image(
            analysis_image,
            vb_settings,
            profile_page_index,
        )

    entries, geometry = processing_module._original_detect_entries_left_edge(
        vb_image,
        vb_settings,
        page_sections=page_sections,
    )
    entries = processing_module._allowed_entries(
        list(entries),
        source,
        settings,
        geometry,
        profile_page_index,
        page_sections,
    )
    return processing_module._core.sort_entries_reading_order(
        entries,
        geometry,
        page_sections,
    ), geometry


def build_ordinary_layout_primary(
    processing_module: Any,
    original_detect_entries: Callable[..., tuple[list[Entry], Any]],
) -> Callable[..., tuple[list[Entry], Any]]:
    """Build the ordinary routing rule without changing OCR/combined behavior."""

    def detect_entries(
        image: Image.Image,
        settings: AppSettings,
        paddle_cache_path: Path | None = None,
        force_paddle_refresh: bool = False,
        paddle_filter_rules_path: Path | None = None,
        profile_page_index: int = 0,
        page_sections: list[PageSection] | None = None,
    ) -> tuple[list[Entry], Any]:
        source = processing_module._core.normalize_page_rgb(image)
        effective = processing_module._core.effective_page_settings(
            settings,
            source.size,
            profile_page_index,
        )
        method = str(
            getattr(effective, "detection_method", "") or ""
        ).strip().lower()

        # OCR and combined have their own evidence-fusion contracts.  This
        # change is deliberately limited to the user-facing ordinary mode.
        if method in {"paddleocr", "combined"}:
            return original_detect_entries(
                image,
                settings,
                paddle_cache_path=paddle_cache_path,
                force_paddle_refresh=force_paddle_refresh,
                paddle_filter_rules_path=paddle_filter_rules_path,
                profile_page_index=profile_page_index,
                page_sections=page_sections,
            )

        analysis_image = build_analysis_image(source, effective)
        understanding: PageUnderstanding | None
        try:
            understanding = processing_module.understand_page(
                analysis_image,
                effective,
                page_index=profile_page_index,
                page_sections=page_sections,
            )
        except Exception:
            understanding = None

        if (
            understanding is not None
            and understanding.physical_reliable
            and understanding.layout.columns
        ):
            # Presence of any final entry role makes Layout authoritative.  Do
            # not run VB afterward, even if template/section filtering removes
            # every marker; those exclusions are intentional display geometry.
            layout_primary = layout_role_entries(understanding)
            if layout_primary:
                geometry = processing_module._geometry_from_page_understanding(
                    understanding
                )
                entries = processing_module._allowed_entries(
                    layout_primary,
                    source,
                    settings,
                    geometry,
                    profile_page_index,
                    page_sections,
                )
                return processing_module._core.sort_entries_reading_order(
                    entries,
                    geometry,
                    page_sections,
                ), geometry

        return _vb_fallback(
            processing_module,
            analysis_image,
            source,
            settings,
            effective,
            understanding,
            profile_page_index=profile_page_index,
            page_sections=page_sections,
        )

    return detect_entries


def install_ordinary_layout_primary() -> None:
    """Install Layout-first ordinary routing exactly once."""
    from . import processing

    if getattr(processing, "_ordinary_layout_primary_installed", False):
        return

    processing.detect_entries = build_ordinary_layout_primary(
        processing,
        processing.detect_entries,
    )
    processing._ordinary_layout_primary_installed = True
