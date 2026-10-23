from __future__ import annotations

"""Source-direction-preserving OCR crops for existing ordinary page markers.

Only produces a detached in-memory crop. Its historical processing_core
entrypoint forwards current normalization, preserving public patch behavior.
No user markers, Entry objects or persisted files are mutated.
"""

from collections.abc import Callable
from typing import Any
from PIL import Image
from ..models import AppSettings, Entry


def ordinary_marker_local_crop(
    canonical: Image.Image,
    entry: Entry,
    geometry: Geometry,
    settings: AppSettings,
    *,
    row_metrics=None,
    source_image: Image.Image | None = None,
    normalize_rgb_fn: Callable[[Image.Image], Image.Image],
) -> tuple[Image.Image, bool]:
    """Crop one marker in the physical direction of the printed text.

    Geometry and the entry's classification are measured in canonical
    coordinates, but a horizontal OCR engine must receive actual source
    glyphs, not a mirror/rotation imposed for Layout analysis. Invert the
    *crop box* into source coordinates; do not inverse-transform recognized
    text, change a marker, or silently reverse CJK strings.
    """
    from ..proofreading.classification import get_entry_classification
    from .entry_crop import entry_ocr_crop_box
    from .entry_visual_scale import visual_oversized_head_height

    metrics_height = (
        float(row_metrics.line_height) if row_metrics is not None
        else float(settings.character_height)
    )
    visual_height = visual_oversized_head_height(
        canonical, entry, geometry, settings, line_height=metrics_height,
    )
    box = entry_ocr_crop_box(
        entry,
        geometry,
        settings,
        canonical.size,
        row_metrics=row_metrics,
        visual_head_height=visual_height,
    )
    meta = get_entry_classification(entry)
    large_for_ocr = meta.entry_scale == "oversized" or visual_height > 0
    horizontal = str(getattr(settings, "layout_writing_mode", "")) == "horizontal-tb"
    if horizontal and source_image is not None:
        source_box = geometry.transform.canonical_box_to_source(
            box, geometry.source_size,
        )
        return (
            normalize_rgb_fn(source_image.crop(source_box)),
            large_for_ocr,
        )
    return normalize_rgb_fn(canonical.crop(box)), large_for_ocr
