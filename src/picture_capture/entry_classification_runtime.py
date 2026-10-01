from __future__ import annotations

"""Runtime bridge from final Layout rows to canonical Entry classification."""

from typing import Any

from .entry_classification import copy_layout_line_classification


def install_processing_entry_classification(processing_module: Any) -> None:
    """Retain row source/scale when ordinary Layout roles become Entry objects."""
    if getattr(processing_module, "_entry_classification_runtime_installed", False):
        return

    original = processing_module._ordinary_entries_from_layout_roles

    def materialize(understanding, image=None, *, page_index: int = 0):
        entries = original(
            understanding,
            image,
            page_index=page_index,
        )
        lines = [
            line
            for column in list(getattr(understanding.layout, "columns", []) or [])
            for line in list(getattr(column, "lines", []) or [])
            if str(getattr(line, "role", "") or "") == "entry"
        ]
        # The original materializer emits one Entry for each final entry line in
        # exactly this column/row order.  Classification is metadata only and
        # therefore must never add/remove/reorder separators.
        for line, entry in zip(lines, entries):
            meta = copy_layout_line_classification(line, entry)
            if meta.entry_scale == "oversized":
                # Preserve compatibility with existing OCR/review diagnostics
                # while the canonical classification API becomes authoritative.
                entry.ocr_oversized_cjk = True
                entry.ocr_single_cjk = True
                if meta.detected_head_height > 0:
                    entry.ocr_visual_run_height = float(meta.detected_head_height)
                    entry.ocr_line_height_reference = float(
                        getattr(understanding.layout, "ordinary_line_height", 0.0) or 0.0
                    )
        return entries

    processing_module._ordinary_entries_from_layout_roles = materialize
    processing_module._entry_classification_runtime_installed = True


__all__ = ["install_processing_entry_classification"]
