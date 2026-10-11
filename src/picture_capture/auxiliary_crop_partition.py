"""Apply auxiliary partition boundaries to *existing* entry crop pieces.

Every resulting piece retains the original PDIC entry reference and index.
An auxiliary boundary can therefore influence the image partition but cannot
create a new entry, index, name, standalone crop, or headword.
"""
from __future__ import annotations

from dataclasses import replace


def partition_entry_pieces(pieces, auxiliary_lines, geometry):
    if not auxiliary_lines:
        return list(pieces)
    column_starts = list(geometry.column_starts)
    if not column_starts:
        return list(pieces)
    columns = [[] for _ in column_starts]
    for line in auxiliary_lines:
        u, v = geometry.source_to_canonical(int(line.x), int(line.y))
        col = min(
            range(len(columns)),
            key=lambda i: abs(u - column_starts[i]),
        )
        columns[col].append(int(v))

    # A boundary between *adjacent real headwords in the same column* is
    # their shared crop boundary, not another continuation of the preceding
    # headword.  Rebalance both neighbouring pieces before splitting any
    # remaining auxiliary-only subdivisions. No synthetic PDIC Entry is made.
    balanced = list(pieces)
    consumed: dict[int, set[int]] = {col: set() for col in range(len(columns))}

    def piece_column(piece):
        x0, y0, x1, y1 = piece.box
        u, _ = geometry.source_to_canonical((x0 + x1) // 2, (y0 + y1) // 2)
        return min(range(len(columns)), key=lambda i: abs(u - column_starts[i]))

    for col, cuts in enumerate(columns):
        p0 = geometry.canonical_to_source(column_starts[col], 0)
        p1 = geometry.canonical_to_source(column_starts[col], 100)
        axis = 1 if abs(p1[1] - p0[1]) >= abs(p1[0] - p0[0]) else 0
        forward = p1[axis] >= p0[axis]
        first_coord, last_coord = (1, 3) if axis == 1 else (0, 2)
        end_side = last_coord if forward else first_coord
        start_side = first_coord if forward else last_coord
        for cut_i, v in sorted(enumerate(cuts), key=lambda item: item[1]):
            cut = int(geometry.canonical_to_source(column_starts[col], v)[axis])
            for i in range(len(balanced) - 1):
                previous, following = balanced[i], balanced[i + 1]
                if (previous.entry_ref_index is None
                        or following.entry_ref_index is None
                        or previous.entry_ref_index == following.entry_ref_index
                        or piece_column(previous) != col
                        or piece_column(following) != col):
                    continue
                prev_box, next_box = previous.box, following.box
                low, high = sorted((prev_box[first_coord], prev_box[last_coord]))
                prev_end, next_start = prev_box[end_side], next_box[start_side]
                # Real adjacent headword pieces share one boundary (the next
                # PDIC marker with only a small row-gap allowance). Exclude
                # SECTION gaps, unrelated columns, and preceding-page remnants.
                if (not low + 2 < cut < high - 2
                        or abs(prev_end - next_start) > 32):
                    continue
                # The auxiliary separator becomes the final pixel of the upper
                # entry and the first pixel of the lower entry. This avoids
                # incorrectly assigning both intervals to the upper word.
                new_prev, new_next = list(prev_box), list(next_box)
                new_prev[end_side] = cut
                new_next[start_side] = cut
                balanced[i] = replace(previous, box=tuple(new_prev))
                balanced[i + 1] = replace(following, box=tuple(new_next))
                consumed[col].add(cut_i)
                break

    result = []
    counts = {}
    for piece in balanced:
        # Do not export a synthetic auxiliary-only fragment or split an
        # earlier-page remainder that has no actual PDIC entry.
        if piece.entry_ref_index is None:
            result.append(piece)
            continue
        x0, y0, x1, y1 = piece.box
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        u, _v = geometry.source_to_canonical(cx, cy)
        col = min(range(len(columns)), key=lambda i: abs(u - column_starts[i]))
        # Direction of canonical reading V in source coordinates.  This works
        # for ordinary, flipped, and quarter-turn rotated scans.
        p0 = geometry.canonical_to_source(column_starts[col], 0)
        p1 = geometry.canonical_to_source(column_starts[col], 100)
        along_y = abs(p1[1] - p0[1]) >= abs(p1[0] - p0[0])
        axis = 1 if along_y else 0
        low, high = (y0, y1) if along_y else (x0, x1)
        split_at = []
        for cut_i, v in enumerate(columns[col]):
            if cut_i in consumed[col]:
                continue
            mapped = geometry.canonical_to_source(column_starts[col], v)
            cut = int(mapped[axis])
            if low + 2 < cut < high - 2:
                split_at.append(cut)
        edges = [low] + sorted(set(split_at)) + [high]
        # Preserve reading order even when canonical V increases in reverse
        # source-image coordinate order.
        if p1[axis] < p0[axis]:
            edges.reverse()
        for a, b in zip(edges, edges[1:]):
            lower, upper = min(a, b), max(a, b)
            if along_y:
                box = (x0, lower, x1, upper)
            else:
                box = (lower, y0, upper, y1)
            index = int(piece.output_index)
            counts[index] = counts.get(index, 0) + 1
            result.append(replace(
                piece, box=box, suffix=f"({counts[index]})",
            ))
    return result
