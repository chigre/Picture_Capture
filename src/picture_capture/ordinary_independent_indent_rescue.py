"""Recover a proven second-column headword family lost in Layout core.

On a real Spanish--Chinese scanned page, the independent page-design analyzer
recognizes 26 right-column entry indent rows while the modern physical-row
normalization collapses nearly all of them into body. An entire printed column
must not be silently discarded because one role estimator failed.

Only run a second, independent visual layout pass for a severely depleted
non-CJK column. Require a *repeated* outer lemma family, a *repeated* inner
body family, and a clear observed offset. Never synthesize one entry merely
because a column has zero predictions. Other dictionaries keep the fast path.
"""
from __future__ import annotations

from typing import Any

from PIL import Image

from .models import AppSettings, Entry
from .page_understanding import uses_cjk_role_model


def recover_depleted_indent_columns(
    image: Image.Image,
    settings: AppSettings,
    understanding: Any,
    entries: list[Entry],
    *,
    page_index: int = 0,
) -> list[Entry]:
    """Add only independently supported real row heads in empty/depleted columns."""
    layout = understanding.layout
    columns = list(getattr(layout, "columns", ()) or ())
    if uses_cjk_role_model(settings) or len(columns) < 2:
        return list(entries)
    transform = layout.transform
    current_counts = [0] * len(columns)
    for entry in entries:
        u, _v = transform.source_to_canonical_point(
            int(entry.x), int(entry.y), layout.source_size,
        )
        nearest = min(
            range(len(columns)),
            key=lambda index: abs(u - int(columns[index].left)),
        )
        current_counts[nearest] += 1

    depleted = {
        index for index, col in enumerate(columns)
        if len(getattr(col, "lines", ()) or ()) >= 18
        and current_counts[index] <= 2
    }
    if not depleted:
        return list(entries)

    from . import dictionary_page_design as native
    from . import dictionary_page_design_refined as refined

    # The raw physical primitives are deliberately independent of the newer
    # composed physical-role pipeline. A second invocation of the same failed
    # role classifier would not provide independent supporting evidence.
    try:
        independent = refined.detect_entries_from_page_design(
            image, settings, page_index=page_index, ops=native.RAW_LAYOUT_OPS,
        )
    except (TypeError, ValueError, RuntimeError, IndexError):
        return list(entries)
    alternate = independent.layout
    alt_cols = list(getattr(alternate, "columns", ()) or ())
    if not getattr(alternate, "reliable", False) or len(alt_cols) != len(columns):
        return list(entries)
    h = max(8.0, float(getattr(alternate, "ordinary_line_height", 1) or 1))
    confirmed = set()
    for index in depleted:
        col = alt_cols[index]
        body = getattr(col, "body_mode", None)
        families = list(getattr(col, "entry_modes", ()) or ())
        if body is None or getattr(body, "support", 0) < 5:
            continue
        accepted = [
            mode for mode in families
            if getattr(mode, "support", 0) >= max(5, round(len(col.lines) * .09))
            and (
                float(getattr(body, "center", 0) or 0)
                - float(getattr(mode, "center", 0) or 0)
            ) >= h * .30
        ]
        if accepted and sum(int(mode.support) for mode in accepted) >= 5:
            confirmed.add(index)
    if not confirmed:
        return list(entries)

    output = list(entries)
    duplicate_gap = max(5.0, h * .58)
    # Source coordinates from the independent pass, snapped only to the main
    # column X. Preserve its independently observed reading-Y value.
    for candidate in list(independent.entries or ()):
        u, v = alternate.transform.source_to_canonical_point(
            int(candidate.x), int(candidate.y), alternate.source_size,
        )
        index = min(
            range(len(alt_cols)),
            key=lambda i: abs(u - int(alt_cols[i].left)),
        )
        if index not in confirmed:
            continue
        column = columns[index]
        dest_x, dest_y = transform.canonical_to_source_point(
            int(column.left), int(v), layout.source_size,
        )
        if any(
            abs(other.x - dest_x) < h * 2
            and abs(other.y - dest_y) <= duplicate_gap
            for other in output
        ):
            continue
        output.append(Entry(
            word="", x=int(dest_x), y=int(dest_y),
            ocr_source="ordinary_independent_indent_rescue",
            issue_type="ORDINARY_INDEPENDENT_INDENT_FAMILY",
        ))
    return output
