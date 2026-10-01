from __future__ import annotations

"""Runtime bridge from final Layout rows to canonical Entry classification."""

from typing import Any

from .entry_classification import (
    classified_entry_crop_height,
    copy_layout_line_classification,
    get_entry_classification,
)


def _install_marker_ocr_crop(processing_module: Any) -> None:
    """Make existing-marker OCR consume the same regular/oversized classification."""
    core = processing_module._core
    if getattr(core, "_entry_classification_crop_installed", False):
        return

    def classified_marker_crop(canonical, entry, geometry, settings):
        canonical_width, canonical_height = canonical.size
        character_height = max(4, int(round(float(getattr(settings, "character_height", 1) or 1))))
        row_padding = max(0, int(round(float(getattr(settings, "row_padding", 0) or 0))))

        # Entry coordinates are source-space; crop geometry is canonical-space.
        _marker_u, marker_v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        try:
            column = int(core.column_index(int(entry.x), geometry, int(entry.y)))
        except Exception:
            column = 0
        column = max(0, min(column, max(0, len(geometry.column_starts) - 1)))
        tracked_x = int(geometry.x_at(column, int(marker_v)))
        column_width = (
            max(1, int(geometry.column_widths[column]))
            if 0 <= column < len(geometry.column_widths)
            else max(1, canonical_width - tracked_x)
        )
        left_pad = max(2, round(character_height * 0.12))
        crop_left = max(0, tracked_x - left_pad)

        meta = get_entry_classification(entry)
        is_large = meta.entry_scale == "oversized"
        regular_height = max(
            character_height + 2 * row_padding,
            round(character_height * 1.20),
        )
        crop_height = classified_entry_crop_height(
            entry,
            settings,
            regular_height=regular_height,
            oversized_height=0,
        )

        if is_large:
            # Keep a display-head crop narrow so pinyin/definition text does not
            # overwhelm single-character recognition. Height comes from the
            # shared classification, preferably the detector's observed box.
            crop_width = min(
                column_width,
                max(round(crop_height * 1.75), round(character_height * 2.6), 72),
            )
            crop_top = max(0, int(marker_v) - max(1, round(character_height * 0.06)))
        else:
            # Ordinary/bracket/indent entry: enough right context for structural
            # parsers, but never the full definition line.
            crop_width = min(
                column_width,
                max(round(character_height * 9.0), round(column_width * 0.45), 120),
            )
            crop_top = max(0, int(marker_v) - row_padding)

        crop_right = min(canonical_width, crop_left + max(24, int(crop_width)))
        crop_bottom = min(canonical_height, max(crop_top + 2, crop_top + int(crop_height)))
        return core.normalize_page_rgb(
            canonical.crop((crop_left, crop_top, crop_right, crop_bottom))
        ), bool(is_large)

    core._ordinary_marker_local_crop = classified_marker_crop
    # Expose the same helper through the processing facade for diagnostics/tests.
    processing_module._ordinary_marker_local_crop = classified_marker_crop
    core._entry_classification_crop_installed = True


def install_processing_entry_classification(processing_module: Any) -> None:
    """Retain row source/scale and share it with marker-based OCR cropping."""
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
    _install_marker_ocr_crop(processing_module)
    processing_module._entry_classification_runtime_installed = True


__all__ = ["install_processing_entry_classification"]
