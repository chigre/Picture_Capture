from types import SimpleNamespace

from picture_capture.layout_physical_indent import normalize_layout_roles


class _Mode:
    def __init__(self, center: float, support: int, ys: list[tuple[int, int]]):
        self.center = float(center)
        self.role = "body"
        self.lines = [
            SimpleNamespace(y0=y0, y1=y1, role="body") for y0, y1 in ys
        ]

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


def test_headword_indent_marks_every_distinct_lane_right_of_body_as_entry() -> None:
    body = _Mode(20, 40, [(i * 20, i * 20 + 10) for i in range(40)])
    slight = _Mode(28, 1, [(900, 910)])
    deeper = _Mode(48, 1, [(940, 950)])
    column = _column(body, slight, deeper)
    layout = SimpleNamespace(
        indent_type="headword",
        columns=[column],
        display_heads=[],
    )

    normalize_layout_roles(layout)

    assert column.body_mode is body
    assert slight.role == "entry"
    assert deeper.role == "entry"
    assert slight.lines[0].role == "entry"
    assert deeper.lines[0].role == "entry"


def test_oversized_display_head_keeps_only_first_overlapping_entry_row() -> None:
    body = _Mode(20, 20, [(i * 20, i * 20 + 10) for i in range(20)])
    display = _Mode(90, 2, [(500, 535), (535, 570)])
    column = _column(body, display)
    head = SimpleNamespace(column=0, y0=495, y1=575)
    layout = SimpleNamespace(
        indent_type="headword",
        columns=[column],
        display_heads=[head],
    )

    normalize_layout_roles(layout)

    assert display.lines[0].role == "entry"
    assert display.lines[1].role == "body"
