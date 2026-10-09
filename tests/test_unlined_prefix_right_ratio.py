"""Unlined diagnosis uses the left-side prefix instead of whole text rows."""
from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.unlined_line_export import (
    _save_unlined_rows,
    row_ink_percent,
    unlined_rows_from_layout,
)


class Identity:
    def canonical_to_source_point(self, x, y, size):
        return x, y

    def source_to_canonical_point(self, x, y, size):
        return x, y


def test_right_ratio_crops_from_column_left():
    line = SimpleNamespace(y0=20, y1=40, role="body")
    column = SimpleNamespace(index=0, left=30, right=230, lines=[line])
    layout = SimpleNamespace(
        source_size=(250, 100), transform=Identity(),
        body_top=0, body_bottom=100, ordinary_line_height=20,
        columns=[column],
    )
    whole, _, _ = unlined_rows_from_layout(layout, [], None)
    prefix, _, _ = unlined_rows_from_layout(
        layout, [], None, right_ratio=10.0,
    )
    assert whole[0].source_box[0] == prefix[0].source_box[0] == 30
    assert whole[0].source_box[2] == 230
    assert prefix[0].source_box[2] == 50


def test_blank_detection_is_on_left_prefix_even_if_row_has_body_text(tmp_path):
    line = SimpleNamespace(y0=15, y1=35, role="body")
    column = SimpleNamespace(index=0, left=10, right=210, lines=[line])
    layout = SimpleNamespace(
        source_size=(240, 65), transform=Identity(),
        body_top=0, body_bottom=65, ordinary_line_height=20,
        columns=[column],
    )
    source = Image.new("RGB", (240, 65), "white")
    draw = ImageDraw.Draw(source)
    # A body-text block later in the row, beyond the 10% diagnostic prefix.
    draw.rectangle((70, 18, 140, 30), fill="black")
    rows, _, _ = unlined_rows_from_layout(layout, [], None, right_ratio=10.0)
    assert rows[0].source_box[0:3:2] == (10, 30)
    exported, blanks, filtered, merged = _save_unlined_rows(
        source, tmp_path / "page.png", rows, tmp_path / "output",
        merge_by_page=False, filter_enabled=True,
        filter_blank=True, blank_ink_percent=0.8,
    )
    assert (exported, blanks, filtered, merged) == (1, 1, 0, False)
    with Image.open(tmp_path / "output" / "page_UL_000.png") as crop:
        assert crop.width == 20
        assert row_ink_percent(crop) == 0.0
    source.close()
