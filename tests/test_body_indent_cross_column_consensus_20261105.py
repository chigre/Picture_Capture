"""Synthetic failure-first regression for body-indent page-wide lane semantics.

The 33 rows reproduce only the six measured C1/C2/C3 lane centers and support
counts from an anonymized diagnostic; no scan, text, OCR, or user sidecar.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.layout.core_understanding import _resolve_directional_body_lanes
from picture_capture.layout.physical_indent import normalize_layout_roles


def _mode(center: float, support: int, tolerance: float) -> SimpleNamespace:
    lines = [
        SimpleNamespace(
            first_x=float(center), y0=48 * index, y1=48 * index + 28,
            role="unknown",
        )
        for index in range(support)
    ]
    return SimpleNamespace(
        center=float(center), tolerance=float(tolerance),
        support=int(support), lines=lines, role="unknown",
    )


def _column(*modes: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        indent_modes=list(modes),
        lines=[line for mode in modes for line in mode.lines],
        body_mode=None,
        entry_modes=[],
    )


def _diagnostic_layout(*, third_has_body: bool = True, polarity: str = "body"):
    first = _column(_mode(12.0, 10, 1.0), _mode(58.0, 1, 1.0))
    second = _column(_mode(13.6, 11, 1.6))
    third_modes = [_mode(15.6, 6, 1.9), _mode(22.1, 2, 1.1)]
    if third_has_body:
        third_modes.append(_mode(61.9, 3, 1.9))
    third = _column(*third_modes)
    return SimpleNamespace(
        indent_type=polarity,
        ordinary_line_height=35.0,
        columns=[first, second, third],
        display_heads=[],
    )


@pytest.mark.parametrize(
    "finalize",
    [normalize_layout_roles, _resolve_directional_body_lanes],
    ids=["stage09-semantic-normalization", "post-stage09-body-lane-refinement"],
)
def test_body_indent_uses_repeated_page_wide_outer_entry_family(
    finalize,
) -> None:
    """A column with no *internal* indentation can still contain all entries.

    With body indentation selected, C1 has 10 aligned headwords and a single
    deeply indented continuation; C2 has 11 aligned headwords but no body row;
    C3 has 8 outer aligned headwords and 3 deeply indented continuations.
    Physical-mode support counts alone must not label the 29 entries as body.
    """
    layout = _diagnostic_layout()
    finalize(layout)

    expected_roles = [
        [["entry"] * 10, ["body"]],
        [["entry"] * 11],
        [["entry"] * 6, ["entry"] * 2, ["body"] * 3],
    ]
    for column, expected_groups in zip(layout.columns, expected_roles):
        assert [
            [line.role for line in mode.lines] for mode in column.indent_modes
        ] == expected_groups
    assert layout.columns[0].body_mode is layout.columns[0].indent_modes[1]
    assert layout.columns[1].body_mode is None
    assert layout.columns[2].body_mode is layout.columns[2].indent_modes[2]
    assert sum(line.role == "entry" for c in layout.columns for line in c.lines) == 29
    assert sum(line.role == "body" for c in layout.columns for line in c.lines) == 4


@pytest.mark.parametrize(
    "finalize",
    [normalize_layout_roles, _resolve_directional_body_lanes],
    ids=["stage09", "body-lane-refinement"],
)
def test_one_unconfirmed_singleton_is_not_page_wide_body_indent_evidence(
    finalize,
) -> None:
    """A lone deep speck in only one column must not relabel entire columns."""
    layout = _diagnostic_layout(third_has_body=False)
    finalize(layout)
    assert all(
        line.role != "entry" for column in layout.columns for line in column.lines
    )


@pytest.mark.parametrize(
    "finalize",
    [normalize_layout_roles, _resolve_directional_body_lanes],
    ids=["stage09", "body-lane-refinement"],
)
def test_opposite_headword_polarity_never_uses_body_indent_consensus(
    finalize,
) -> None:
    layout = _diagnostic_layout(polarity="headword")
    finalize(layout)
    assert all(
        line.role == "body"
        for column in layout.columns
        for line in column.indent_modes[0].lines
    )
