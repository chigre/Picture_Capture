from __future__ import annotations

from types import SimpleNamespace

from picture_capture.layout_visualization_summary import _summary_box


class _Geometry:
    top = 100
    bottom = 1000
    column_starts = [40, 600]
    column_widths = [500, 500]

    def x_at(self, index: int, _y: int) -> int:
        return int(self.column_starts[index])

    def canonical_to_source(self, x: int, y: int) -> tuple[int, int]:
        return int(x), int(y)


def test_summary_box_occupies_rightmost_eighty_percent_of_first_column() -> None:
    app = SimpleNamespace(view_scale=2.0)
    snapshot = SimpleNamespace(
        geometry=_Geometry(),
        used_values={"character_height": 20},
    )

    x, y, width = _summary_box(app, snapshot)

    # C1 spans x=40..540.  The summary box must span the rightmost 80%:
    # x=140..540, whose centre is 340.  At 2x zoom this becomes 680px wide
    # and 800px in display width.
    assert x == 680.0
    assert width == 800.0

    # Vertical anchor remains body_top + 5 * character_height = 200.
    assert y == 400.0
