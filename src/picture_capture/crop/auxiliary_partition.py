"""Apply auxiliary stop lines without producing an auxiliary image.

An auxiliary line ends the preceding PDIC entry at that exact source-space
coordinate.  From the line to the next headword (or the lane end), the region
is a preview-only gap labelled 【辅助不切】.  The following real entry keeps
its original start, identity, and filename.  No synthetic entry is exported.
"""
from __future__ import annotations

from dataclasses import replace


def partition_entry_pieces(pieces, auxiliary_lines, geometry, auxiliary_gaps=None):
    """Return exportable pieces; optionally collect non-exported source boxes.

    `auxiliary_gaps` is deliberately separate from the returned export plan:
    callers that write WW images can never accidentally publish a gap.
    """
    if not auxiliary_lines or not geometry.column_starts:
        return list(pieces)

    starts = list(geometry.column_starts)
    columns = [[] for _ in starts]
    for line in auxiliary_lines:
        u, v = geometry.source_to_canonical(int(line.x), int(line.y))
        column = min(range(len(starts)), key=lambda i: abs(u - starts[i]))
        columns[column].append(int(v))

    def piece_column(piece):
        x0, y0, x1, y1 = piece.box
        u, _ = geometry.source_to_canonical((x0 + x1) // 2, (y0 + y1) // 2)
        return min(range(len(starts)), key=lambda i: abs(u - starts[i]))

    axes = []
    for col in range(len(starts)):
        p0 = geometry.canonical_to_source(starts[col], 0)
        p1 = geometry.canonical_to_source(starts[col], 100)
        axis = 1 if abs(p1[1] - p0[1]) >= abs(p1[0] - p0[0]) else 0
        forward = p1[axis] >= p0[axis]
        first, last = (1, 3) if axis == 1 else (0, 2)
        axes.append((axis, forward, first if forward else last,
                     last if forward else first))

    result = []
    stopped_entry = None
    for pos, piece in enumerate(pieces):
        # The inherited preceding-page remainder has no PDIC headword.  It is
        # intentionally left intact, as with the original partition planner.
        if piece.entry_ref_index is None:
            stopped_entry = None
            result.append(piece)
            continue
        if piece.entry_ref_index == stopped_entry:
            if auxiliary_gaps is not None:
                auxiliary_gaps.append(piece.box)
            continue
        stopped_entry = None

        col = piece_column(piece)
        axis, forward, start_side, end_side = axes[col]
        start = piece.box[start_side]
        end = piece.box[end_side]
        cuts = (int(geometry.canonical_to_source(starts[col], v)[axis])
                for v in columns[col])
        valid = sorted(
            (cut for cut in cuts
             if (start + 2 < cut < end - 2 if forward
                 else end + 2 < cut < start - 2)),
            reverse=not forward,
        )
        if not valid:
            result.append(piece)
            continue

        # The first line in canonical reading order stops the exportable word.
        cut = valid[0]
        cropped = list(piece.box)
        cropped[end_side] = cut
        result.append(replace(piece, box=tuple(cropped)))

        gap_end = end
        # The next real headword begins at its own original marker/padded top,
        # never at the auxiliary line.  Close the preview gap at that start
        # when two same-column pieces meet (allowing a small row-padding delta).
        for following in pieces[pos + 1:]:
            if following.entry_ref_index is None:
                break
            if following.entry_ref_index == piece.entry_ref_index:
                continue
            if (piece_column(following) == col
                    and abs(following.box[start_side] - end) <= 32):
                candidate = following.box[start_side]
                if (candidate > cut if forward else candidate < cut):
                    gap_end = candidate
            break

        gap = list(piece.box)
        gap[start_side] = cut
        gap[end_side] = gap_end
        if auxiliary_gaps is not None and gap[0] < gap[2] and gap[1] < gap[3]:
            auxiliary_gaps.append(tuple(gap))
        # All continuation fragments of this *same* PDIC headword after the
        # stop also belong to the unexported gap, including other columns.
        stopped_entry = piece.entry_ref_index

    return result
