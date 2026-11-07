from __future__ import annotations

"""OCR source-band to canonical coordinates; preserve metadata and model identity.

This is an in-memory coordinate projection only. The source OCR pixels,
persisted raw detections, and OCRRecord legacy pickle path remain unchanged.
"""

from collections.abc import Callable
from typing import Any
from ..geometry.layout_transform import LayoutTransform
from .headword_models import OCRRecord


def records_to_canonical_band(
    records: list[OCRRecord],
    source_band_size: tuple[int, int],
    transform_kind: str,
    *,
    transform_cls: Callable[[str], Any] = LayoutTransform,
    record_cls: type[OCRRecord] = OCRRecord,
) -> list[OCRRecord]:
    """Map OCR boxes to analysis space without transforming OCR input pixels."""
    transform = transform_cls(transform_kind)
    return [
        record_cls(
            record.text,
            record.confidence,
            transform.source_box_to_canonical(
                record.box, source_band_size
            ),
            recovery=record.recovery,
            recovery_source_text=record.recovery_source_text,
            parent_box=(
                transform.source_box_to_canonical(
                    record.parent_box, source_band_size
                )
                if record.parent_box is not None else None
            ),
        )
        for record in records
    ]
