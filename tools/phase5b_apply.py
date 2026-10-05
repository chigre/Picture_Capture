from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# app.py: add an explicit compatibility wrapper for the selected-scope
# single-line action. The runtime installer must no longer create this method.
app_path = ROOT / "src" / "picture_capture" / "app.py"
app = app_path.read_text(encoding="utf-8")
old = '''    def split_lines_current(self) -> None:\n        self._crop_controller_for_call().split_lines_current()\n\n    def split_whole_current(self) -> None:\n'''
new = '''    def split_lines_current(self) -> None:\n        self._crop_controller_for_call().split_lines_current()\n\n    def split_single_lines_selected_scope(self) -> None:\n        self._crop_controller_for_call().split_single_lines_selected_scope()\n\n    def split_whole_current(self) -> None:\n'''
app = replace_once(app, old, new, label="app selected-scope single-line wrapper")
app_path.write_text(app, encoding="utf-8")


# Runtime module: keep button insertion, __init__ wrapping, worker/thread/polling,
# but expose the scheduler as an explicit helper and stop monkey-patching the app method.
runtime_path = ROOT / "src" / "picture_capture" / "postproduction_single_line_runtime.py"
runtime = runtime_path.read_text(encoding="utf-8")
runtime = replace_once(
    runtime,
    "def _start_single_line_export(app: Any) -> None:\n",
    "def start_single_line_export(app: Any) -> None:\n",
    label="runtime scheduler public name",
)
method_patch = '''\n    def split_single_lines_selected_scope(self) -> None:\n        _start_single_line_export(self)\n\n    app_class.split_single_lines_selected_scope = split_single_lines_selected_scope\n\n'''
runtime = replace_once(runtime, method_patch, "\n", label="runtime method monkey patch")
runtime = replace_once(
    runtime,
    '''__all__ = [\n    "install_postproduction_single_line_runtime",\n]\n''',
    '''__all__ = [\n    "install_postproduction_single_line_runtime",\n    "start_single_line_export",\n]\n''',
    label="runtime public exports",
)
if "app_class.split_single_lines_selected_scope" in runtime:
    raise RuntimeError("runtime still monkey-patches split_single_lines_selected_scope")
if "_start_single_line_export" in runtime:
    raise RuntimeError("stale private single-line scheduler name remains")
runtime_path.write_text(runtime, encoding="utf-8")


# CropController becomes the explicit action owner while the runtime module
# deliberately retains its independent worker/poll implementation for a later slice.
crop_path = ROOT / "src" / "picture_capture" / "ui" / "controllers" / "crop.py"
crop = crop_path.read_text(encoding="utf-8")
crop = replace_once(
    crop,
    '''Crop geometry and file generation remain in ``processing`` and project path\npolicy remains in ``project_storage``. Crop-settings UI, illustration actions,\nand the runtime-installed ``split_single_lines_selected_scope`` path remain\noutside this controller phase.\n''',
    '''Crop geometry and file generation remain in ``processing`` and project path\npolicy remains in ``project_storage``. Crop-settings UI and illustration actions\nremain outside this controller. The selected-scope single-line action is explicit\nhere, while its temporary Tk worker/poll scheduler remains runtime-owned.\n''',
    label="crop ownership docstring",
)
crop = replace_once(
    crop,
    "from ...formats import pdic_path, read_pdic, read_ppp\n",
    "from ...formats import pdic_path, read_pdic, read_ppp\n"
    "from ...postproduction_single_line_runtime import start_single_line_export\n",
    label="crop runtime scheduler import",
)
crop = replace_once(
    crop,
    '''    def __init__(self, app: Any) -> None:\n        self.app = app\n\n    def split_lines_current(self) -> None:\n''',
    '''    def __init__(self, app: Any) -> None:\n        self.app = app\n\n    def split_single_lines_selected_scope(self) -> None:\n        """Start selected-scope single-line export through the retained Tk scheduler."""\n        start_single_line_export(self.app)\n\n    def split_lines_current(self) -> None:\n''',
    label="crop selected-scope method",
)
crop_path.write_text(crop, encoding="utf-8")


# Crop controller tests: behavior + source ownership transfer.
test_crop_path = ROOT / "tests" / "test_ui_crop_controller.py"
test_crop = test_crop_path.read_text(encoding="utf-8")
behavior_marker = "\ndef test_batch_active_short_circuits_before_guards() -> None:\n"
behavior = '''\ndef test_selected_scope_single_line_routes_to_retained_runtime_scheduler(monkeypatch) -> None:\n    app = _App()\n    calls: list[object] = []\n    monkeypatch.setattr(crop_module, "start_single_line_export", lambda value: calls.append(value))\n\n    CropController(app).split_single_lines_selected_scope()\n\n    assert calls == [app]\n\n'''
test_crop = replace_once(
    test_crop,
    behavior_marker,
    behavior + behavior_marker,
    label="crop selected-scope routing test",
)
test_crop = replace_once(
    test_crop,
    '    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" in runtime\n',
    '    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" not in runtime\n'
    '    assert "def split_single_lines_selected_scope(self)" in app\n'
    '    assert "self._crop_controller_for_call().split_single_lines_selected_scope()" in app\n',
    label="crop source ownership assertion",
)
test_crop = replace_once(
    test_crop,
    '    assert "split_single_lines_selected_scope" not in method_names\n',
    '    assert "split_single_lines_selected_scope" in method_names\n',
    label="crop method names ownership",
)
test_crop_path.write_text(test_crop, encoding="utf-8")


# Selected-scope crop regression: update the old Phase 4L runtime exclusion assertion.
selected_path = ROOT / "tests" / "test_ui_crop_controller_selected_scope.py"
selected = selected_path.read_text(encoding="utf-8")
selected = replace_once(
    selected,
    '    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" in runtime_text\n',
    '    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" not in runtime_text\n'
    '    assert "def split_single_lines_selected_scope(self)" in app_text\n'
    '    assert "self._crop_controller_for_call().split_single_lines_selected_scope()" in app_text\n'
    '    assert "def split_single_lines_selected_scope(self)" in controller_text\n',
    label="selected-scope runtime ownership assertion",
)
selected_path.write_text(selected, encoding="utf-8")


# Illustration ownership tests should continue to prove those actions did not move,
# but no longer require the retired single-line method monkey patch.
for rel in (
    "tests/test_ui_illustration_controller.py",
    "tests/test_ui_illustration_crop_controller.py",
):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" in runtime\n',
        '    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" not in runtime\n'
        '    assert "install_postproduction_single_line_runtime" in runtime\n',
        label=f"{rel} runtime boundary assertion",
    )
    path.write_text(text, encoding="utf-8")


# Runtime tests: preserve UI/bootstrap and worker semantics while asserting method
# ownership is now explicit outside the installer.
runtime_test_path = ROOT / "tests" / "test_postproduction_single_line_runtime.py"
runtime_test = runtime_test_path.read_text(encoding="utf-8")
append_test = '''\n\ndef test_phase5b_runtime_keeps_ui_and_worker_but_not_method_monkey_patch():\n    root = Path(__file__).resolve().parents[1]\n    runtime_source = (\n        root / "src" / "picture_capture" / "postproduction_single_line_runtime.py"\n    ).read_text(encoding="utf-8")\n    app_source = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")\n    crop_source = (\n        root / "src" / "picture_capture" / "ui" / "controllers" / "crop.py"\n    ).read_text(encoding="utf-8")\n\n    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" not in runtime_source\n    assert "app_class.__init__ = wrapped_init" in runtime_source\n    assert "_insert_single_line_button(self)" in runtime_source\n    assert "def start_single_line_export(app: Any)" in runtime_source\n    assert "def split_single_lines_selected_scope(self)" in app_source\n    assert "self._crop_controller_for_call().split_single_lines_selected_scope()" in app_source\n    assert "def split_single_lines_selected_scope(self)" in crop_source\n    assert "start_single_line_export(self.app)" in crop_source\n'''
if "def test_phase5b_runtime_keeps_ui_and_worker_but_not_method_monkey_patch" in runtime_test:
    raise RuntimeError("Phase 5B runtime test already present")
runtime_test = runtime_test.rstrip() + append_test + "\n"
runtime_test_path.write_text(runtime_test, encoding="utf-8")


# Final hard guards.
assert "def split_single_lines_selected_scope(self)" in app_path.read_text(encoding="utf-8")
assert "def split_single_lines_selected_scope(self)" in crop_path.read_text(encoding="utf-8")
assert "start_single_line_export(self.app)" in crop_path.read_text(encoding="utf-8")
assert "app_class.split_single_lines_selected_scope" not in runtime_path.read_text(encoding="utf-8")
assert "app_class.__init__ = wrapped_init" in runtime_path.read_text(encoding="utf-8")
assert "_insert_single_line_button(self)" in runtime_path.read_text(encoding="utf-8")
