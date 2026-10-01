from __future__ import annotations

"""Fuse OCR-independent ordinary-mode entry evidence.

The universal ordinary mode is intentionally an OR-fusion of independent page
structures:

* final Layout line role (physical indentation/topology);
* sampled structural symbols at a row start;
* oversized display-head typography.

No evidence family is allowed to veto another.  Fusion only deduplicates nearby
boundaries and keeps the strongest runtime metadata for diagnostics.
"""

from typing import Iterable

from .models import Entry


def _priority(entry: Entry) -> tuple[int, float]:
    source = str(getattr(entry, "ocr_source", "") or "")
    if source == "ordinary_symbol_evidence":
        family = 3
    elif source == "ordinary_large_head_evidence":
        family = 2
    elif "ordinary_layout_role" in source:
        family = 1
    else:
        family = 0
    confidence = float(entry.confidence) if entry.confidence is not None else 0.0
    return family, confidence


def fuse_ordinary_entry_evidence(
    groups: Iterable[Iterable[Entry]],
    *,
    line_height: float,
) -> list[Entry]:
    """OR-fuse ordinary candidates while collapsing the same physical entry."""
    candidates = [entry for group in groups for entry in group]
    if not candidates:
        return []

    # Same entry detectors can disagree slightly on separator Y.  Keep that
    # disagreement local to one ordinary row and leave final Y placement to the
    # shared separator-Y refinement stage.
    y_tolerance = max(3, round(float(line_height) * 0.58))
    x_tolerance = max(4, round(float(line_height) * 1.10))

    candidates.sort(key=lambda item: (item.y, item.x, -_priority(item)[0]))
    fused: list[Entry] = []
    for candidate in candidates:
        duplicate_index: int | None = None
        for index, existing in enumerate(fused):
            if (
                abs(int(candidate.y) - int(existing.y)) <= y_tolerance
                and abs(int(candidate.x) - int(existing.x)) <= x_tolerance
            ):
                duplicate_index = index
                break
        if duplicate_index is None:
            fused.append(candidate)
            continue
        existing = fused[duplicate_index]
        if _priority(candidate) > _priority(existing):
            fused[duplicate_index] = candidate

    return fused
