from picture_capture import layout_visualization_summary as summary
from picture_capture.layout_visualization_role_theme import (
    BODY_ROLE_COLOR,
    ENTRY_ROLE_COLOR,
    install_layout_role_theme,
)


def test_layout_entry_role_theme_is_red() -> None:
    install_layout_role_theme()

    assert ENTRY_ROLE_COLOR == "#d32f2f"
    assert BODY_ROLE_COLOR == "#1976d2"
    assert summary._ROLE_STYLE["entry"] == ("#d32f2f", "词条行")
    assert summary._ROLE_STYLE["headword"] == ("#d32f2f", "词条行")
    assert summary._ROLE_STYLE["body"] == ("#1976d2", "正文行")
