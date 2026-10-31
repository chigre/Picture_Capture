"""Issue #562 Round 74: physical selected-page drawing dispatch owner."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.ui.detection_selected_scope_actions import (
    run_selected_draw_action,
)


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class App:
    def __init__(self):
        self.settings = SimpleNamespace(detection_method="original")
        self.ocr_refresh_var = Var("force")
        self.indices = [1, 3]
        self.scope_error = None
        self.guard_ok = True
        self.quick_ok = True
        self.calls = []
        self.errors = []

    def guard(self):
        self.calls.append("guard")
        return self.guard_ok

    def apply_quick_settings(self, *, show_status):
        self.calls.append(("quick", show_status))
        return self.quick_ok

    def selected_page_indices(self):
        self.calls.append("selected")
        if self.scope_error:
            raise self.scope_error
        return list(self.indices)

    def show_error(self, title, error):
        self.errors.append((title, error))

    def save_settings(self):
        self.calls.append("save")

    def _detect_pages(self, indices, *, method, force_refresh):
        self.calls.append(("detect", list(indices), method, force_refresh))


@pytest.mark.parametrize(
    ("method", "expected_calls"),
    [
        ("left_edge", ["guard", "ordinary", "selected", "save",
                       ("detect", [1, 3], "left_edge", False)]),
        ("paddleocr", ["ocr_guard", "guard", ("quick", False), "selected", "save",
                       ("detect", [1, 3], "paddleocr", True)]),
        ("combined", ["ocr_guard", "guard", ("quick", False), "selected", "save",
                      ("detect", [1, 3], "combined", True)]),
    ],
)
def test_selected_modes_keep_preflight_scope_save_and_dispatch_order(method, expected_calls):
    app = App()
    run_selected_draw_action(
        app, method=method,
        ordinary_settings_guard=lambda obj: obj.calls.append("ordinary") or True,
        ocr_engine_guard=lambda obj: obj.calls.append("ocr_guard") or True,
    )
    assert app.calls == expected_calls
    assert app.settings.detection_method == method


@pytest.mark.parametrize("method", ["paddleocr", "combined"])
def test_ocr_engine_rejection_never_enters_generic_guards_or_mutates_settings(method):
    app = App()
    run_selected_draw_action(
        app, method=method,
        ocr_engine_guard=lambda obj: obj.calls.append("ocr_guard") or False,
    )
    assert app.calls == ["ocr_guard"]
    assert app.settings.detection_method == "original"
    assert app.errors == []


@pytest.mark.parametrize("method", ["left_edge", "paddleocr", "combined"])
def test_invalid_selected_page_range_does_not_save_or_dispatch(method):
    app = App()
    problem = ValueError("malformed range")
    app.scope_error = problem
    run_selected_draw_action(
        app, method=method,
        ordinary_settings_guard=lambda _obj: True,
        ocr_engine_guard=lambda _obj: True,
    )
    assert app.settings.detection_method == "original"
    assert app.errors == [("页面范围无效", problem)]
    assert "save" not in app.calls
    assert not any(isinstance(c, tuple) and c[0] == "detect" for c in app.calls)


@pytest.mark.parametrize("method", ["left_edge", "paddleocr", "combined"])
def test_failed_project_guard_short_circuits_before_quick_settings_or_scope(method):
    app = App()
    app.guard_ok = False
    run_selected_draw_action(
        app, method=method,
        ordinary_settings_guard=lambda obj: obj.calls.append("ordinary") or True,
        ocr_engine_guard=lambda obj: obj.calls.append("ocr_guard") or True,
    )
    assert app.settings.detection_method == "original"
    assert "selected" not in app.calls
    assert "save" not in app.calls
    assert ("quick", False) not in app.calls
    assert "ordinary" not in app.calls


def test_ordinary_quick_settings_failure_never_calls_detector():
    app = App()
    run_selected_draw_action(
        app, method="left_edge",
        ordinary_settings_guard=lambda obj: obj.calls.append("ordinary") or False,
    )
    assert app.calls == ["guard", "ordinary"]
    assert app.settings.detection_method == "original"


@pytest.mark.parametrize("method", ["paddleocr", "combined"])
def test_ocr_quick_settings_failure_never_calls_scope(method):
    app = App()
    app.quick_ok = False
    run_selected_draw_action(
        app, method=method, ocr_engine_guard=lambda _obj: True,
    )
    assert app.calls == ["guard", ("quick", False)]
    assert app.settings.detection_method == "original"


def test_selected_scope_ocr_reuse_keeps_force_refresh_false():
    app = App()
    app.ocr_refresh_var = Var("reuse")
    run_selected_draw_action(
        app, method="paddleocr", ocr_engine_guard=lambda _obj: True,
    )
    assert app.calls[-1] == ("detect", [1, 3], "paddleocr", False)


def test_invalid_method_fails_before_any_settings_mutation():
    app = App()
    with pytest.raises(ValueError, match="unknown selected drawing method"):
        run_selected_draw_action(app, method="not-a-detector")
    assert app.calls == []
    assert app.settings.detection_method == "original"


def test_three_legacy_entrypoints_keep_the_controller_contract():
    root = Path(__file__).resolve().parents[1] / "src/picture_capture/ui"
    controller = (root / "controllers/detection.py").read_text(encoding="utf-8")
    owner = (root / "detection_selected_scope_actions.py").read_text(encoding="utf-8")
    for method in ("run_normal_draw_action", "run_ocr_draw_action", "run_combined_draw_action"):
        assert f"def {method}(" in controller
    assert "return run_selected_draw_action(" in controller
    assert "def run_selected_draw_action(" in owner
    assert "app.selected_page_indices()" in owner
    assert "app.save_settings()" in owner
    assert "app._detect_pages(" in owner
