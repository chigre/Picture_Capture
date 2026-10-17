"""Recover CJK entry starts marked by a *matched pair* of printed 【…】.

The physical layout classifier sometimes misses short numbered subentries.
Unlike text recognition, this evidence uses the distinctive left/right
vertical-ink polarity of both square brackets in the headword lane. A single
bracket, quotation inside a definition, or an unmatched ink component is
insufficient to introduce a separator.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from .models import Entry
from .geometry.visual_boundary_locator import safe_gap_above



def _strict_bracket_components(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """True 8-connected RLE components, without bridging a blank pixel.

    The illustration component finder intentionally joins near-adjacent row
    runs (up to two pixels apart). For tiny printed 【】 glyphs that merges an
    otherwise intact 15px bracket into the nearby Han character. Keep its
    illustration behavior unchanged; bracket recognition needs literal
    8-connectivity (overlap or one-pixel diagonal adjacency) instead.
    """
    ink = np.asarray(mask, dtype=bool)
    if ink.ndim != 2 or not ink.size:
        return []
    height = ink.shape[0]
    parent: list[int] = []
    rank: list[int] = []
    boxes: list[list[int]] = []

    def root(k: int) -> int:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def join(a: int, b: int) -> None:
        a, b = root(a), root(b)
        if a == b:
            return
        if rank[a] < rank[b]:
            a, b = b, a
        parent[b] = a
        if rank[a] == rank[b]:
            rank[a] += 1

    previous: list[tuple[int, int, int]] = []
    for y in range(height):
        changes = np.diff(
            np.r_[False, ink[y], False].astype(np.int8)
        )
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1)
        current: list[tuple[int, int, int]] = []
        start_previous = 0
        for start, end in zip(starts.tolist(), ends.tolist()):
            idx = len(parent)
            parent.append(idx)
            rank.append(0)
            boxes.append([start, y, end, y + 1, end - start])
            # Half-open [start,end) runs are 8-connected when previous.end
            # >= start and previous.start <= end. Adding +/-1 here bridges
            # one entire empty pixel and merges bracket and word strokes.
            while (
                start_previous < len(previous)
                and previous[start_previous][1] < start
            ):
                start_previous += 1
            scan = start_previous
            while scan < len(previous) and previous[scan][0] <= end:
                old_start, old_end, old_idx = previous[scan]
                if old_end >= start:
                    join(idx, old_idx)
                scan += 1
            current.append((start, end, idx))
        previous = current

    merged: dict[int, list[int]] = {}
    for idx, (x0, y0, x1, y1, area) in enumerate(boxes):
        target = merged.setdefault(root(idx), [x0, y0, x1, y1, 0])
        target[0] = min(target[0], x0)
        target[1] = min(target[1], y0)
        target[2] = max(target[2], x1)
        target[3] = max(target[3], y1)
        target[4] += area
    return [tuple(row) for row in merged.values()]


def _bracket_side(mask: np.ndarray, opening: bool) -> bool:
    height, width = mask.shape
    if width < 8 or height < 16:
        return False
    edge = max(2, round(width * .30))
    top = max(2, round(height * .12))
    middle = mask[round(height * .30):round(height * .70)]
    left = mask[:, 1:edge]
    right = mask[:, width - edge:width - 1]
    mid_left = middle[:, 1:edge]
    mid_right = middle[:, width - edge:width - 1]
    if any(part.size == 0 for part in (left, right, mid_left, mid_right)):
        return False
    dense, sparse = (left, right) if opening else (right, left)
    middle_dense, middle_sparse = (
        (mid_left, mid_right) if opening else (mid_right, mid_left)
    )
    return (
        dense.mean() > .55 and sparse.mean() < .38
        and middle_dense.mean() > .60 and middle_sparse.mean() < .27
        and mask[:top].mean() > .35 and mask[-top:].mean() > .35
    )



def _visible_bracket_band(
    ink: np.ndarray,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    opening: bool,
    pitch: float,
) -> bool:
    """Validate bracket strokes within a *narrow* band even if CCs merge.

    An attached Han stroke can merge a bracket into a wide connected component,
    but it does not normally erase its dense vertical side and top/bottom caps.
    Limit searches to the position learned from independent intact pairs.
    """
    w = int(round(width))
    h = int(round(height))
    if w < 8 or h < 16:
        return False
    xcenter = int(round(x))
    ycenter = int(round(y))
    radius_x = max(3, min(8, int(round(pitch * .21))))
    radius_y = max(1, min(3, int(round(pitch * .07))))
    for dy in sorted(range(-radius_y, radius_y + 1), key=lambda v: abs(v)):
        yy = ycenter + dy
        if yy < 0 or yy + h > ink.shape[0]:
            continue
        for dx in sorted(range(-radius_x, radius_x + 1), key=lambda v: abs(v)):
            xx = xcenter + dx
            if xx < 0 or xx + w > ink.shape[1]:
                continue
            if _bracket_side(ink[yy:yy + h, xx:xx + w], opening):
                return True
    return False


def _sticky_pairs_from_printed_template(
    ink: np.ndarray,
    openings: list[tuple[int, int, int, int]],
    closings: list[tuple[int, int, int, int]],
    pairs: list[tuple[tuple[int, int, int, int], tuple[int, int, int, int]]],
    *,
    x_offset: int,
    y_offset: int,
    column_left: int,
    pitch: float,
) -> list[tuple[int, int]]:
    """Recover only matched rows supported by a reliable local bracket grid.

    XDHYCD has numerous pairs with a stable 2-character closing bracket offset.
    Do not assume that layout for other dictionaries or long bracket words.
    A one-sided connected component anchors Y; the other side must still show
    a full directional bracket stroke pattern at the measured location.
    """
    if len(pairs) < 3:
        return []
    distances = np.asarray([int(c[0] - o[0]) for o, c in pairs], dtype=float)
    offset = float(np.median(distances))
    supported = distances[
        np.abs(distances - offset) <= max(5.0, pitch * .30)
    ]
    if supported.size < 3 or supported.size < int(np.ceil(len(pairs) * .65)):
        return []
    offset = float(np.median(supported))
    supporting_pairs = [
        (o, c) for o, c in pairs
        if abs(float(c[0] - o[0]) - offset) <= max(5.0, pitch * .30)
    ]
    opening_w = float(np.median([o[2] - o[0] for o, _ in supporting_pairs]))
    closing_w = float(np.median([c[2] - c[0] for _, c in supporting_pairs]))
    opening_h = float(np.median([o[3] - o[1] for o, _ in supporting_pairs]))
    closing_h = float(np.median([c[3] - c[1] for _, c in supporting_pairs]))
    typical_open_x = float(np.median([o[0] for o, _ in supporting_pairs]))
    typical_y_delta = float(np.median([c[1] - o[1] for o, c in supporting_pairs]))
    paired_opens = {id(o) for o, _ in pairs}
    paired_closes = {id(c) for _, c in pairs}
    results: list[tuple[int, int]] = []

    for opening in openings:
        if id(opening) in paired_opens:
            continue
        ax, ay, _x1, _y1 = opening
        if abs(float(ax) - typical_open_x) > max(7.0, pitch * .40):
            continue
        if _visible_bracket_band(
            ink, ax + offset - x_offset, ay + typical_y_delta - y_offset,
            closing_w, closing_h, opening=False, pitch=pitch,
        ):
            results.append((int(ax), int(ay)))
            continue

        # Longer printed bracketed heads put the closing bracket further
        # right than the repeated two-character template. A closing bracket
        # attached to a Han stroke need not be a separate component. Look
        # for its full directional ink shape near the same printed baseline.
        # This runs only after >=3 trustworthy intact local pairs.
        width = max(8, round(closing_w))
        height = max(16, round(closing_h))
        by = round(ay + typical_y_delta - y_offset)
        search_from = round(ax + offset + max(4.0, pitch * .25) - x_offset)
        search_to = min(
            ink.shape[1] - width,
            round(ax + min(10.0 * pitch, .55 * ink.shape[1]) - x_offset),
        )
        if 0 <= by and by + height <= ink.shape[0]:
            for bx in range(max(0, search_from), search_to + 1):
                if _bracket_side(ink[by:by + height, bx:bx + width], False):
                    results.append((int(ax), int(ay)))
                    break

    for closing in closings:
        if id(closing) in paired_closes:
            continue
        bx, by, _x1, _y1 = closing
        predicted_ax = float(bx) - offset
        if abs(predicted_ax - typical_open_x) > max(7.0, pitch * .40):
            continue
        if predicted_ax - column_left > 5.5 * pitch:
            continue
        if _visible_bracket_band(
            ink, predicted_ax - x_offset, by - typical_y_delta - y_offset,
            opening_w, opening_h, opening=True, pitch=pitch,
        ):
            results.append((int(round(predicted_ax)), int(round(by - typical_y_delta))))
    return results


def recover_bracketed_ordinary_entries(
    entries: list[Entry],
    image: Image.Image,
    columns,
    body_top: int,
    body_bottom: int,
    line_height: float,
    *,
    transform=None,
    source_size: tuple[int, int] | None = None,
    candidate_debug: list[dict[str, object]] | None = None,
) -> list[Entry]:
    """Supplement entries only from matching opening/closing print glyphs.

    Detect on a canonical image, and inverse-map accepted boundaries to the
    source image when a transform is supplied (RTL / rotated dictionaries).
    Matching pairs must begin in the first ~5.5 text pitches of the column;
    this excludes quoted bracket expressions deeper inside a definition.
    """
    pitch = float(line_height)
    if not 12 <= pitch <= 120:
        return list(entries)
    gray = image.convert("L")
    try:
        result = list(entries)
        for col in columns:
            left, right = int(col.left), int(col.right)
            # Brackets in real 三民 / XDHYCD pages start at (or even a few
            # pixels before) the registered column boundary. The old +0.5h
            # crop omitted entire opening glyphs and whole runs of entries.
            x0 = max(0, left - round(pitch * .25))
            x1 = min(gray.width, right, left + round(pitch * 21.0))
            y0 = max(0, int(body_top))
            y1 = min(gray.height, int(body_bottom))
            if x1 - x0 < pitch * 8 or y1 <= y0:
                continue
            crop = np.asarray(gray.crop((x0, y0, x1, y1)), dtype=np.uint8)
            ink = crop < 170
            openings, closings = [], []
            for a, b, c, d, area in _strict_bracket_components(ink):
                w, h = c - a, d - b
                if not (.32 * pitch <= w <= 1.25 * pitch
                        and .72 * pitch <= h <= 2.50 * pitch
                        and area >= .11 * pitch * pitch):
                    continue
                component = ink[b:d, a:c]
                location = (a + x0, b + y0, c + x0, d + y0)
                if (location[0] - left <= 5.5 * pitch
                        and _bracket_side(component, True)):
                    openings.append(location)
                if _bracket_side(component, False):
                    closings.append(location)
            paired = [
                (o, c) for o in openings for c in closings
                if .8 * pitch <= c[0] - o[0] <= 18.0 * pitch
                and abs(c[1] - o[1]) <= .5 * pitch
                and abs((c[3] - c[1]) - (o[3] - o[1])) <= .7 * pitch
            ]
            if candidate_debug is not None:
                paired_openings = {tuple(o) for o, _c in paired}
                paired_closings = {tuple(c) for _o, c in paired}
                for label, boxes, paired_boxes in (
                    ("opening", openings, paired_openings),
                    ("closing", closings, paired_closings),
                ):
                    for box in boxes:
                        source_box = (
                            transform.canonical_box_to_source(box, source_size)
                            if transform is not None and source_size is not None
                            else box
                        )
                        proven = tuple(box) in paired_boxes
                        candidate_debug.append({
                            "source_box": [int(v) for v in source_box],
                            "status": "accepted" if proven else "unpaired",
                            "bracket_side": label,
                            "reason": ("括号笔画方向、距离及高度共同满足成对匹配"
                                       if proven else "该括号外形未构成有效的完整配对"),
                        })
            proven_rows = [(int(o[0]), int(o[1])) for o, _c in paired]
            proven_rows.extend(_sticky_pairs_from_printed_template(
                ink, openings, closings, paired,
                x_offset=x0, y_offset=y0, column_left=left, pitch=pitch,
            ))
            visited: list[int] = []
            for ax, ay in sorted(proven_rows, key=lambda pair: pair[1]):
                if any(abs(ay - prior) <= max(5, pitch * .32) for prior in visited):
                    continue
                visited.append(ay)
                # Find a true preceding gap instead of splitting bracket ink.
                proposed_y = y0 + safe_gap_above(crop, ay - y0, pitch)

                def at_same_boundary(entry):
                    if transform is not None and source_size is not None:
                        ex, ey = transform.source_to_canonical_point(
                            int(entry.x), int(entry.y), source_size,
                        )
                    else:
                        ex, ey = int(entry.x), int(entry.y)
                    return (
                        abs(ex - left) <= pitch
                        and abs(ey - proposed_y) <= max(6.0, pitch * .35)
                    )

                existing = next((entry for entry in result if at_same_boundary(entry)), None)
                if existing is not None:
                    # An already-existing Layout candidate can be a *confirmed*
                    # bracket head. Preserve the visual proof so final-stage
                    # indent/body vetoes never delete it as an unproven role.
                    if (
                        "ordinary_layout_role" in str(existing.ocr_source or "")
                        and not bool(existing.ocr_oversized_cjk)
                    ):
                        existing.ocr_source = "ordinary_bracket_pair"
                        existing.issue_type = "ORDINARY_VISUAL_BRACKET_PAIR"
                    continue
                if transform is not None and source_size is not None:
                    source_x, source_y = transform.canonical_to_source_point(
                        left, proposed_y, source_size,
                    )
                else:
                    source_x, source_y = left, proposed_y
                result.append(Entry(
                    word="", x=int(source_x), y=int(source_y),
                    ocr_source="ordinary_bracket_pair",
                    issue_type="ORDINARY_VISUAL_BRACKET_PAIR",
                ))
        return result
    finally:
        gray.close()
