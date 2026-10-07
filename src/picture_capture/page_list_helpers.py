from __future__ import annotations

"""Pure sorting and semantic-status helpers for the page list."""

from .models import natural_text_key


def _natural_text_key(value: object) -> tuple:
    """Natural, case-insensitive key used by the sortable page list.

    Numeric runs are compared as integers so e.g. page2 sorts before page10.
    The tagged tuple parts keep text and integer components mutually comparable.
    """
    return natural_text_key(value)


def _sorted_page_list_rows(rows: list[tuple[str, tuple]], column: str, descending: bool = False) -> list[tuple[str, tuple]]:
    """Sort Treeview-like page rows without changing their stable page iids.

    ``rows`` contains ``(iid, values)`` pairs. Empty cells stay at the bottom in
    either direction, while visible values use natural text ordering.
    """
    # Accept older four/five-value rows in unit callers/session migrations.
    max_values = max((len(values) for _iid, values in rows), default=0)
    has_section = max_values >= 6
    has_bookmark = max_values >= 5
    if has_section:
        mapping = {
            "bookmark": 0, "page": 1, "section": 2, "lined": 3,
            "fill_status": 4, "illustrations": 5,
        }
    elif has_bookmark:
        mapping = {"bookmark": 0, "page": 1, "lined": 2, "fill_status": 3, "illustrations": 4}
    else:
        mapping = {"page": 0, "lined": 1, "fill_status": 2, "illustrations": 3}
    column_index = mapping.get(column, 1 if has_bookmark else 0)
    populated: list[tuple[str, tuple]] = []
    empty: list[tuple[str, tuple]] = []
    for row in rows:
        values = row[1]
        value = values[column_index] if column_index < len(values) else ""
        (populated if str(value).strip() else empty).append(row)
    populated.sort(
        key=lambda row: _natural_text_key(row[1][column_index] if column_index < len(row[1]) else ""),
        reverse=descending,
    )
    return populated + empty

def _fill_status_cell_style(status_text: object) -> tuple[str, str] | None:
    """Return semantic (background, foreground) colors for fill-status cells.

    ``未核对`` deliberately uses the native Treeview background, so it returns
    ``None`` and no overlay is created.
    """
    text = str(status_text or "").strip()
    if text == "一致":
        return "#d9ead3", "#245b2a"
    if text.startswith("少 " ) or text.startswith("多 " ) or text in {"少", "多"}:
        return "#f8d7da", "#6b1f25"
    if text == "待重新核对":
        return "#fff3cd", "#6b5714"
    if text == "无资料":
        return "#e9ecef", "#495057"
    return None
