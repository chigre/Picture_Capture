from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui.controllers.detection import DetectionController


ROOT = Path(__file__).resolve().parents[1]


class _Var:
    def __init__(self, value) -> None:
        self.value = value

    def get(self):
        return self.value


class _App:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(detection_method="left_edge")
        self.ocr_refresh_var = _Var("reuse")
        self.current_index = 2
        self.project = SimpleNamespace(images=[object(), object(), object(), object()])
        self.guard_result = True
        self.apply_result = True
        self.selected_result = [1, 3]
        self.selected_error: Exception | None = None
        self.calls: list[tuple] = []
        self.errors: list[tuple[str, Exception]] = []

    def guard(self) -> bool:
        self.calls.append(("guard",))
        return self.guard_result

    def apply_quick_settings(self, *, show_status: bool) -> bool:
        self.calls.append(("apply_quick_settings", show_status))
        return self.apply_result

    def selected_page_indices(self) -> list[int]:
        self.calls.append(("selected_page_indices",))
        if self.selected_error is not None:
            raise self.selected_error
        return list(self.selected_result)

    def save_settings(self) -> None:
        self.calls.append(("save_settings",))

    def sync_quick_settings(self) -> None:
        self.calls.append(("sync_quick_settings",))

    def auto_detect_current(self, *, force_paddle_refresh: bool) -> None:
        self.calls.append(("auto_detect_current", force_paddle_refresh))

    def _detect_pages(self, indices, *, method: str, force_refresh: bool) -> None:
        self.calls.append(("detect_pages", list(indices), method, force_refresh))

    def show_error(self, title: str, exc: Exception) -> None:
        self.errors.append((title, exc))


def test_paddle_detect_current_preserves_setting_sync_save_and_current_page_call() -> None:
    app = _App()
    controller = DetectionController(app)

    controller.paddle_detect_current(force_refresh=True)

    assert app.settings.detection_method == "paddleocr"
    assert app.calls == [
        ("sync_quick_settings",),
        ("save_settings",),
        ("auto_detect_current", True),
    ]


def test_combined_action_preserves_validation_scope_method_and_refresh_semantics() -> None:
    app = _App()
    app.ocr_refresh_var = _Var("force")
    controller = DetectionController(app)

    controller.run_combined_draw_action()

    assert app.settings.detection_method == "combined"
    assert app.calls == [
        ("guard",),
        ("apply_quick_settings", False),
        ("selected_page_indices",),
        ("save_settings",),
        ("detect_pages", [1, 3], "combined", True),
    ]


def test_ocr_action_preserves_reuse_refresh_semantics() -> None:
    app = _App()
    controller = DetectionController(app)

    controller.run_ocr_draw_action()

    assert app.settings.detection_method == "paddleocr"
    assert app.calls[-2:] == [
        ("save_settings",),
        ("detect_pages", [1, 3], "paddleocr", False),
    ]


def test_selected_scope_error_is_reported_without_mutating_detection_method() -> None:
    app = _App()
    problem = ValueError("bad range")
    app.selected_error = problem
    controller = DetectionController(app)

    controller.run_combined_draw_action()

    assert app.settings.detection_method == "left_edge"
    assert app.errors == [("页面范围无效", problem)]
    assert not any(call[0] in {"save_settings", "detect_pages"} for call in app.calls)


def test_action_validation_short_circuits_in_original_order() -> None:
    app = _App()
    controller = DetectionController(app)

    app.guard_result = False
    controller.run_ocr_draw_action()
    assert app.calls == [("guard",)]

    app.calls.clear()
    app.guard_result = True
    app.apply_result = False
    controller.run_combined_draw_action()
    assert app.calls == [("guard",), ("apply_quick_settings", False)]


def test_run_ocr_draw_preserves_current_and_all_scope_routing_without_save_settings() -> None:
    app = _App()
    controller = DetectionController(app)

    controller.run_ocr_draw("current", True)
    assert app.settings.detection_method == "paddleocr"
    assert app.calls[-1] == ("detect_pages", [2], "paddleocr", True)
    assert ("save_settings",) not in app.calls

    app.calls.clear()
    controller.run_ocr_draw("all", False)
    assert app.calls[-1] == ("detect_pages", [0, 1, 2, 3], "paddleocr", False)
    assert ("selected_page_indices",) not in app.calls


def test_detection_controller_has_no_reverse_dependency_on_app_module() -> None:
    path = ROOT / "src/picture_capture/ui/controllers/detection.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_detection_controller_wiring_preserves_app_methods_and_runtime_guard_seam() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (
        ROOT / "src/picture_capture/ui/controllers/detection.py"
    ).read_text(encoding="utf-8")
    ocr_guard = (
        ROOT / "src/picture_capture/ocr_action_guard.py"
    ).read_text(encoding="utf-8")
    ordinary_runtime = (
        ROOT / "src/picture_capture/ordinary_action_runtime.py"
    ).read_text(encoding="utf-8")

    imports = app[: app.index("class PictureCaptureApp")]
    assert "DetectionController" in imports
    assert "self.detection_controller = DetectionController(self)" in app
    assert app.index("self.detection_controller = DetectionController(self)") < app.index("self._build_ui()")
    assert "def _detection_controller_for_call(" in app
    assert 'self.__dict__.get("detection_controller")' in app

    expected = {
        "paddle_detect_current": "paddle_detect_current",
        "run_combined_draw_action": "run_combined_draw_action",
        "run_ocr_draw_action": "run_ocr_draw_action",
        "run_ocr_draw": "run_ocr_draw",
    }
    for app_method, controller_method in expected.items():
        assert f"def {app_method}(" in app
        assert f"self._detection_controller_for_call().{controller_method}" in app
        assert f"def {controller_method}(" in controller

    # Phase 4G keeps the compatibility method names that the legacy guard wraps.
    assert '"run_ocr_draw_action"' in ocr_guard
    assert '"run_combined_draw_action"' in ocr_guard

    # Ordinary drawing remains with its runtime adapter until Phase 5 removes it.
    assert "def run_normal_draw_action(self)" in ordinary_runtime
    assert "run_normal_draw_action" not in controller
