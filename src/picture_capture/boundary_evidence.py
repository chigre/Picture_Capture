"""Non-destructive evidence ledger for dictionary entry-boundary decisions.

A physical text row and a dictionary entry are different facts. This immutable
ledger makes every existing ordinary entry role explainable *before* the project
changes its PDIC. It intentionally never invents a line from word density and
never treats OCR text alone as authoritative visual-entry evidence.

This is the safe first migration step: the existing production labels are
preserved, and the observations can be used for per-book validation before a
future confidence threshold is allowed to suppress ambiguous real headwords.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .entry_classification import get_layout_line_classification


@dataclass(frozen=True, slots=True)
class BoundaryProposal:
    column: int
    canonical_v: int
    source_x: int
    source_y: int
    role: str
    source: str
    positives: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()
    decision: str = "keep_legacy"  # no unvalidated suppression


def proposed_layout_boundaries(understanding: Any) -> tuple[BoundaryProposal, ...]:
    """Snapshot accepted rows without changing cached LayoutLine.role values."""
    layout = understanding.layout
    reference = max(1.0, float(getattr(layout, "ordinary_line_height", 1.0) or 1.0))
    result: list[BoundaryProposal] = []
    for index, column in enumerate(getattr(layout, "columns", ())):
        lines = sorted(getattr(column, "lines", ()), key=lambda line: (line.y0, line.y1))
        for row_index, line in enumerate(lines):
            if str(getattr(line, "role", "") or "") != "entry":
                continue
            metadata = get_layout_line_classification(line)
            source = str(metadata.entry_source or "unknown")
            positives: list[str] = []
            caveats: list[str] = []
            if source == "symbol_sample":
                positives.append("confirmed_symbol_visual")
            elif source == "large_head":
                positives.append("oversized_head_visual")
            else:
                positives.append("layout_indent_lane")

            if bool(getattr(line, "has_small_prefix", False)):
                positives.append("small_leading_symbol")
            if source in {"unknown", "indent"}:
                # A true word might have no OCR or typographic cues at all.
                # Record the uncertainty; do not suppress it yet.
                caveats.append("indent_not_independent_entry_proof")
            if row_index == 0:
                caveats.append("first_visible_row_may_continue_previous_page")

            first_x = float(getattr(line, "first_x", 0.0) or 0.0)
            column_width = max(1.0, float(column.right - column.left))
            if first_x >= max(reference * 2.7, column_width * 0.24):
                caveats.append("unusually_deep_start_check_caption_or_example")

            canonical_v = int(layout.body_top) + int(line.y0)
            x, y = layout.transform.canonical_to_source_point(
                int(column.left), canonical_v, layout.source_size,
            )
            result.append(BoundaryProposal(
                column=int(getattr(column, "index", index)),
                canonical_v=canonical_v,
                source_x=int(x), source_y=int(y),
                role="entry_candidate",
                source=source,
                positives=tuple(positives),
                caveats=tuple(caveats),
            ))
    return tuple(result)


def serialize_proposals(proposals: tuple[BoundaryProposal, ...]) -> list[dict]:
    """Stable JSON-friendly format for diagnostic exports and model comparison."""
    return [asdict(item) for item in proposals]
