from __future__ import annotations

"""Canonical crop geometry for OCR of already-established entry boundaries.

The separator supplies only the entry Y. Horizontal bounds come from resolved
column geometry; vertical extent comes from shared entry classification plus the
physical Layout row metrics. OCR engine choice must never alter this crop box.
"""

from dataclasses import dataclass
from typing import Any

from .entry_classification import get_entry_classification
from .models import AppSettings, Entry


@dataclass(frozen=True, slots=True)
class EntryOcrRowMetrics:
    """Physical ordinary-row measurements used by OCR/review cropping."""

    line_height: float
    line_pitch: float

    @property
    def row_gap(self) -> float:
        return max(0.0, float(self.line_pitch) - float(self.line_height))


def _fallback_row_metrics(settings: AppSettings) -> EntryOcrRowMetrics:
    line_height = max(
        1.0, float(getattr(settings, "character_height", 1) or 1)
    )
    legacy_gap = max(0.0, float(getattr(settings, "row_padding", 0) or 0))
    return EntryOcrRowMetrics(
        line_height=line_height,
        line_pitch=line_height + legacy_gap,
    )


def resolve_entry_ocr_row_metrics(
    image: Any,
    settings: AppSettings,
    *,
    page_index: int = 0,
) -> EntryOcrRowMetrics:
    """Resolve one page's physical line height/pitch from cached Layout Core.

    ``row_padding`` is only a legacy fallback. The real OCR row gap is the
    observed physical ``ordinary_line_pitch - ordinary_line_height``.
    """
    fallback = _fallback_row_metrics(settings)
    analysis = None
    try:
        from .image_utils import build_analysis_image
        from .layout_core_understanding import understand_layout_core

        analysis = build_analysis_image(image, settings)
        understanding = understand_layout_core(
            analysis,
            settings,
            page_index=max(0, int(page_index)),
        )
        layout = understanding.layout
        line_height = max(
            1.0, float(getattr(layout, "ordinary_line_height", 0.0) or 0.0)
        )
        line_pitch = max(
            line_height,
            float(getattr(layout, "ordinary_line_pitch", 0.0) or 0.0),
        )
        return EntryOcrRowMetrics(
            line_height=line_height,
            line_pitch=line_pitch,
        )
    except Exception:
        return fallback
    finally:
        if analysis is not None:
            try:
                analysis.close()
            except Exception:
                pass


def _column_at_entry(entry: Entry, geometry: Any) -> tuple[int, int]:
    u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
    starts = list(getattr(geometry, "column_starts", []) or [])
    widths = list(getattr(geometry, "column_widths", []) or [])
    if not starts:
        return 0, int(v)
    candidates: list[tuple[float, int]] = []
    for index, _start in enumerate(starts):
        left = int(geometry.x_at(index, int(v)))
        width = max(1, int(widths[index])) if index < len(widths) else 1
        right = left + width
        if left <= int(u) <= right:
            distance = 0.0
        else:
            distance = float(min(abs(int(u) - left), abs(int(u) - right)))
        candidates.append((distance, index))
    return min(candidates, key=lambda item: (item[0], item[1]))[1], int(v)


def _local_gutter(
    geometry: Any,
    column: int,
    marker_v: int,
    settings: AppSettings,
) -> int:
    starts = list(getattr(geometry, "column_starts", []) or [])
    widths = list(getattr(geometry, "column_widths", []) or [])
    if not starts or not (0 <= column < len(starts)):
        return max(0, int(getattr(settings, "gutter", 0) or 0))
    left = int(geometry.x_at(column, marker_v))
    width = max(1, int(widths[column])) if column < len(widths) else 1
    if column + 1 < len(starts):
        next_left = int(geometry.x_at(column + 1, marker_v))
        return max(0, next_left - (left + width))
    if column > 0:
        previous_left = int(geometry.x_at(column - 1, marker_v))
        previous_width = (
            max(1, int(widths[column - 1]))
            if column - 1 < len(widths)
            else 1
        )
        return max(0, left - (previous_left + previous_width))
    return max(0, int(getattr(settings, "gutter", 0) or 0))


def entry_ocr_content_height(
    entry: Entry,
    settings: AppSettings,
    *,
    row_metrics: EntryOcrRowMetrics | None = None,
) -> int:
    """Return entry-content height, excluding surrounding row-gap margins.

    The detected physical regular line height is a hard minimum. Historical
    configured values may enlarge a crop but may never shrink it below what the
    page actually contains.
    """
    meta = get_entry_classification(entry)
    metrics = row_metrics or _fallback_row_metrics(settings)
    physical_regular = max(1, int(round(float(metrics.line_height))))
    regular_configured = max(
        0, int(getattr(settings, "entry_regular_crop_height", 0) or 0)
    )
    regular = max(physical_regular, regular_configured)
    if meta.entry_scale != "oversized":
        return regular

    oversized_configured = max(
        0, int(getattr(settings, "entry_oversized_crop_height", 0) or 0)
    )
    detected = max(
        0, int(round(float(meta.detected_head_height or 0.0)))
    )
    if oversized_configured or detected:
        return max(regular, oversized_configured, detected)
    return max(regular, int(round(regular * 2.5)))


def entry_ocr_row_gap(
    settings: AppSettings,
    *,
    row_metrics: EntryOcrRowMetrics | None = None,
) -> int:
    metrics = row_metrics or _fallback_row_metrics(settings)
    return max(0, int(round(float(metrics.row_gap))))


def entry_ocr_crop_box(
    entry: Entry,
    geometry: Any,
    settings: AppSettings,
    image_size: tuple[int, int],
    *,
    row_metrics: EntryOcrRowMetrics | None = None,
) -> tuple[int, int, int, int]:
    """Return canonical OCR crop box using one project-wide formula.

    left   = column_left - gutter/2
    right  = column_left + column_width * right_ratio + gutter/2
    top    = entry_y - physical_row_gap/2
    bottom = entry_y + classified_content_height + physical_row_gap

    ``right_ratio`` is the same user-visible 【向右比例 %】 used by the existing
    entry box/crop geometry. Paddle's independent ``paddle_band_width_ratio``
    only controls PaddleOCR's own full-column detection band.
    """
    image_width, image_height = map(int, image_size)
    column, marker_v = _column_at_entry(entry, geometry)
    widths = list(getattr(geometry, "column_widths", []) or [])
    left = int(geometry.x_at(column, marker_v)) if widths else 0
    column_width = (
        max(1, int(widths[column]))
        if 0 <= column < len(widths)
        else max(1, image_width - left)
    )
    gutter = _local_gutter(geometry, column, marker_v, settings)
    half_gutter = int(round(gutter * 0.5))
    row_gap = entry_ocr_row_gap(settings, row_metrics=row_metrics)
    gap_before = row_gap // 2
    right_ratio = float(getattr(settings, "right_ratio", 100.0) or 100.0)
    right_ratio = max(5.0, min(200.0, right_ratio)) / 100.0
    height = entry_ocr_content_height(
        entry,
        settings,
        row_metrics=row_metrics,
    )

    crop_left = max(0, left - half_gutter)
    crop_right = min(
        image_width,
        max(
            crop_left + 2,
            int(round(left + column_width * right_ratio + half_gutter)),
        ),
    )
    crop_top = max(0, int(marker_v) - gap_before)
    crop_bottom = min(
        image_height,
        max(
            crop_top + 2,
            int(marker_v) + int(height) + row_gap,
        ),
    )
    return crop_left, crop_top, crop_right, crop_bottom


__all__ = [
    "EntryOcrRowMetrics",
    "entry_ocr_content_height",
    "entry_ocr_crop_box",
    "entry_ocr_row_gap",
    "resolve_entry_ocr_row_metrics",
]
