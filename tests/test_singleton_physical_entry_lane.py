from types import SimpleNamespace

from picture_capture.layout_physical_indent import assign_binary_roles


class _Mode:
    def __init__(self, center: float, support: int):
        self.center = float(center)
        self.lines = [SimpleNamespace(role="body") for _ in range(int(support))]
        self.role = "body"

    @property
    def support(self) -> int:
        return len(self.lines)


def _column(*modes: _Mode):
    lines = [line for mode in modes for line in mode.lines]
    return SimpleNamespace(
        indent_modes=list(modes),
        lines=lines,
        entry_modes=[],
        body_mode=None,
    )


def test_singleton_outer_lane_is_entry_for_body_indent_layout() -> None:
    outer = _Mode(center=4, support=1)
    body = _Mode(center=36, support=49)
    column = _column(outer, body)

    assign_binary_roles(column, "body")

    assert column.entry_modes == [outer]
    assert outer.role == "entry"
    assert outer.lines[0].role == "entry"
    assert body.role == "body"
    assert all(line.role == "body" for line in body.lines)
    assert column.body_mode is body


def test_single_lane_column_stays_all_body() -> None:
    only = _Mode(center=30, support=50)
    column = _column(only)

    assign_binary_roles(column, "body")

    assert column.entry_modes == []
    assert only.role == "body"
    assert all(line.role == "body" for line in only.lines)
    assert column.body_mode is only
