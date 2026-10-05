from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/picture_capture/app.py"
CONTROLLER = ROOT / "src/picture_capture/ui/controllers/detection.py"
TEST = ROOT / "tests/test_ui_detection_controller.py"

app = APP.read_text(encoding="utf-8")
controller = CONTROLLER.read_text(encoding="utf-8")
test = TEST.read_text(encoding="utf-8")

old_app = '''    def batch_auto_detect(self, force_paddle_refresh: bool = False) -> None:\n        if not self.project: return\n        self._detect_pages(\n            list(range(len(self.project.images))),\n            method=self.settings.detection_method,\n            force_refresh=force_paddle_refresh,\n        )\n'''
new_app = '''    def batch_auto_detect(self, force_paddle_refresh: bool = False) -> None:\n        self._detection_controller_for_call().batch_auto_detect(force_paddle_refresh)\n'''
assert app.count(old_app) == 1, "live batch_auto_detect body drifted"
app = app.replace(old_app, new_app, 1)

marker = '''    def run_ocr_draw(self, scope: str, force_refresh: bool) -> None:\n'''
method = '''    def batch_auto_detect(self, force_paddle_refresh: bool = False) -> None:\n        app = self.app\n        if not app.project:\n            return\n        app._detect_pages(\n            list(range(len(app.project.images))),\n            method=app.settings.detection_method,\n            force_refresh=force_paddle_refresh,\n        )\n\n'''
assert controller.count(marker) == 1
assert "    def batch_auto_detect(" not in controller
controller = controller.replace(marker, method + marker, 1)

old_expected = '''        "run_ocr_draw_action": "run_ocr_draw_action",\n        "run_ocr_draw": "run_ocr_draw",\n'''
new_expected = '''        "run_ocr_draw_action": "run_ocr_draw_action",\n        "batch_auto_detect": "batch_auto_detect",\n        "run_ocr_draw": "run_ocr_draw",\n'''
assert test.count(old_expected) == 1
test = test.replace(old_expected, new_expected, 1)

insert_marker = '''def test_detection_controller_has_no_reverse_dependency_on_app_module() -> None:\n'''
new_tests = '''def test_batch_auto_detect_preserves_all_project_pages_current_method_and_refresh() -> None:\n    app = _App()\n    app.settings.detection_method = "combined"\n    controller = DetectionController(app)\n\n    controller.batch_auto_detect(force_paddle_refresh=True)\n\n    assert app.calls == [\n        ("detect_pages", [0, 1, 2, 3], "combined", True),\n    ]\n    assert ("save_settings",) not in app.calls\n    assert ("selected_page_indices",) not in app.calls\n\n\ndef test_batch_auto_detect_missing_project_is_exact_no_op() -> None:\n    app = _App()\n    app.project = None\n    controller = DetectionController(app)\n\n    controller.batch_auto_detect(force_paddle_refresh=True)\n\n    assert app.calls == []\n\n\n'''
assert test.count(insert_marker) == 1
test = test.replace(insert_marker, new_tests + insert_marker, 1)

APP.write_text(app, encoding="utf-8")
CONTROLLER.write_text(controller, encoding="utf-8")
TEST.write_text(test, encoding="utf-8")
