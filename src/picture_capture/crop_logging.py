from __future__ import annotations

"""Crop and illustration logging helpers."""

from pathlib import Path
from typing import TYPE_CHECKING

from .project_storage import crop_log_path, qt_root

if TYPE_CHECKING:
    from .processing_core import CropRecord, IllustrationCropEvent


def append_crop_log(root: Path, records: list[CropRecord]) -> None:
    """Append crop boxes in original-image pixels with a self-describing header."""
    if not records:
        return
    log = crop_log_path(root)
    needs_header = not log.exists() or log.stat().st_size == 0
    with log.open("a", encoding="utf-8") as handle:
        if needs_header:
            handle.write(
                "# coordinate_space=source_image_pixels; "
                "columns=page,file,source_x,source_y,width,height\n"
            )
        for record in records:
            left, top, right, bottom = record.box
            handle.write(
                f"{record.page}\t{record.filename}\t{left}\t{top}\t"
                f"{right-left}\t{bottom-top}\n"
            )


def append_illustration_crop_log(
    root: Path, events: list[IllustrationCropEvent],
) -> None:
    if not events:
        return
    path = qt_root(root) / "_illustration_crop_log.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(
                f"{event.page}\tPPP{event.polygon_index:03d}\t{event.name}\t"
                f"{event.associated_word}\t{event.relation}\t{event.action}\t"
                f"{event.filename}\n"
            )
