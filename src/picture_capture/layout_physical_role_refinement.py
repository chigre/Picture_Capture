from __future__ import annotations

"""Refine row-role assignment on top of physical-indent lanes.

Physical indent is a layout fact; semantic role is a second-stage inference.
For body-indented dictionaries, many continuation patterns (for example '~',
'el ~', examples, numbered senses) can occupy intermediate lanes between the
flush-left headword lane and the dominant body lane.  Treating every lane on
the headword side of body as an entry lane therefore over-promotes continuation
rows.

This module keeps physical-indent clustering unchanged and narrows semantic
entry assignment to the single stable extreme lane on the entry side of the
dominant body lane.  Intermediate lanes remain unknown unless later evidence
promotes them.
"""

from typing import Any


def _support(mode: Any) -> int:
    try:
        return int(getattr(mode, "support", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _center(mode: Any) -> float:
    try:
        return float(getattr(mode, "center", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def assign_refined_physical_roles(
    column: Any,
    indent_type: str,
    reference: float,
) -> None:
    """Assign body/entry roles after per-column physical-indent clustering.

    The body lane is the dominant stable physical-indent lane.  Only one extreme
    stable lane on the configured entry side may become the entry lane.  This
    intentionally leaves intermediate lanes (tilde substitutions, examples,
    continuation text, numbered senses) as unknown instead of promoting them
    solely because they sit on the entry side of body.
    """
    modes = list(getattr(column, "indent_modes", []) or [])
    column.body_mode = None
    column.entry_modes = []
    if not modes:
        return

    for mode in modes:
        mode.role = "unknown"

    total = max(1, sum(_support(mode) for mode in modes))
    stable_min = max(3, round(total * 0.10))
    stable = [mode for mode in modes if _support(mode) >= stable_min]
    if not stable:
        stable = [max(modes, key=_support)]

    # First choose the statistically dominant body lane.  Only use the expected
    # indentation direction as a tie-breaker among equally supported lanes.
    max_support = max(_support(mode) for mode in stable)
    dominant = [mode for mode in stable if _support(mode) == max_support]
    if str(indent_type) == "headword":
        body = min(dominant, key=_center)
        entry_side = 1.0
    else:
        body = max(dominant, key=_center)
        entry_side = -1.0

    body.role = "body"
    column.body_mode = body

    ref = max(6.0, float(reference))
    minimum_separation = ref * 0.42
    maximum_separation = ref * 5.0

    candidates: list[Any] = []
    for mode in modes:
        if mode is body or _support(mode) < 2:
            continue
        separation = entry_side * (_center(mode) - _center(body))
        if minimum_separation <= separation <= maximum_separation:
            candidates.append(mode)

    if not candidates:
        return

    # Critical rule: entry is an extreme physical lane, not every lane on the
    # entry side of body.  Intermediate lanes stay unknown.
    if str(indent_type) == "headword":
        entry = max(candidates, key=_center)
    else:
        entry = min(candidates, key=_center)

    entry.role = "entry"
    column.entry_modes = [entry]


def install_refined_physical_role_assignment() -> None:
    """Install the refined physical-lane role assignment exactly once."""
    from . import dictionary_page_design as page_design

    if getattr(page_design, "_refined_physical_role_assignment_installed", False):
        return

    page_design._assign_indent_semantics = assign_refined_physical_roles
    page_design._refined_physical_role_assignment_installed = True
