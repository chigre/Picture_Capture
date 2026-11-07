"""Round 69: legacy OCR action entrypoints cannot bypass engine/scope guards."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.ui.controllers.detection import DetectionController


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class App:
    def __init__(self, *, lens_only: bool):
        self.settings = SimpleNamespace(
            detection_method="left_edge",
            paddle_use_paddleocr=not lens_only,
            paddle_compare_tesseract=False,
            paddle_tesseract_rescue=False,
            paddle_enable_lens=lens_only,
            paddle_lens_mode="off",
        )
        self.quick_bool_vars = {
            "paddle_use_paddleocr": Var(not lens_only),
            "paddle_compare_tesseract": Var(False),
            "paddle_enable_lens": Var(lens_only),
        }
        self.lens_mode_var = Var("① 关闭")
        self.current_index = 1
        self.project = SimpleNamespace(images=[object(), object(), object()])
        self.calls = []
        self.errors = []

    def show_error(self, title, error):
        self.errors.append((title, error))

    def guard(self):
        self.calls.append("guard")
        return True

    def apply_quick_settings(self, *, show_status):
        self.calls.append(("apply_quick_settings", show_status))
        return True

    def sync_quick_settings(self):
        self.calls.append("sync_quick_settings")

    def save_settings(self):
        self.calls.append("save_settings")

    def auto_detect_current(self, *, force_paddle_refresh):
        self.calls.append(("auto_detect_current", force_paddle_refresh))

    def _detect_pages(self, indices, *, method, force_refresh):
        self.calls.append(("detect_pages", list(indices), method, force_refresh))


@pytest.mark.parametrize("entrypoint", ["paddle_detect_current", "run_ocr_draw"])
def test_legacy_entry_rejects_ineffective_lens_before_mutation(entrypoint):
    app = App(lens_only=True)
    ctrl = DetectionController(app)
    if entrypoint == "paddle_detect_current":
        ctrl.paddle_detect_current(force_refresh=True)
    else:
        ctrl.run_ocr_draw("all", True)
    assert app.settings.detection_method == "left_edge"
    assert app.calls == []
    assert len(app.errors) == 1
    assert app.errors[0][0] == "OCR 引擎配置无效"


@pytest.mark.parametrize("scope", ["", "ALL", "selected", "../all"])
def test_legacy_ocr_rejects_unknown_scope_before_any_dispatch(scope):
    app = App(lens_only=False)
    DetectionController(app).run_ocr_draw(scope, True)
    assert app.settings.detection_method == "left_edge"
    assert "save_settings" not in app.calls
    assert not any(isinstance(x, tuple) and x[0] == "detect_pages" for x in app.calls)
    assert len(app.errors) == 1
    title, error = app.errors[0]
    assert title == "页面范围无效"
    assert isinstance(error, ValueError)


@pytest.mark.parametrize(
    ("scope", "expected_indices"),
    [("current", [1]), ("all", [0, 1, 2])],
)
def test_legacy_ocr_valid_scope_preserves_dispatch(scope, expected_indices):
    app = App(lens_only=False)
    DetectionController(app).run_ocr_draw(scope, True)
    assert app.settings.detection_method == "paddleocr"
    assert app.calls[-1] == ("detect_pages", expected_indices, "paddleocr", True)
    assert "save_settings" not in app.calls


def test_legacy_current_valid_ocr_still_syncs_and_saves():
    app = App(lens_only=False)
    DetectionController(app).paddle_detect_current(force_refresh=True)
    assert app.settings.detection_method == "paddleocr"
    assert app.calls == [
        "sync_quick_settings",
        "save_settings",
        ("auto_detect_current", True),
    ]
