from __future__ import annotations

"""Preserve physical indents when a scanned column drifts across Y.

Project/Profile geometry owns the *semantic* column-left boundary.  Real scans,
however, can lean or curve slightly so lower rows may extend left of that fixed
boundary.  The historical Page Layout strip started exactly at ``column.left``;
once a row crossed that edge its leading ink was clipped and ``first_x`` became
0.  A later slant correction cannot recover pixels that were never observed.

This helper keeps the configured column geometry unchanged but re-measures each
recovered row in a wider analysis window that extends to the left.  The measured
``first_x`` remains expressed relative to the original semantic ``column.left``
and is therefore allowed to be negative before common-drift normalization.

Important ownership rule: this module owns *indent remeasurement only*.  It must
never replace the universal large-head detector.  Large-head detection has its
own stricter row-front/oversized authorization runtime; replacing that callable
here used to silently disable those guards in the real GUI/spawn import order.
The helper ``_analysis_left_for_column`` remains public so the strict large-head
detector can reuse exactly the same left safety band without changing ownership.
"""

from typing import Any

import numpy as np
from PIL import Image, ImageOps

from . import dictionary_page_design as base
from .geometry.layout_gutter_rule import gutter_divider_right_edge as _gutter_divider_right_edge


def _left_safety(reference: float, column_width: int) -> int:
    """Maximum evidence-probe radius, NOT an estimated skew or row offset.

    Actual per-row overhang is accepted only from visible, attributable ink.
    Merely having a 92px potential window does not authorize a 92px drift.
    """
    ref = max(6.0, float(reference))
    width = max(1, int(column_width))
    return max(12, min(round(ref * 1.75), round(width * 0.14), 96))


def _analysis_left_for_column(
    columns: list[Any],
    index: int,
    reference: float,
) -> int:
    """Extend left into margin/gutter but never into the previous text column."""
    column = columns[index]
    semantic_left = int(getattr(column, "left", 0) or 0)
    semantic_right = int(getattr(column, "right", semantic_left + 1) or semantic_left + 1)
    safety = _left_safety(reference, max(1, semantic_right - semantic_left))
    candidate = max(0, semantic_left - safety)
    if index <= 0:
        return candidate
    previous_right = int(getattr(columns[index - 1], "right", 0) or 0)
    return max(candidate, previous_right + 1)





def _foreign_column_tail_replacement(
    row: np.ndarray,
    *,
    initial_x: int,
    analysis_left: int,
    semantic_left: int,
    previous_right: int,
    reference: float,
    previous_column_tail: np.ndarray,
) -> int | None:
    """Find real in-column text behind a disconnected neighboring-column tail.

    Widened slant windows can begin only 1–3 px beyond the previous column's
    nominal right edge. A previous-column line ending there is not evidence
    that the *next* column starts at that X. Require BOTH an actual in-column
    text onset and a long, physically empty horizontal gap from the outside
    fragment to that onset. This is a row-local image observation, not a
    second-pass role guess, row-index rule or cross-column body vote.

    Genuine negative first-X drift/overhang is preserved when print continues
    across the semantic left edge or the gap is ambiguous.
    """
    from .layout_physical_indent import _credible_first_ink_x

    if (
        row.ndim != 2 or row.size == 0
        or initial_x >= semantic_left
        or initial_x > previous_right + max(12, round(reference * .40))
    ):
        return None
    boundary = semantic_left - analysis_left
    if boundary <= 0 or boundary >= row.shape[1]:
        return None
    # The allegedly foreign fragment must actually be backed by printed
    # previous-column text on this SAME physical row. Do not drop a legitimate
    # isolated outdented bullet/label solely because it is far from body text.
    if previous_column_tail.ndim != 2 or previous_column_tail.size == 0:
        return None
    prior_columns = np.asarray(previous_column_tail, dtype=bool).any(axis=0)
    if (
        int(prior_columns.sum()) < max(4, round(reference * .12))
        or int(np.count_nonzero(previous_column_tail)) < max(10, round(reference * .50))
    ):
        return None

    right_onset = _credible_first_ink_x(row[:, boundary:], reference)
    if right_onset is None:
        return None

    # A true overhanging glyph/prefix normally continues through the gutter
    # towards semantic_left. An unrelated previous-column tail leaves a large
    # background corridor before any credible in-column glyph.
    outside_ink = np.flatnonzero(np.asarray(row[:, :boundary], dtype=bool).any(axis=0))
    if outside_ink.size == 0:
        return None
    last_outside_x = analysis_left + int(outside_ink[-1])
    inside_x = semantic_left + int(right_onset)
    gap = inside_x - last_outside_x - 1
    if gap < max(12, round(max(6.0, reference) * .70)):
        return None
    return int(inside_x)


def remeasure_layout_indents_from_ink(
    layout: Any,
    page_ink: np.ndarray,
    *,
    ops: base.LayoutPrimitiveOps | None = None,
    divider_positions: dict[int, int] | None = None,
    foreign_tail_rejections: dict[int, int] | None = None,
    measured_overhangs: dict[int, tuple[int, int]] | None = None,
) -> dict[int, int]:
    """Measure within each semantic column first, then verify true overhang.

    The maximum scan-slant inspection window is only an upper bound. For later
    columns, an in-column print onset is authoritative by default; the widened
    gutter window can override it only if it contains a credible glyph fragment
    with no evidence that it is the preceding column's disconnected line tail.
    This protects real negative indents without treating a 92px safety radius
    as a measured skew. No physical rows or column geometry are modified.

    Return updated row counts by column, in the original local-X convention.
    """
    from .layout_physical_indent import _credible_first_ink_x

    ops = base.current_layout_ops() if ops is None else ops

    if page_ink.ndim != 2 or page_ink.size == 0:
        return {}

    reference = max(
        6.0,
        float(getattr(layout, "ordinary_line_height", 1.0) or 1.0),
    )
    body_top = int(getattr(layout, "body_top", 0) or 0)
    height, width = page_ink.shape
    updated: dict[int, int] = {}
    columns = list(getattr(layout, "columns", []) or [])

    for position, column in enumerate(columns):
        column_index = int(getattr(column, "index", position) or position)
        semantic_left = int(getattr(column, "left", 0) or 0)
        semantic_right = int(getattr(column, "right", semantic_left + 1) or semantic_left + 1)
        column_width = max(1, semantic_right - semantic_left)
        analysis_left = _analysis_left_for_column(columns, position, reference)
        # The widening needed for tilted text also reaches back into the
        # *printed divider* of a ruled dictionary. An ink stroke stretching
        # most of the page may otherwise become "first_x" on every row,
        # collapsing real entry/body indents to the same negative X lane.
        if position > 0 and analysis_left < semantic_left:
            previous_right = int(columns[position - 1].right)
            rule_right = _gutter_divider_right_edge(
                page_ink,
                body_top=body_top,
                body_bottom=int(getattr(layout, "body_bottom", height)),
                corridor_left=max(analysis_left, previous_right + 1),
                corridor_right=semantic_left - max(2, round(reference * .12)),
                reference=reference,
            )
            if rule_right is not None and rule_right > analysis_left:
                analysis_left = min(semantic_left, rule_right)
                if divider_positions is not None:
                    divider_positions[column_index] = analysis_left
        analysis_right = min(
            width,
            semantic_left + base._leading_width(column_width, reference),
        )
        if analysis_right <= analysis_left:
            continue

        count = 0
        rejected_tails = 0
        accepted_outdents = 0
        largest_outdent = 0
        for line in list(getattr(column, "lines", []) or []):
            try:
                y0 = max(0, min(height, body_top + int(getattr(line, "y0"))))
                y1 = max(y0 + 1, min(height, body_top + int(getattr(line, "y1"))))
            except (AttributeError, TypeError, ValueError):
                continue

            # Ownership-first measurement: the original detected column is
            # the default text source, NOT the negative-X scan safety strip.
            inside = page_ink[y0:y1, semantic_left:analysis_right]
            local_inside = _credible_first_ink_x(inside, reference)
            inside_x = (
                semantic_left + int(local_inside)
                if local_inside is not None else None
            )
            absolute_x = inside_x

            if analysis_left < semantic_left:
                # The full old radius is a *possible inspection area*, not
                # the offset applied to every row. Do not even look for an
                # outside origin unless physical ink exists outside the
                # semantic column on this row.
                outer_ink = page_ink[y0:y1, analysis_left:semantic_left]
                if bool(outer_ink.any()):
                    row = page_ink[y0:y1, analysis_left:analysis_right]
                    local_extended = _credible_first_ink_x(row, reference)
                    if local_extended is not None:
                        candidate = analysis_left + int(local_extended)
                        if candidate < semantic_left:
                            replacement = None
                            if position > 0:
                                replacement = _foreign_column_tail_replacement(
                                    row,
                                    initial_x=candidate,
                                    analysis_left=analysis_left,
                                    semantic_left=semantic_left,
                                    previous_right=int(columns[position - 1].right),
                                    reference=reference,
                                    previous_column_tail=page_ink[
                                        y0:y1,
                                        max(
                                            0,
                                            int(columns[position - 1].right)
                                            - max(12, round(reference * .80)),
                                        ):analysis_left,
                                    ],
                                )
                            if replacement is not None:
                                # The foreign fragment only becomes relevant
                                # if a different credible IN-column line start
                                # is independently visible. Fail closed for
                                # ambiguous outside-only print.
                                absolute_x = inside_x
                                rejected_tails += 1
                            else:
                                # Genuine printed outdent, measured directly
                                # from actual first ink, not an assumed skew.
                                absolute_x = candidate
                                if position > 0:
                                    accepted_outdents += 1
                                    largest_outdent = max(
                                        largest_outdent,
                                        semantic_left - candidate,
                                    )

            if absolute_x is None:
                continue
            line.first_x = int(absolute_x - semantic_left)
            count += 1

        if rejected_tails and foreign_tail_rejections is not None:
            foreign_tail_rejections[column_index] = rejected_tails
        if accepted_outdents and measured_overhangs is not None:
            measured_overhangs[column_index] = (
                accepted_outdents, largest_outdent,
            )

        if count:
            # Composition already provides the physical-indent implementations.
            # Rebuild modes and roles from the unclipped values.
            column.indent_modes = ops.indent_modes(column.lines, reference)
            ops.assign_indent_semantics(
                column,
                str(getattr(layout, "indent_type", "body") or "body"),
                reference,
            )
            updated[column_index] = count

    return updated


def finalize_layout_column_drift(
    image: Image.Image,
    settings: Any,
    layout: Any,
    *,
    page_index: int = 0,
    page_ink: np.ndarray | None = None,
    ops: base.LayoutPrimitiveOps | None = None,
) -> Any:
    """Apply post-policy indent remeasurement, reusing an existing page mask when supplied."""
    explicit_ops = ops is not None
    ops = base.current_layout_ops() if ops is None else ops
    divider_positions: dict[int, int] = {}
    foreign_tails: dict[int, int] = {}
    measured_overhangs: dict[int, tuple[int, int]] = {}
    if page_ink is None:
        from .layout_detection import analysis_ink_mask

        source, canonical, _transform, effective = base._analysis_page(
            image,
            settings,
            int(page_index),
        )
        try:
            page_ink = analysis_ink_mask(
                np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8),
                effective,
            )
            counts = remeasure_layout_indents_from_ink(
                layout, page_ink, divider_positions=divider_positions,
                foreign_tail_rejections=foreign_tails,
                measured_overhangs=measured_overhangs,
                **({"ops": ops} if explicit_ops else {}),
            )
        finally:
            try:
                canonical.close()
            except Exception:
                pass
            try:
                source.close()
            except Exception:
                pass
    else:
        counts = remeasure_layout_indents_from_ink(
                layout, page_ink, divider_positions=divider_positions,
                foreign_tail_rejections=foreign_tails,
                measured_overhangs=measured_overhangs,
                **({"ops": ops} if explicit_ops else {}),
            )

    if counts:
        detail = ",".join(
            f"C{index + 1}:{count}" for index, count in sorted(counts.items())
        )
        layout.reason += f"; unclipped_first_x={detail}"
    if divider_positions:
        detail = ",".join(
            f"C{index + 1}:X{right}" for index, right in sorted(divider_positions.items())
        )
        layout.reason += f"; slanted_gutter_rule_guard={detail}"
    if foreign_tails:
        detail = ",".join(
            f"C{index + 1}:{count}" for index, count in sorted(foreign_tails.items())
        )
        layout.reason += f"; foreign_column_tail_rejected={detail}"
    if measured_overhangs:
        detail = ",".join(
            f"C{index + 1}:{count}/max{pixels}px"
            for index, (count, pixels) in sorted(measured_overhangs.items())
        )
        layout.reason += f"; measured_outdents={detail}"
    return layout


__all__ = [
    "_analysis_left_for_column",
    "_left_safety",
    "finalize_layout_column_drift",
    "remeasure_layout_indents_from_ink",
]
