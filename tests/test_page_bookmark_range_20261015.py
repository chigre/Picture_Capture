"""Bookmark means selected batch page scope, never a page-index filter."""
from __future__ import annotations

from pathlib import Path

from picture_capture.page_list_helpers import bookmarked_page_indices, _sorted_page_list_rows


def test_bookmark_scope_uses_original_project_order_not_sorted_treeview():
    pages = [Path(f"/scan/page{i:04}.png") for i in range(6)]
    # The page list may currently show descending "插图" order.
    sorted_rows = _sorted_page_list_rows(
        [(str(i), ("", pages[i].stem, "", "", "", str(i + 1))) for i in range(6)],
        "illustrations", descending=True,
    )
    assert [iid for iid, _ in sorted_rows] != ["0", "1", "2", "3", "4", "5"]
    assert bookmarked_page_indices(pages, {"page0005", "page0001", "page0003"}) == [1, 3, 5]
    # No mutation/sort/filter of the Treeview.
    assert len(sorted_rows) == len(pages)


def test_bookmark_scope_is_empty_if_no_bookmarks_or_unmatched_old_names():
    pages = [Path("001.png"), Path("002.png"), Path("003.png")]
    assert bookmarked_page_indices(pages, set()) == []
    assert bookmarked_page_indices(pages, {"999"}) == []


def test_bookmark_scope_uses_stems_as_existing_bookmark_storage_contract():
    pages = [Path("001.jpg"), Path("002.png"), Path("003.tif")]
    assert bookmarked_page_indices(pages, {"001", "003"}) == [0, 2]


def test_bookmark_scope_does_not_use_current_page_or_range_spec():
    pages = [Path(f"{n:04}.png") for n in range(10)]
    assert bookmarked_page_indices(pages, {"0001", "0009"}) == [1, 9]
