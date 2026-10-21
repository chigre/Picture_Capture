from __future__ import annotations

from types import SimpleNamespace

from picture_capture.layout_visualization_ui_v3 import _set_layout_exclusive_visibility


class _Var:
    def __init__(self, value: bool) -> None:
        self.value = value

    def get(self) -> bool:
        return self.value

    def set(self, value: bool) -> None:
        self.value = bool(value)


def test_layout_exclusive_mode_hides_other_overlays_then_restores_false() -> None:
    app = SimpleNamespace(hide_var=_Var(False))

    _set_layout_exclusive_visibility(app, True)
    assert app.hide_var.get() is True
    assert app._layout_visualization_previous_hide_value is False

    _set_layout_exclusive_visibility(app, False)
    assert app.hide_var.get() is False
    assert not hasattr(app, "_layout_visualization_previous_hide_value")


def test_layout_exclusive_mode_preserves_preexisting_hidden_state() -> None:
    app = SimpleNamespace(hide_var=_Var(True))

    _set_layout_exclusive_visibility(app, True)
    assert app.hide_var.get() is True
    assert app._layout_visualization_previous_hide_value is True

    _set_layout_exclusive_visibility(app, False)
    assert app.hide_var.get() is True
