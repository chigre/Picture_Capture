"""Page list pale grid: viewport geometry without changing Treeview rows."""
from __future__ import annotations

from picture_capture.ui.page_list_grid import (
    DARK_GRID, LIGHT_GRID, page_grid_segments,
)


class FakeTable:
    def __init__(self, *, width=310, height=180, scroll=0, reversed_rows=False):
        self.width = width
        self.height = height
        self.scroll = scroll
        self.row_height = 30
        self.header = 24
        self.rows = [str(n) for n in range(50)]
        if reversed_rows:
            self.rows.reverse()
        self.column_edges = [0, 28, 128, 205, 310]

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def identify_row(self, y):
        if y < self.header:
            return ""
        index = self.scroll + (y - self.header) // self.row_height
        return self.rows[index] if 0 <= index < len(self.rows) else ""

    def identify_column(self, x):
        if x < 0 or x >= self.width:
            return ""
        for index, edge in enumerate(self.column_edges[1:], 1):
            if x < edge:
                return f"#{index}"
        return ""


def test_grid_has_both_horizontal_and_vertical_pale_lines():
    segments = page_grid_segments(FakeTable())
    horizontal = [line for line in segments if line[3] == 1]
    vertical = [line for line in segments if line[2] == 1]
    assert len(horizontal) >= 4, segments
    assert len(vertical) == 3, segments
    assert [item[0] for item in vertical] == [27, 127, 204]
    assert all(item[1] >= 24 for item in vertical)
    assert all(item[0] == 0 and item[2] == 310 for item in horizontal)
    assert LIGHT_GRID.startswith("#") and DARK_GRID.startswith("#")


def test_grid_lines_follow_scroll_position_and_dynamic_row_height():
    tree = FakeTable(height=200, scroll=39)
    before = page_grid_segments(tree)
    assert before
    tree.row_height = 60
    after = page_grid_segments(tree)
    # Rows have doubled height; horizontal dividers are now twice as far apart.
    y0 = [s[1] for s in before if s[3] == 1]
    y1 = [s[1] for s in after if s[3] == 1]
    assert y0[:3] == [53, 83, 113]
    assert y1[:2] == [83, 143]


def test_optional_column_visibility_and_horizontal_scroll_shift_gridlines():
    tree = FakeTable()
    first = [s[0] for s in page_grid_segments(tree) if s[2] == 1]
    assert first == [27, 127, 204]
    tree.column_edges = [0, 40, 150, 310]  # One optional column removed.
    assert [s[0] for s in page_grid_segments(tree) if s[2] == 1] == [39, 149]
    tree.column_edges = [0, 15, 100, 280, 310]  # Horizontally scrolled.
    assert [s[0] for s in page_grid_segments(tree) if s[2] == 1] == [14, 99, 279]


def test_no_rows_does_not_draw_fake_cell_borders():
    tree = FakeTable(scroll=200)
    assert page_grid_segments(tree) == []


def test_sort_does_not_change_border_geometry_or_page_identity():
    usual = FakeTable(scroll=12)
    reversed_tree = FakeTable(scroll=12, reversed_rows=True)
    assert page_grid_segments(usual) == page_grid_segments(reversed_tree)
    assert usual.identify_row(27) != reversed_tree.identify_row(27)


class TtkResizeGripTable(FakeTable):
    """The native ttk column hit-test changes AFTER a draggable separator.

    The screenshot showed heading boundaries ~5 logical pixels to the LEFT
    of the current overlay. bbox() carries exact native heading/body geometry.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.column_edges = [1, 91, 136, 266, 326]
        self._scroll_x = 0
        self._hitbox_bias = 5

    def identify_column(self, x):
        for index, edge in enumerate(self.column_edges[1:], 1):
            if x < edge + self._hitbox_bias - self._scroll_x:
                return f"#{index - 1}"
        return ""

    def bbox(self, iid, column):
        if iid not in self.rows:
            return ""
        try:
            position = int(str(column).replace("#", ""))
        except ValueError:
            return ""
        if position >= len(self.column_edges) - 1:
            return ""
        start = self.column_edges[position] - self._scroll_x
        width = self.column_edges[position + 1] - self.column_edges[position]
        return (start, 24, width, self.row_height)


def test_real_cell_bounds_avoid_resize_grip_hitbox_offset():
    tree = TtkResizeGripTable()
    # The old implementation placed these lines at 95, 140, 270 rather
    # than on the native header/cell edges at 90, 135, 265.
    border_x = [
        line[0] for line in page_grid_segments(tree)
        if line[2] == 1
    ]
    assert border_x == [90, 135, 265], border_x


def test_separator_geometry_follows_scroll_and_resized_columns():
    tree = TtkResizeGripTable()
    tree.scroll = 28
    assert [line[0] for line in page_grid_segments(tree) if line[2] == 1] == [
        90, 135, 265,
    ]
    tree._scroll_x = 40
    assert [line[0] for line in page_grid_segments(tree) if line[2] == 1] == [
        50, 95, 225, 285,
    ]
    tree._scroll_x = 0
    tree.column_edges = [1, 111, 156, 286, 346]
    assert [line[0] for line in page_grid_segments(tree) if line[2] == 1] == [
        110, 155, 285,
    ]


def test_missing_unlaid_out_bbox_skips_inaccurate_separator_not_shifts():
    tree = TtkResizeGripTable()
    tree.bbox = lambda iid, column: ""
    assert not [line for line in page_grid_segments(tree) if line[2] == 1]
    assert [line for line in page_grid_segments(tree) if line[3] == 1]


class NativeColumnGeometry(TtkResizeGripTable):
    """Tk-style column API whose final resize hitbox is outside viewport."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from types import SimpleNamespace

        self.tk = SimpleNamespace(
            splitlist=lambda value: value if isinstance(value, tuple) else tuple(value.split()),
        )

    def cget(self, name):
        return {
            "columns": ("bookmark", "page", "lined"),
            "displaycolumns": ("#all",),
            "show": ("tree", "headings"),
        }[name]

    def bbox(self, iid, column):
        aliases = {"bookmark": "#1", "page": "#2", "lined": "#3"}
        return super().bbox(iid, aliases.get(column, column))


def test_native_columns_include_final_boundary_when_resize_grip_is_offscreen():
    tree = NativeColumnGeometry(width=304)
    tree._scroll_x = 26
    # The final cell ends at x=299 but identify_column() won't reach
    # the empty hitbox until x=305 (already outside the widget).
    assert tree.identify_column(303) == "#3"
    vertical = [line[0] for line in page_grid_segments(tree) if line[2] == 1]
    assert vertical == [64, 109, 239, 299]


def test_native_column_enumeration_keeps_all_boundaries_after_scroll_and_sort():
    tree = NativeColumnGeometry(width=310, scroll=39, reversed_rows=True)
    expected = [90, 135, 265]
    assert [line[0] for line in page_grid_segments(tree) if line[2] == 1] == expected
    tree._scroll_x = 40
    assert [line[0] for line in page_grid_segments(tree) if line[2] == 1] == [
        50, 95, 225, 285,
    ]


def test_tk_tcl_obj_show_values_include_thumbnail_tree_column():
    class TclOption:
        def __init__(self, text):
            self.text = text

        def __str__(self):
            return self.text

    tree = NativeColumnGeometry(width=310)
    original_cget = tree.cget
    tree.cget = lambda name: (
        (TclOption("tree"), TclOption("headings"))
        if name == "show" else original_cget(name)
    )
    borders = [x for x, _y, w, _h in page_grid_segments(tree) if w == 1]
    assert borders == [90, 135, 265]
