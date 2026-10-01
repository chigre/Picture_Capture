from __future__ import annotations

"""Make final Layout roles authoritative for ordinary drawing.

Ordinary drawing has one primary source of truth: the final Page Understanding
``LayoutLine.role`` assignment. Historical VB detection is isolated here as a
true emergency fallback and is never fused back into a usable Layout result.

A usable Layout means Page Understanding returned at least one column. Once
that happens, ordinary drawing obeys its row roles exactly:
* ``entry`` rows create markers;
* every non-entry row creates no marker;
* zero entry rows means zero ordinary markers, not a VB retry.

``physical_reliable`` is intentionally *not* a routing gate here. It is a
quality diagnostic for layout inference, not permission for VB to overwrite an
already materialized row-role assignment.

When the main-window Layout visualization has already inferred the current page,
ordinary drawing reuses that exact PageUnderstanding object when it runs in the
same process. Batch/spawn workers recompute the same Page Understanding from the
same settings and page sections.

PaddleOCR and combined modes are intentionally untouched.
"""

from dataclasses import fields, replace
from pathlib import Path
from typing import Any, Callable
import weakref

from PIL import Image

from .image_utils import build_analysis_image
from .models import AppSettings, Entry
from .page_sections import PageSection
from .page_understanding import PageUnderstanding


_VISUALIZED_UNDERSTANDING: dict[
    tuple[int, int, tuple[Any, ...], tuple[Any, ...]],
    tuple[weakref.ReferenceType[Any] | None, PageUnderstanding],
] = {}


def _settings_signature(settings: AppSettings) -> tuple[Any, ...]:
    try:
        return tuple(
            (item.name, repr(getattr(settings, item.name, None)))
            for item in fields(settings)
        )
    except (TypeError, AttributeError):
        return (repr(settings),)


def _sections_signature(
    page_sections: list[PageSection] | None,
) -> tuple[Any, ...]:
    return tuple(repr(section) for section in list(page_sections or []))


def _snapshot_key(
    image: Image.Image,
    settings: AppSettings,
    page_index: int,
    page_sections: list[PageSection] | None,
) -> tuple[int, int, tuple[Any, ...], tuple[Any, ...]]:
    return (
        id(image),
        int(page_index),
        _settings_signature(settings),
        _sections_signature(page_sections),
    )


def remember_visualized_understanding(
    image: Image.Image,
    settings: AppSettings,
    page_index: int,
    page_sections: list[PageSection] | None,
    understanding: PageUnderstanding,
) -> None:
    """Remember exactly what the current Layout overlay showed to the user."""
    key = _snapshot_key(image, settings, page_index, page_sections)
    try:
        reference: weakref.ReferenceType[Any] | None = weakref.ref(image)
    except TypeError:
        reference = None
    _VISUALIZED_UNDERSTANDING.clear()
    _VISUALIZED_UNDERSTANDING[key] = (reference, understanding)


def recall_visualized_understanding(
    image: Image.Image,
    settings: AppSettings,
    page_index: int,
    page_sections: list[PageSection] | None,
) -> PageUnderstanding | None:
    """Return the exact visible Layout result only when every input still matches."""
    key = _snapshot_key(image, settings, page_index, page_sections)
    cached = _VISUALIZED_UNDERSTANDING.get(key)
    if cached is None:
        return None
    reference, understanding = cached
    if reference is not None and reference() is not image:
        _VISUALIZED_UNDERSTANDING.pop(key, None)
        return None
    return understanding


def layout_role_entries(understanding: PageUnderstanding) -> list[Entry]:
    """Convert only final ``role=entry`` rows into ordinary draw markers."""
    layout = understanding.layout
    result: list[Entry] = []

    for column in list(getattr(layout, "columns", []) or []):
        for line in list(getattr(column, "lines", []) or []):
            if str(getattr(line, "role", "") or "") != "entry":
                continue
            canonical_y = int(layout.body_top) + int(line.y0)
            source_x, source_y = layout.transform.canonical_to_source_point(
                int(column.left),
                canonical_y,
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
    *,
    profile_page_index: int,
    page_sections: list[PageSection] | None,
) -> tuple[list[Entry], Any]:
    """Run historical VB only when Page Understanding produced no usable Layout."""
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
    """Build ordinary routing without changing OCR/combined behavior."""

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

        understanding = recall_visualized_understanding(
            image,
            effective,
            profile_page_index,
            page_sections,
        )

        analysis_image = build_analysis_image(source, effective)
        if understanding is None:
            try:
                understanding = processing_module.understand_page(
                    analysis_image,
                    effective,
                    page_index=profile_page_index,
                    page_sections=page_sections,
                )
            except Exception:
                understanding = None

        # Layout roles are authoritative whenever Page Understanding produced
        # real columns. Do not gate this on physical_reliable and do not fall
        # back to VB merely because the correct result contains zero entries.
        if (
            understanding is not None
            and list(getattr(understanding.layout, "columns", []) or [])
        ):
            geometry = processing_module._geometry_from_page_understanding(
                understanding
            )
            layout_primary = layout_role_entries(understanding)
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
