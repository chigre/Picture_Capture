from __future__ import annotations

from picture_capture import app, page_list_helpers as page_list


def test_phase7h_app_reexports_page_list_helpers() -> None:
    for name in (
        "_natural_text_key",
        "_sorted_page_list_rows",
        "_fill_status_cell_style",
    ):
        assert getattr(app, name) is getattr(page_list, name)


def test_page_list_sort_keeps_natural_order_and_empty_rows_last() -> None:
    rows = [
        ("10", ("page10", "有线", "一致", "0")),
        ("2", ("page2", "有线", "一致", "0")),
        ("empty", ("", "有线", "一致", "0")),
    ]

    ordered = page_list._sorted_page_list_rows(rows, "page")
    assert [iid for iid, _values in ordered] == ["2", "10", "empty"]

    reverse = page_list._sorted_page_list_rows(rows, "page", descending=True)
    assert [iid for iid, _values in reverse] == ["10", "2", "empty"]


def test_page_list_sort_accepts_legacy_bookmark_rows() -> None:
    rows = [
        ("2", ("☆", "page2", "有线", "一致", "0")),
        ("10", ("★", "page10", "有线", "一致", "0")),
    ]
    ordered = page_list._sorted_page_list_rows(rows, "page")
    assert [iid for iid, _values in ordered] == ["2", "10"]


def test_fill_status_style_keeps_semantic_contract() -> None:
    assert page_list._fill_status_cell_style("一致") == ("#d9ead3", "#245b2a")
    assert page_list._fill_status_cell_style("少 2") == ("#f8d7da", "#6b1f25")
    assert page_list._fill_status_cell_style("待重新核对") == ("#fff3cd", "#6b5714")
    assert page_list._fill_status_cell_style("无资料") == ("#e9ecef", "#495057")
    assert page_list._fill_status_cell_style("未核对") is None
