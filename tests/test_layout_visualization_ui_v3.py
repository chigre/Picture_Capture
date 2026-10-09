from pathlib import Path
from types import SimpleNamespace

import picture_capture.layout_visualization_ui_v3 as layout_ui


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value



def test_layout_toggle_is_ui_local_and_not_persisted() -> None:
    text = Path("src/picture_capture/layout_visualization_ui_v3.py").read_text(encoding="utf-8")

    assert 'text="显示Layout"' in text
    assert 'quick_bool_vars["show_layout_visualization"]' not in text
    assert 'setattr(app.settings, "show_layout_visualization"' not in text
    assert 'setattr(self.settings, "show_layout_visualization"' not in text
    assert 'app._layout_visualization_var = var' in text
    assert 'app.redraw()' in text



def test_static_layout_draw_temporarily_unhides_and_restores(monkeypatch) -> None:
    seen = []
    app = SimpleNamespace(
        _layout_visualization_var=_Var(True),
        hide_var=_Var(True),
    )

    monkeypatch.setattr(
        layout_ui,
        "draw_layout_visualization_detailed",
        lambda current: seen.append(bool(current.hide_var.get())),
    )

    layout_ui.draw_layout_visualization_if_enabled(app)

    assert seen == [False]
    assert app.hide_var.get() is True


def test_layout_visualization_is_wired_statically_in_app() -> None:
    root = Path(__file__).resolve().parents[1]
    app = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    gui = (
        root / "src" / "picture_capture" / "bootstrap" / "gui.py"
    ).read_text(encoding="utf-8")
    helper = (
        root / "src" / "picture_capture" / "layout_visualization_ui_v3.py"
    ).read_text(encoding="utf-8")

    assert "add_layout_visualization_controls(self, aux)" in app
    assert app.count("draw_layout_visualization_if_enabled(self)") >= 4
    assert (
        "draw_ocr_crop_preview(self)\n"
        "            draw_layout_visualization_if_enabled(self)\n"
        "            return"
    ) in app
    assert (
        "draw_ocr_crop_preview(self)\n"
        "        draw_layout_visualization_if_enabled(self)"
    ) in app
    assert "install_layout_visualization(app_module)" not in gui
    assert "cls._section_frame =" not in helper
    assert "cls._build_quick_settings =" not in helper
    assert "cls.redraw =" not in helper
