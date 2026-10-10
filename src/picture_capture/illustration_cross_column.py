"""Reconcile per-column illustration detections against full-page ink components.

A spanning illustration can be cut at the column crop boundary, leaving two
boxes whose edges are not both close to the *right* column start.  Only a
component supported on both sides of the actual gutter can fuse those boxes.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


def spanning_figure_boxes(image, column_spans, boxes, *, gray_threshold=170, width_limit=1040):
    """Return reconciled boxes and indices of fused original candidates.

    The analysis is performed in whole-page coordinates, so the gutter itself
    is visible. Only sufficiently large components crossing a real pair of
    adjacent columns and overlapping a candidate from *each* column qualify.
    """
    if len(column_spans) < 2 or len(boxes) < 2:
        return list(boxes), set()
    scale = min(1.0, width_limit / max(1, image.width))
    small = image.convert("L")
    if scale < 1.0:
        resized = small.resize((max(1, round(image.width * scale)),
                                max(1, round(image.height * scale))), Image.Resampling.BILINEAR)
        small.close()
        small = resized
    try:
        dark = np.asarray(small, dtype=np.uint8) < int(gray_threshold)
        mask = Image.fromarray((dark * 255).astype(np.uint8), mode="L")
        try:
            joined = np.asarray(mask.filter(ImageFilter.MaxFilter(3)), dtype=np.uint8) > 0
        finally:
            mask.close()
    finally:
        small.close()

    # Late import avoids a cyclic dependency with illustration_detection.
    from .illustration_detection import _rle_components
    comps = _rle_components(joined)
    output = list(boxes)
    consumed = set()
    for left_span, right_span in zip(column_spans, column_spans[1:]):
        left_end, right_start = left_span[1], right_span[0]
        seam_mid = (left_end + right_start) / 2
        for cx0, cy0, cx1, cy1, pixels in comps:
            a, b, c, d = (round(value / scale) for value in (cx0, cy0, cx1, cy1))
            bw, bh = c - a, d - b
            if (not (a < left_end and c > right_start)
                    or bw < min(left_span[1] - left_span[0], right_span[1] - right_span[0]) * .50
                    or bh < 20 or pixels < 60):
                continue
            left_matches, right_matches = [], []
            for i, box in enumerate(boxes):
                if i in consumed:
                    continue
                bx0, by0, bx1, by1 = box
                overlap_w = max(0, min(c, bx1) - max(a, bx0))
                overlap_h = max(0, min(d, by1) - max(b, by0))
                share = (overlap_w * overlap_h) / max(1, (bx1 - bx0) * (by1 - by0))
                if share < .30:
                    continue
                center = (bx0 + bx1) / 2
                if center < seam_mid:
                    left_matches.append(i)
                else:
                    right_matches.append(i)
            if not left_matches or not right_matches:
                continue
            selected = left_matches + right_matches
            # Do not join unrelated nearby figures: a spanning ink component
            # must substantially occupy every matched box.
            if len(selected) > 4:
                continue
            fused = (
                min([a] + [boxes[i][0] for i in selected]),
                min([b] + [boxes[i][1] for i in selected]),
                max([c] + [boxes[i][2] for i in selected]),
                max([d] + [boxes[i][3] for i in selected]),
            )
            for i in selected:
                consumed.add(i)
            output.append(fused)
    return [box for i, box in enumerate(output) if i >= len(boxes) or i not in consumed], consumed
