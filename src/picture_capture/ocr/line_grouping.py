from __future__ import annotations

"""Paddle OCR visual line clustering and logical line composition.

The public/core historical module owns callable entrypoints and live patch
hooks; the models continue to have their original persisted __module__ values.
"""

from collections.abc import Callable
from typing import Any
import numpy as np
from .headword_models import OCRRecord, OCRLine


def vertical_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    top = max(a[1], b[1])
    bottom = min(a[3], b[3])
    overlap = max(0, bottom - top)
    minimum = max(1, min(a[3] - a[1], b[3] - b[1]))
    return overlap / minimum


def group_ocr_records(
    records: list[OCRRecord],
    y_ratio: float = 0.55,
    *,
    overlap_fn: Callable[[tuple[int, int, int, int], tuple[int, int, int, int]], float] = vertical_overlap,
    line_type: type[OCRLine] = OCRLine,
    np_module: Any = np,
) -> list[OCRLine]:
    """Merge OCR fragments that belong to the same printed line.

    Paddle normally returns a whole text line, but mixed bold/italic dictionary
    typography can split ``lemma`` and ``(plural) POS`` into adjacent boxes.
    Merging them before parsing lets grammatical labels become a strong cue.
    """
    usable = [record for record in records if record.text]
    if not usable:
        return []
    heights = np_module.asarray([max(1, record.box[3] - record.box[1]) for record in usable], dtype=float)
    median_height = max(1.0, float(np_module.median(heights)))
    center_tolerance = max(2.0, median_height * max(0.1, y_ratio))

    clusters: list[list[OCRRecord]] = []
    cluster_boxes: list[tuple[int, int, int, int]] = []
    for record in sorted(usable, key=lambda item: ((item.box[1] + item.box[3]) / 2.0, item.box[0])):
        cy = (record.box[1] + record.box[3]) / 2.0
        best_index: int | None = None
        best_distance = float("inf")
        # Only nearby recent clusters are plausible; dictionary lines do not
        # interleave vertically.
        for index in range(max(0, len(clusters) - 3), len(clusters)):
            box = cluster_boxes[index]
            cluster_cy = (box[1] + box[3]) / 2.0
            distance = abs(cy - cluster_cy)
            if distance <= center_tolerance or overlap_fn(record.box, box) >= 0.72:
                if distance < best_distance:
                    best_index = index
                    best_distance = distance
        if best_index is None:
            clusters.append([record])
            cluster_boxes.append(record.box)
            continue
        clusters[best_index].append(record)
        x0, y0, x1, y1 = cluster_boxes[best_index]
        rx0, ry0, rx1, ry1 = record.box
        cluster_boxes[best_index] = (min(x0, rx0), min(y0, ry0), max(x1, rx1), max(y1, ry1))

    lines: list[OCRLine] = []
    for members, box in zip(clusters, cluster_boxes):
        members = sorted(members, key=lambda item: item.box[0])
        text = " ".join(member.text.strip() for member in members if member.text.strip()).strip()
        weights = [max(1, len(member.text.strip())) for member in members]
        confidence = float(np_module.average([member.confidence for member in members], weights=weights))
        lines.append(line_type(text=text, confidence=confidence, box=box, records=members))
    return sorted(lines, key=lambda item: (item.box[1], item.box[0]))



def merge_ocr_lines(
    lines: list[OCRLine], *,
    line_type: type[OCRLine] = OCRLine,
    np_module: Any = np,
) -> OCRLine:
    members = sorted(
        [record for line in lines for record in line.records],
        key=lambda item: item.box[0],
    )
    x0 = min(line.box[0] for line in lines); y0 = min(line.box[1] for line in lines)
    x1 = max(line.box[2] for line in lines); y1 = max(line.box[3] for line in lines)
    text = " ".join(record.text.strip() for record in members if record.text.strip()).strip()
    weights = [max(1, len(record.text.strip())) for record in members]
    confidence = float(np_module.average([record.confidence for record in members], weights=weights))
    repairs = tuple(dict.fromkeys(r for line in lines for r in line.logical_repairs))
    return line_type(text=text, confidence=confidence, box=(x0, y0, x1, y1), records=members, logical_repairs=repairs)

