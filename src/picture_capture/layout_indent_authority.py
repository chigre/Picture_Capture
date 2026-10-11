"""Trustworthy per-column CJK indent grammar and per-physical-row evidence.

A repeated entry lane opposite an independently repeated body lane is positive
evidence for ordinary headwords. Final separator-Y refinement does not change
which printed *physical row* a marker represents; sampling ink below its
separator must not override that evidence.

Weak/singleton, no-indent, or missing-geometry columns retain older fallbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .layout_physical_indent import normalized_physical_indents


@dataclass(frozen=True)
class StableIndentGrammar:
    entry_center: float
    body_center: float
    boundary: float
    minimum_margin: float
    entry_mode_ids: frozenset[int]


def stable_indent_grammar(
    column: Any, indent_type: str, reference: float,
) -> StableIndentGrammar | None:
    """Require two well-separated, independently repeated physical lanes."""
    if indent_type not in {"body", "headword"}:
        return None
    lines = list(getattr(column, "lines", ()) or ())
    body = getattr(column, "body_mode", None)
    entries = list(getattr(column, "entry_modes", ()) or ())
    if body is None or not entries or len(lines) < 16:
        return None
    n_min = max(4, int(round(len(lines) * .09)))
    if int(getattr(body, "support", 0) or 0) < n_min:
        return None
    eligible = [
        mode for mode in entries
        if int(getattr(mode, "support", 0) or 0) >= n_min
    ]
    if not eligible:
        return None
    # "Body indentation" means entries are closer to the column outer edge;
    # "Headword indentation" reverses the direction.
    entry = (
        min(eligible, key=lambda m: float(m.center))
        if indent_type == "body"
        else max(eligible, key=lambda m: float(m.center))
    )
    entry_x = float(entry.center)
    body_x = float(body.center)
    ref = max(8.0, float(reference))
    if abs(entry_x - body_x) < max(12.0, ref * .72):
        return None
    if (body_x <= entry_x if indent_type == "body" else body_x >= entry_x):
        return None
    return StableIndentGrammar(
        entry_center=entry_x,
        body_center=body_x,
        boundary=(entry_x + body_x) / 2.0,
        minimum_margin=max(3.0, min(7.0, ref * .12)),
        entry_mode_ids=frozenset(id(mode) for mode in eligible),
    )


def stable_indent_row_ids(column: Any, grammar: StableIndentGrammar) -> set[int]:
    """Return only printed rows independently supported by the entry lane.

    A repeated lane family must be established, then the individual row's
    slant-normalized first-ink start must independently agree with that lane.
    """
    normal = normalized_physical_indents(
        list(getattr(column, "lines", ()) or ())
    )
    role_direction = 1 if grammar.entry_center < grammar.body_center else -1
    protected: set[int] = set()
    for line in list(getattr(column, "lines", ()) or ()):
        if str(getattr(line, "role", "")) != "entry":
            continue
        x = normal.get(id(line))
        if x is None:
            continue
        if role_direction * (grammar.boundary - x) >= grammar.minimum_margin:
            protected.add(id(line))
    return protected


def reconcile_stable_indent_rows(
    layout: Any, *, cjk: bool,
) -> dict[str, int]:
    """Resolve mixed-mode mistakes by the actual first ink of each row.

    Never reclassify without stable, separated lane statistics. Visual symbol
    and large-head evidence is promoted *after* this physical step.
    """
    result = {"trusted_columns": 0, "entry_promoted": 0, "body_demoted": 0}
    if not cjk:
        return result
    grammar_name = str(getattr(layout, "indent_type", "") or "")
    reference = float(getattr(layout, "ordinary_line_height", 0) or 0)
    for column in list(getattr(layout, "columns", ()) or ()):
        grammar = stable_indent_grammar(column, grammar_name, reference)
        if grammar is None:
            continue
        result["trusted_columns"] += 1
        normal = normalized_physical_indents(
            list(getattr(column, "lines", ()) or ())
        )
        direction = 1 if grammar.entry_center < grammar.body_center else -1
        for line in list(getattr(column, "lines", ()) or ()):
            x = normal.get(id(line))
            if x is None:
                continue
            signed_distance = direction * (grammar.boundary - x)
            if signed_distance >= grammar.minimum_margin:
                if str(getattr(line, "role", "")) != "entry":
                    line.role = "entry"
                    result["entry_promoted"] += 1
            elif signed_distance <= -grammar.minimum_margin:
                if str(getattr(line, "role", "")) == "entry":
                    line.role = "body"
                    result["body_demoted"] += 1
    return result


__all__ = [
    "StableIndentGrammar", "stable_indent_grammar", "stable_indent_row_ids",
    "reconcile_stable_indent_rows",
]
