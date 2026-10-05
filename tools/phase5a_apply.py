from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# app.py: make the ordinary action an explicit compatibility wrapper.
app_path = ROOT / "src" / "picture_capture" / "app.py"
app = app_path.read_text(encoding="utf-8")
if "    def run_normal_draw_action(self) -> None:\n" not in app:
    marker = "    def auto_detect_current(\n"
    wrapper = (
        "    def run_normal_draw_action(self) -> None:\n"
        "        self._detection_controller_for_call().run_normal_draw_action()\n\n"
    )
    app = replace_once(app, marker, wrapper + marker, label="app ordinary wrapper")
app_path.write_text(app, encoding="utf-8")


# DetectionController: own the ordinary action while reusing the OCR-independent
# quick-settings helper that is also consumed by single-line postproduction.
detection_path = ROOT / "src" / "picture_capture" / "ui" / "controllers" / "detection.py"
detection = detection_path.read_text(encoding="utf-8")
detection = detection.replace(
    "This controller owns the stable detection action-entry seams, batch OCR\n"
    "orchestration, and the current-page detection worker/batch bridge.  The heavy\n"
    "multi-page detection pipeline, generic batch runner, and broader app/UI\n"
    "persistence infrastructure remain on ``PictureCaptureApp``.\n\n"
    "``run_normal_draw_action`` is deliberately excluded for now because the legacy\n"
    "``ordinary_action_runtime`` installer replaces that app method at runtime.  It\n"
    "should move only when Phase 5 removes that installer so ownership matches the\n"
    "actual execution path.\n",
    "This controller owns the stable detection action-entry seams, including the\n"
    "ordinary OCR-independent drawing action, batch OCR orchestration, and the\n"
    "current-page detection worker/batch bridge.  The heavy multi-page detection\n"
    "pipeline, generic batch runner, and broader app/UI persistence infrastructure\n"
    "remain on ``PictureCaptureApp``.\n",
)
if "from ...ordinary_action_runtime import _apply_quick_settings_for_ordinary\n" not in detection:
    detection = replace_once(
        detection,
        "from ...image_utils import normalize_page_rgb\n",
        "from ...image_utils import normalize_page_rgb\n"
        "from ...ordinary_action_runtime import _apply_quick_settings_for_ordinary\n",
        label="detection ordinary helper import",
    )
if "    def run_normal_draw_action(self) -> None:\n" not in detection:
    marker = "    def paddle_detect_current(self, force_refresh: bool = False) -> None:\n"
    method = '''    def run_normal_draw_action(self) -> None:\n        """Run ordinary OCR-independent drawing for the selected page scope."""\n        app = self.app\n        if not app.guard() or not _apply_quick_settings_for_ordinary(app):\n            return\n        try:\n            indices = app.selected_page_indices()\n        except Exception as exc:\n            app.show_error("页面范围无效", exc)\n            return\n        app.settings.detection_method = "left_edge"\n        app.save_settings()\n        app._detect_pages(indices, method="left_edge", force_refresh=False)\n\n'''
    detection = replace_once(detection, marker, method + marker, label="detection ordinary method")
detection_path.write_text(detection, encoding="utf-8")


# ordinary_action_runtime.py: retain only the reusable validator.  The runtime
# method installer is retired in Phase 5A.
ordinary_path = ROOT / "src" / "picture_capture" / "ordinary_action_runtime.py"
ordinary = ordinary_path.read_text(encoding="utf-8")
ordinary = ordinary.replace(
    '"""Keep the OCR-free ordinary drawing entry path independent from OCR setup.\n',
    '"""OCR-independent quick-setting helper for ordinary drawing/cropping paths.\n',
    1,
)
installer_marker = "\ndef install_ordinary_action_runtime(app_module: Any) -> None:\n"
if installer_marker in ordinary:
    start = ordinary.index(installer_marker)
    ordinary = ordinary[:start].rstrip() + "\n\n\n__all__ = [\"_apply_quick_settings_for_ordinary\"]\n"
if "install_ordinary_action_runtime" in ordinary:
    raise RuntimeError("ordinary runtime installer was not fully removed")
ordinary_path.write_text(ordinary, encoding="utf-8")


# GUI composition root: no longer install the retired method monkey patch.
gui_path = ROOT / "src" / "picture_capture" / "bootstrap" / "gui.py"
gui = gui_path.read_text(encoding="utf-8")
gui = gui.replace(
    "    from ..ordinary_action_runtime import install_ordinary_action_runtime\n",
    "",
)
gui = gui.replace("    install_ordinary_action_runtime(app_module)\n", "")
if "install_ordinary_action_runtime" in gui:
    raise RuntimeError("GUI composition still references retired ordinary installer")
gui_path.write_text(gui, encoding="utf-8")


# Controller tests: add behavior coverage and transfer source-shape ownership.
test_detection_path = ROOT / "tests" / "test_ui_detection_controller.py"
test_detection = test_detection_path.read_text(encoding="utf-8")
if "def test_normal_action_preserves_ocr_independent_validation_scope_and_left_edge_routing" not in test_detection:
    marker = "\ndef test_ocr_action_preserves_reuse_refresh_semantics() -> None:\n"
    test = '''\ndef test_normal_action_preserves_ocr_independent_validation_scope_and_left_edge_routing() -> None:\n    app = _App()\n    controller = DetectionController(app)\n\n    controller.run_normal_draw_action()\n\n    assert app.settings.detection_method == "left_edge"\n    assert app.calls == [\n        ("guard",),\n        ("apply_quick_settings", False),\n        ("selected_page_indices",),\n        ("save_settings",),\n        ("detect_pages", [1, 3], "left_edge", False),\n    ]\n\n'''
    test_detection = replace_once(test_detection, marker, test + marker, label="ordinary behavior test")
test_detection = replace_once(
    test_detection,
    '        "auto_detect_current": "auto_detect_current",\n',
    '        "auto_detect_current": "auto_detect_current",\n'
    '        "run_normal_draw_action": "run_normal_draw_action",\n',
    label="ordinary expected wrapper mapping",
)
test_detection = replace_once(
    test_detection,
    '    # Ordinary drawing remains with its runtime adapter until Phase 5 removes it.\n'
    '    assert "def run_normal_draw_action(self)" in ordinary_runtime\n'
    '    controller_tree = ast.parse(controller)\n'
    '    assert not any(\n',
    '    # Phase 5A retires only the method monkey patch; the shared ordinary\n'
    '    # quick-settings helper remains reusable by postproduction paths.\n'
    '    assert "def install_ordinary_action_runtime" not in ordinary_runtime\n'
    '    assert "def _apply_quick_settings_for_ordinary" in ordinary_runtime\n'
    '    controller_tree = ast.parse(controller)\n'
    '    assert any(\n',
    label="ordinary ownership assertion",
)
test_detection_path.write_text(test_detection, encoding="utf-8")


# Runtime-entry tests: keep helper semantics, but assert bootstrap no longer
# installs a dynamic method.
runtime_test_path = ROOT / "tests" / "test_runtime_entry_path_guards.py"
runtime_test = runtime_test_path.read_text(encoding="utf-8")
old_block = '''def test_gui_composition_installs_ordinary_action_runtime():\n    source = _gui_composition_source()\n    assert "install_ordinary_action_runtime" in source\n    assert "install_ordinary_action_runtime(app_module)" in source\n\n    ordinary_source = (\n        Path(__file__).resolve().parents[1]\n        / "src"\n        / "picture_capture"\n        / "ordinary_action_runtime.py"\n    ).read_text(encoding="utf-8")\n    assert 'self.settings.detection_method = "left_edge"' in ordinary_source\n    assert 'self._detect_pages(indices, method="left_edge", force_refresh=False)' in ordinary_source\n\n\n'''
new_block = '''def test_gui_composition_no_longer_installs_ordinary_action_runtime():\n    source = _gui_composition_source()\n    assert "install_ordinary_action_runtime" not in source\n\n    ordinary_source = (\n        Path(__file__).resolve().parents[1]\n        / "src"\n        / "picture_capture"\n        / "ordinary_action_runtime.py"\n    ).read_text(encoding="utf-8")\n    assert "def install_ordinary_action_runtime" not in ordinary_source\n    assert "def _apply_quick_settings_for_ordinary" in ordinary_source\n\n    controller_source = (\n        Path(__file__).resolve().parents[1]\n        / "src"\n        / "picture_capture"\n        / "ui"\n        / "controllers"\n        / "detection.py"\n    ).read_text(encoding="utf-8")\n    assert 'app.settings.detection_method = "left_edge"' in controller_source\n    assert 'app._detect_pages(indices, method="left_edge", force_refresh=False)' in controller_source\n\n\n'''
runtime_test = replace_once(runtime_test, old_block, new_block, label="runtime installer regression")
runtime_test_path.write_text(runtime_test, encoding="utf-8")


# Hard scope guards for this migration.
assert "install_ordinary_action_runtime" not in gui_path.read_text(encoding="utf-8")
assert "def install_ordinary_action_runtime" not in ordinary_path.read_text(encoding="utf-8")
assert "def run_normal_draw_action(self)" in app_path.read_text(encoding="utf-8")
assert "def run_normal_draw_action(self)" in detection_path.read_text(encoding="utf-8")
