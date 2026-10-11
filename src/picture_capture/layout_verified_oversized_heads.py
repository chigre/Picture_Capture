"""Independently verify tall, row-front CJK heads on anomalous Layout pages.

Only columns already confirmed to have repeated ink-vs-indent contradictions
are inspected. The detector uses an actual connected black glyph (not the
indent role of a split physical row) and corrects both missing top boundaries
and repeated starts *inside the same glyph*. Normal columns never run it.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageFilter

from . import dictionary_page_design as base
from .entry_classification import register_layout_line_classification
from .illustration_detection import _rle_components
from .models import Entry


def recover_verified_oversized_heads(
    image: Image.Image, layout: Any, repaired_indices: Iterable[int],
) -> dict[str, int]:
    stats = {"verified_glyphs": 0, "promoted_heads": 0, "demoted_fragments": 0}
    selected = set(map(int, repaired_indices))
    if not selected:
        return stats

    reference = max(8.0, float(getattr(layout, "ordinary_line_height", 1.0)))
    canonical = layout.transform.canonical_image_for_analysis(image.convert("RGB"))
    try:
        gray = canonical.convert("L")
        try:
            top = max(0, int(getattr(layout, "body_top", 0)))
            bottom = min(gray.height, int(getattr(layout, "body_bottom", gray.height)))
            for index in sorted(selected):
                if index < 0 or index >= len(layout.columns):
                    continue
                column = layout.columns[index]
                left = max(0, int(column.left) - round(reference * .20))
                right = min(gray.width, int(column.right),
                            int(column.left) + max(110, round(reference * 5.5)))
                if right <= left or bottom <= top:
                    continue
                binary = (np.asarray(
                    gray.crop((left, top, right, bottom)), dtype=np.uint8
                ) < 170).astype(np.uint8)
                linked = Image.fromarray(binary * 255, "L")
                try:
                    dilated = np.asarray(
                        linked.filter(ImageFilter.MaxFilter(3)), dtype=np.uint8
                    ) > 0
                finally:
                    linked.close()
                glyphs = []
                for x0, y0, x1, y1, area in _rle_components(dilated):
                    width, height = x1 - x0, y1 - y0
                    if not (
                        1.60 * reference <= width <= 3.30 * reference
                        and 1.65 * reference <= height <= 3.70 * reference
                        and .62 <= height / max(1, width) <= 1.75
                        and area >= .25 * width * height
                        and left + x0 <= int(column.left) + .55 * reference
                    ):
                        continue
                    glyphs.append((int(left + x0), int(top + y0),
                                   int(width), int(height)))
                # Multiple confirmed physical glyphs, rather than one
                # illustration fragment, are required to alter Layout.
                if len(glyphs) < 3:
                    continue
                for glyph_x, glyph_y, glyph_width, glyph_height in sorted(
                    glyphs, key=lambda item: item[1]
                ):
                    stats["verified_glyphs"] += 1
                    allowable_top_delta = max(5.0, reference * .24)
                    earliest = [
                        line for line in column.lines
                        if abs(
                            (top + int(line.y0)) - glyph_y
                        ) <= allowable_top_delta
                    ]
                    # A 2-3-line display head must have ONE separator, not
                    # a second start through the middle of its ideograph.
                    for line in column.lines:
                        row_y = top + int(line.y0)
                        if (
                            str(line.role) == "entry"
                            and glyph_y - reference * .52 <= row_y
                            < glyph_y + glyph_height - reference * .12
                            and abs(row_y - glyph_y) > allowable_top_delta
                        ):
                            line.role = "body"
                            stats["demoted_fragments"] += 1

                    if earliest:
                        head = min(earliest, key=lambda line: abs(
                            top + int(line.y0) - glyph_y
                        ))
                        if str(head.role) != "entry":
                            stats["promoted_heads"] += 1
                        head.role = "entry"
                    else:
                        boundary = max(top, glyph_y - max(1, round(reference * .08)))
                        local = boundary - top
                        head = base.LayoutLine(
                            column=index, y0=local,
                            y1=local + max(1, round(reference)),
                            first_x=max(0, glyph_x - int(column.left)),
                            anchor_x=max(0, glyph_x - int(column.left)),
                            anchor_width=glyph_width, anchor_height=glyph_height,
                            gap_before=0, patch=np.zeros((0, 0), dtype=bool),
                            role="entry",
                        )
                        column.lines.append(head)
                        stats["promoted_heads"] += 1
                    sx, sy = layout.transform.canonical_to_source_point(
                        int(column.left), glyph_y, layout.source_size,
                    )
                    register_layout_line_classification(head, Entry(
                        word="", x=int(sx), y=int(sy),
                        ocr_source="ordinary_large_head_evidence",
                        issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
                        ocr_visual_run_height=float(glyph_height),
                        ocr_line_height_reference=reference,
                        ocr_oversized_cjk=True,
                        ocr_single_cjk=True,
                    ))
                column.lines.sort(key=lambda line: (line.y0, line.y1))
        finally:
            gray.close()
    finally:
        canonical.close()
    return stats


__all__ = ["recover_verified_oversized_heads"]
