from pathlib import Path

crop_test = Path("tests/test_ui_illustration_crop_controller.py")
text = crop_test.read_text(encoding="utf-8")
old = '''    assert (\n        \"def _start_illustration_crop(self, indices: list[int], config: dict) -> None:\\n\"\n        \"        self._illustration_controller_for_call()._start_illustration_crop(indices, config)\"\n    ) in app\n'''
new = '''    app_runner_start = app.index(\"    def _start_illustration_crop(\")\n    app_runner_end = app.index(\"    def build_picdic(\", app_runner_start)\n    app_runner_block = app[app_runner_start:app_runner_end]\n    assert \"self._illustration_controller_for_call()._start_illustration_crop(indices, config)\" in app_runner_block\n'''
assert text.count(old) == 1, "expected one Phase 4O app-wrapper source-shape assertion"
text = text.replace(old, new, 1)
crop_test.write_text(text, encoding="utf-8")

core_test = Path("tests/test_core.py")
text = core_test.read_text(encoding="utf-8")
old = 'controller_end = controller_text.index("    def detect_illustrations_selected_scope(", controller_start)'
new = 'controller_end = controller_text.index("    def _start_illustration_crop(", controller_start)'
assert text.count(old) == 1, "expected one v2.9.5 illustration entry-block boundary"
text = text.replace(old, new, 1)
core_test.write_text(text, encoding="utf-8")
