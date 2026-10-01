from __future__ import annotations

from types import SimpleNamespace

from picture_capture.layout_physical_indent import assign_binary_roles


class Mode(SimpleNamespace):
    @property
    def support(self) -> int:
        return len(self.lines)


def _line(x: float):
    return SimpleNamespace(first_x=x, y0=0, y1=10, role="unknown")


def _mode(center: float, values: list[float]) -> Mode:
    return Mode(
        center=center,
        tolerance=1.0,
        lines=[_line(value) for value in values],
        role="unknown",
    )


def test_nearby_lane_after_body_range_stays_body() -> None:
    body = _mode(2.0, [0, 1, 2, 3, 5, 8, 11] * 7)
    near = _mode(12.0, [16])
    entry = _mode(98.2, [98])
    column = SimpleNamespace(
        indent_modes=[body, near, entry],
        lines=[*body.lines, *near.lines, *entry.lines],
        body_mode=None,
        entry_modes=[],
    )

    assign_binary_roles(column, "headword", 68.0)

    assert body.role == "body"
    assert near.role == "body"
    assert entry.role == "entry"
    assert near not in column.entry_modes
    assert entry in column.entry_modes


def test_body_envelope_does_not_walk_into_far_entry_lanes() -> None:
    body = _mode(3.0, [0, 4, 8, 11] * 10)
    near1 = _mode(13.0, [16])
    near2 = _mode(20.0, [22])
    far = _mode(80.0, [80])
    column = SimpleNamespace(
        indent_modes=[body, near1, near2, far],
        lines=[*body.lines, *near1.lines, *near2.lines, *far.lines],
        body_mode=None,
        entry_modes=[],
    )

    assign_binary_roles(column, "headword", 68.0)

    assert near1.role == "body"
    assert near2.role == "body"
    assert far.role == "entry"
