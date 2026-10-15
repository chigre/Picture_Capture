"""Viewport-scoped thumbnails follow real on-screen Treeview rows after scrolling."""
from picture_capture.ui.page_thumbnails import visible_page_iids


class ScrolledTree:
    """Synthetic Treeview without bbox support, reproduces old early-stop case."""
    def __init__(self, offset=0):
        self.displayed = [str(i) for i in range(50)]
        self.offset = offset
        self.header = 32
        self.rowheight = 72
        self.height = 350

    def winfo_height(self):
        return self.height

    def identify_row(self, y):
        if y < self.header:
            return ""
        index = self.offset + (y - self.header) // self.rowheight
        return self.displayed[index] if 0 <= index < len(self.displayed) else ""

    def bbox(self, iid):
        # On many native ttk themes, bbox is empty until the row has been
        # laid out for the current scroll position; the old walker stopped.
        return ""


def test_scrolled_viewport_is_not_stuck_at_first_nine_rows():
    tree = ScrolledTree()
    assert visible_page_iids(tree) == ["0", "1", "2", "3", "4"]
    tree.offset = 27
    assert visible_page_iids(tree) == ["27", "28", "29", "30", "31"]
    tree.offset = 45
    assert visible_page_iids(tree) == ["45", "46", "47", "48", "49"]


def test_viewport_tracks_sorted_iid_identity_not_original_row_index():
    tree = ScrolledTree(offset=15)
    tree.displayed = list(reversed(tree.displayed))
    assert visible_page_iids(tree) == ["34", "33", "32", "31", "30"]


def test_viewport_still_captures_partly_visible_last_row():
    tree = ScrolledTree(offset=22)
    tree.height = 360
    ids = visible_page_iids(tree)
    assert ids == ["22", "23", "24", "25", "26"]
    assert ids == list(dict.fromkeys(ids))


def test_viewport_handles_unmapped_or_empty_scrolled_tree():
    tree = ScrolledTree(offset=60)
    assert visible_page_iids(tree) == []
