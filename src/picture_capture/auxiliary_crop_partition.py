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

    result = []
    counts = {}
    for piece in pieces:
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
        for v in columns[col]:
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
