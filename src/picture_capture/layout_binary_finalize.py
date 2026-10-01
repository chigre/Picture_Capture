from __future__ import annotations

"""Finalize dictionary layout roles as a strict physical-indent binary split.

Legacy layout construction still contains downstream sparse-entry propagation.
That older pass can append entry modes after the primary physical-indent role
assignment and can leave ``IndentMode.role`` / ``LayoutLine.role`` inconsistent.
This module normalizes the *returned* layout so every consumer (Page
Understanding, ordinary drawing and the diagnostic overlay) sees one contract:

* one physical-indent entry lane per column when a distinct candidate exists;
* every other lane and every other row is body;
* no ``unknown`` row or lane roles leave the layout boundary.
"""

from typing import Any, Callable


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


def finalize_binary_physical_roles(layout: Any) -> Any:
    """Normalize a finished layout to strict entry/body row roles."""
    indent_type = str(getattr(layout, "indent_type", "body") or "body")

    for column in list(getattr(layout, "columns", []) or []):
        modes = list(getattr(column, "indent_modes", []) or [])
        lines = list(getattr(column, "lines", []) or [])

        # Default everything to body first, including rows that are not present
        # in any lane due to filtering/outlier handling.
        for line in lines:
            line.role = "body"
        for mode in modes:
            mode.role = "body"

        column.entry_modes = []
        column.body_mode = None
        if not modes:
            continue

        # A single-lane column cannot establish an entry-vs-body separation.
        if len(modes) == 1:
            column.body_mode = modes[0]
            continue

        total = max(1, sum(_support(mode) for mode in modes))
        min_support = max(2, int((total * 0.06) + 0.999999))
        eligible = [mode for mode in modes if _support(mode) >= min_support]

        # Need at least two supported lanes to make a binary physical split.
        # If only one survives, keep the whole column as body.
        if len(eligible) < 2:
            column.body_mode = max(modes, key=_support)
            continue

        if indent_type == "headword":
            entry = max(eligible, key=_center)
        else:
            entry = min(eligible, key=_center)

        entry.role = "entry"
        for line in list(getattr(entry, "lines", []) or []):
            line.role = "entry"
        column.entry_modes = [entry]

        body_modes = [mode for mode in modes if mode is not entry]
        column.body_mode = max(
            body_modes,
            key=lambda mode: (_support(mode), -abs(_center(mode))),
        )

    return layout


def install_binary_layout_finalizer() -> None:
    """Wrap the public layout inference so returned roles are always binary."""
    from . import dictionary_page_design as page_design

    if getattr(page_design, "_binary_layout_finalizer_installed", False):
        return

    original: Callable[..., Any] = page_design.infer_dictionary_page_layout

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        return finalize_binary_physical_roles(original(*args, **kwargs))

    page_design.infer_dictionary_page_layout = wrapped
    page_design._binary_layout_finalizer_installed = True
