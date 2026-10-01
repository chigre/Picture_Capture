from picture_capture.layout_visualization_readability import _background_for_text


def test_layout_label_backgrounds_follow_text_category() -> None:
    assert _background_for_text("#d32f2f", "body_top=120") == ("#ffebee", "#d32f2f")
    assert _background_for_text("#1976d2", "C1 x=42 w=300") == ("#e3f2fd", "#1976d2")
    assert _background_for_text("#7b1fa2", "gutter") == ("#f3e5f5", "#7b1fa2")
    assert _background_for_text("#111111", "Layout AUTO\nmethod: reliable") == ("#fffde7", "#757575")
    assert _background_for_text("#111111", "other") == ("#ffffff", "#9e9e9e")
