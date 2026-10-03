from pathlib import Path


def test_layout_toggle_is_ui_local_and_not_persisted() -> None:
    text = Path("src/picture_capture/layout_visualization_ui_v3.py").read_text(encoding="utf-8")

    assert 'text="显示Layout"' in text
    assert 'quick_bool_vars["show_layout_visualization"]' not in text
    assert 'setattr(app.settings, "show_layout_visualization"' not in text
    assert 'setattr(self.settings, "show_layout_visualization"' not in text
    assert 'app._layout_visualization_var = var' in text
    assert 'app.redraw()' in text
