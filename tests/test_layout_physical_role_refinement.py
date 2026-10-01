from __future__ import annotations

from types import SimpleNamespace

from picture_capture.layout_physical_role_refinement import (
    assign_refined_physical_roles,
)


def _mode(center: float, support: int) -> SimpleNamespace:
    return SimpleNamespace(center=center, support=support, role="unknown")


def test_body_indented_layout_only_extreme_left_lane_becomes_entry() -> None:
    # Typical page: headwords are flush-left, ordinary body is farther inward,
    # while '~'/example/continuation text occupies intermediate physical lanes.
    entry = _mode(4.0, 5)
    tilde = _mode(20.0, 4)
    body = _mode(36.0, 12)
    deep = _mode(58.0, 3)
    column = SimpleNamespace(
        indent_modes=[entry, tilde, body, deep],
        body_mode=None,
        entry_modes=[],
    )

    assign_refined_physical_roles(column, "body", reference=20.0)

    assert body.role == "body"
    assert entry.role == "entry"
    assert tilde.role == "unknown"
    assert deep.role == "unknown"
    assert column.body_mode is body
    assert column.entry_modes == [entry]


def test_intermediate_lane_is_not_entry_even_with_good_support() -> None:
    # Reproduces the '~' / 'el ~' failure mode: an intermediate lane may appear
    # repeatedly, but repeated support alone must not make it a headword lane.
    entry = _mode(3.0, 4)
    continuation = _mode(17.0, 9)
    body = _mode(34.0, 10)
    column = SimpleNamespace(
        indent_modes=[entry, continuation, body],
        body_mode=None,
        entry_modes=[],
    )

    assign_refined_physical_roles(column, "body", reference=20.0)

    assert body.role == "body"
    assert entry.role == "entry"
    assert continuation.role == "unknown"


def test_dominant_support_selects_body_before_direction_tie_break() -> None:
    # A rare deeply-indented continuation lane must not steal body role merely
    # because it is the deepest stable lane.
    entry = _mode(2.0, 4)
    body = _mode(32.0, 11)
    rare_deep = _mode(54.0, 4)
    column = SimpleNamespace(
        indent_modes=[entry, body, rare_deep],
        body_mode=None,
        entry_modes=[],
    )

    assign_refined_physical_roles(column, "body", reference=20.0)

    assert column.body_mode is body
    assert body.role == "body"
    assert rare_deep.role == "unknown"
