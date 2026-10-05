from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# app.py: construct the single-line button in the normal postproduction UI row.
app_path = ROOT / "src" / "picture_capture" / "app.py"
app = app_path.read_text(encoding="utf-8")
app = replace_once(
    app,
    '        production_tooltips = {\n            "词条切图": "按所选页面范围和【设置中心 → 切图】生成完整词条切图。",\n',
    '        production_tooltips = {\n'
    '            "单行切图": (\n'
    '                "将【选定范围】内各页按校对界面相同的单行裁切逻辑批量输出到 QT/PSW；"\n'
    '                "可在【设置中心 → 切图】选择是否按页合并，并复用切图并行进程数。"\n'
    '            ),\n'
    '            "词条切图": "按所选页面范围和【设置中心 → 切图】生成完整词条切图。",\n',
    label="app single-line tooltip",
)
app = replace_once(
    app,
    '            (("词条切图", self.split_entries_selected_scope), ("插图切图", self.split_illustrations_selected_scope)),\n',
    '            (("单行切图", self.split_single_lines_selected_scope), ("词条切图", self.split_entries_selected_scope), ("插图切图", self.split_illustrations_selected_scope)),\n',
    label="app postproduction first row",
)
app = replace_once(
    app,
    '                button = self._sidebar_action_button(row, text, command)\n                tooltip = production_tooltips.get(text)\n',
    '                button = self._sidebar_action_button(row, text, command)\n'
    '                if text == "单行切图":\n'
    '                    self._pc_single_line_crop_button = button\n'
    '                tooltip = production_tooltips.get(text)\n',
    label="app direct single-line button reference",
)
app_path.write_text(app, encoding="utf-8")


# Runtime: retain selected-scope snapshot + thread/queue/Tk poll scheduler only.
runtime_path = ROOT / "src" / "picture_capture" / "postproduction_single_line_runtime.py"
runtime = runtime_path.read_text(encoding="utf-8")
runtime = replace_once(runtime, "from functools import wraps\n", "", label="runtime wraps import")
runtime = replace_once(
    runtime,
    "from typing import Any, Iterable\n",
    "from typing import Any\n",
    label="runtime Iterable import",
)
runtime = replace_once(
    runtime,
    "from tkinter import messagebox, ttk\n",
    "from tkinter import messagebox\n",
    label="runtime ttk import",
)
ui_start = runtime.index('_BUTTON_TEXT = "单行切图"')
ui_end = runtime.index("def _set_job_button_state(app: Any, active: bool) -> None:")
runtime = runtime[:ui_start] + runtime[ui_end:]
installer_start = runtime.index("\ndef install_postproduction_single_line_runtime(app_module: Any) -> None:")
runtime = runtime[:installer_start].rstrip() + '\n\n\n__all__ = [\n    "start_single_line_export",\n]\n'
for forbidden in (
    "install_postproduction_single_line_runtime",
    "app_class.__init__ = wrapped_init",
    "_insert_single_line_button",
    "_find_postproduction_entry_crop_button",
    "_pack_before",
    "_grid_before",
    '_BUTTON_TEXT = "单行切图"',
    '_TARGET_TEXT = "词条切图"',
):
    if forbidden in runtime:
        raise RuntimeError(f"runtime UI/bootstrap seam remains: {forbidden}")
for required in (
    "def start_single_line_export(app: Any) -> None:",
    "threading.Thread(",
    'queue.Queue[tuple[str, Any]]',
    "app.after(80, poll)",
    "def _snapshot_scope(app: Any)",
    "def _set_job_button_state(app: Any, active: bool)",
):
    if required not in runtime:
        raise RuntimeError(f"runtime worker/poll seam unexpectedly missing: {required}")
runtime_path.write_text(runtime, encoding="utf-8")


# GUI composition root: no installer is needed for the now-normal app UI button.
gui_path = ROOT / "src" / "picture_capture" / "bootstrap" / "gui.py"
gui = gui_path.read_text(encoding="utf-8")
gui = replace_once(
    gui,
    '    from ..postproduction_single_line_runtime import (\n        install_postproduction_single_line_runtime,\n    )\n',
    "",
    label="gui single-line installer import",
)
gui = replace_once(
    gui,
    '    # Install in this order: the unlined-row action locates the concrete\n'
    '    # 【单行切图】 button and inserts itself immediately to its right.\n'
    '    install_postproduction_single_line_runtime(app_module)\n'
    '    install_unlined_line_export_ui(app_module)\n',
    '    # The app now constructs 【单行切图】 in its normal postproduction row.\n'
    '    # The unlined-row installer can therefore resolve that concrete button\n'
    '    # after normal app construction and insert itself immediately to its right.\n'
    '    install_unlined_line_export_ui(app_module)\n',
    label="gui single-line installer call",
)
if "install_postproduction_single_line_runtime" in gui:
    raise RuntimeError("GUI composition still installs single-line runtime UI")
gui_path.write_text(gui, encoding="utf-8")


# Direct runtime/UI ownership tests.
test_runtime_path = ROOT / "tests" / "test_postproduction_single_line_runtime.py"
test_runtime = test_runtime_path.read_text(encoding="utf-8")
test_runtime = replace_once(
    test_runtime,
    '    worker_source = (root / "src" / "picture_capture" / "single_line_parallel.py").read_text(\n        encoding="utf-8"\n    )\n\n'
    '    assert \'_BUTTON_TEXT = "单行切图"\' in runtime_source\n'
    '    assert \'_TARGET_TEXT = "词条切图"\' in runtime_source\n'
    '    assert "_pack_before(button, target)" in runtime_source\n'
    '    assert "_grid_before(button, target)" in runtime_source\n'
    '    assert "app.selected_page_indices()" in runtime_source\n',
    '    worker_source = (root / "src" / "picture_capture" / "single_line_parallel.py").read_text(\n'
    '        encoding="utf-8"\n'
    '    )\n'
    '    app_source = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")\n\n'
    '    assert (\n'
    '        \'(("单行切图", self.split_single_lines_selected_scope), \'\n'
    '        \'("词条切图", self.split_entries_selected_scope), \'\n'
    '        \'("插图切图", self.split_illustrations_selected_scope))\'\n'
    '    ) in app_source\n'
    '    assert \'if text == "单行切图":\' in app_source\n'
    '    assert "self._pc_single_line_crop_button = button" in app_source\n'
    '    assert "app.selected_page_indices()" in runtime_source\n',
    label="runtime contract direct UI assertions",
)
test_runtime = replace_once(
    test_runtime,
    'def test_gui_composition_installs_single_line_postproduction_extension():\n'
    '    root = Path(__file__).resolve().parents[1]\n'
    '    source = (\n'
    '        root / "src" / "picture_capture" / "bootstrap" / "gui.py"\n'
    '    ).read_text(encoding="utf-8")\n'
    '    assert "install_postproduction_single_line_runtime" in source\n'
    '    assert "install_postproduction_single_line_runtime(app_module)" in source\n',
    'def test_gui_composition_no_longer_installs_single_line_ui_runtime():\n'
    '    root = Path(__file__).resolve().parents[1]\n'
    '    source = (\n'
    '        root / "src" / "picture_capture" / "bootstrap" / "gui.py"\n'
    '    ).read_text(encoding="utf-8")\n'
    '    assert "install_postproduction_single_line_runtime" not in source\n'
    '    assert "install_unlined_line_export_ui(app_module)" in source\n',
    label="gui composition ownership test",
)
test_runtime = replace_once(
    test_runtime,
    'def test_phase5b_runtime_keeps_ui_and_worker_but_not_method_monkey_patch():\n',
    'def test_phase5c_runtime_keeps_worker_poll_but_no_ui_or_method_monkey_patch():\n',
    label="phase5c runtime test name",
)
test_runtime = replace_once(
    test_runtime,
    '    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" not in runtime_source\n'
    '    assert "app_class.__init__ = wrapped_init" in runtime_source\n'
    '    assert "_insert_single_line_button(self)" in runtime_source\n'
    '    assert "def start_single_line_export(app: Any)" in runtime_source\n',
    '    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" not in runtime_source\n'
    '    assert "app_class.__init__ = wrapped_init" not in runtime_source\n'
    '    assert "_insert_single_line_button" not in runtime_source\n'
    '    assert "install_postproduction_single_line_runtime" not in runtime_source\n'
    '    assert "def start_single_line_export(app: Any)" in runtime_source\n'
    '    assert "threading.Thread(" in runtime_source\n'
    '    assert "app.after(80, poll)" in runtime_source\n'
    '    assert \'if text == "单行切图":\' in app_source\n'
    '    assert "self._pc_single_line_crop_button = button" in app_source\n',
    label="phase5c runtime boundary assertions",
)
test_runtime_path.write_text(test_runtime, encoding="utf-8")


# Unlined UI remains runtime-owned but now depends on the app-created button.
unlined_test_path = ROOT / "tests" / "test_unlined_line_export.py"
unlined_test = unlined_test_path.read_text(encoding="utf-8")
unlined_test = replace_once(
    unlined_test,
    '    ui = (root / "src" / "picture_capture" / "unlined_line_export_ui.py").read_text(encoding="utf-8")\n',
    '    ui = (root / "src" / "picture_capture" / "unlined_line_export_ui.py").read_text(encoding="utf-8")\n'
    '    app_source = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")\n',
    label="unlined app source",
)
unlined_test = replace_once(
    unlined_test,
    '    assert \'install_postproduction_single_line_runtime(app_module)\' in composition\n'
    '    assert \'install_unlined_line_export_ui(app_module)\' in composition\n'
    '    assert \'install_unlined_export_filter_settings_ui(app_module)\' in composition\n'
    '    assert composition.index(\'install_postproduction_single_line_runtime(app_module)\') < composition.index(\n'
    '        \'install_unlined_line_export_ui(app_module)\'\n'
    '    )\n',
    '    assert \'install_postproduction_single_line_runtime(app_module)\' not in composition\n'
    '    assert \'install_unlined_line_export_ui(app_module)\' in composition\n'
    '    assert \'install_unlined_export_filter_settings_ui(app_module)\' in composition\n'
    '    assert (\n'
    '        \'(("单行切图", self.split_single_lines_selected_scope), \'\n'
    '        \'("词条切图", self.split_entries_selected_scope), \'\n'
    '        \'("插图切图", self.split_illustrations_selected_scope))\'\n'
    '    ) in app_source\n'
    '    assert "self._pc_single_line_crop_button = button" in app_source\n',
    label="unlined normal single-line dependency",
)
unlined_test_path.write_text(unlined_test, encoding="utf-8")


# Phase 4 illustration tests should record that the unrelated single-line UI
# installer is now gone, while the worker runtime file itself deliberately remains.
for rel in (
    "tests/test_ui_illustration_controller.py",
    "tests/test_ui_illustration_crop_controller.py",
):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    assert "install_postproduction_single_line_runtime" in runtime\n',
        '    assert "install_postproduction_single_line_runtime" not in runtime\n'
        '    assert "def start_single_line_export(app: Any)" in runtime\n',
        label=f"{rel} Phase 5C single-line boundary",
    )
    path.write_text(text, encoding="utf-8")


# Hard scope guards.
final_app = app_path.read_text(encoding="utf-8")
final_runtime = runtime_path.read_text(encoding="utf-8")
final_gui = gui_path.read_text(encoding="utf-8")
assert '(("单行切图", self.split_single_lines_selected_scope), ("词条切图", self.split_entries_selected_scope), ("插图切图", self.split_illustrations_selected_scope))' in final_app
assert 'if text == "单行切图":' in final_app
assert "self._pc_single_line_crop_button = button" in final_app
assert "install_postproduction_single_line_runtime" not in final_runtime
assert "app_class.__init__ = wrapped_init" not in final_runtime
assert "def start_single_line_export(app: Any)" in final_runtime
assert "threading.Thread(" in final_runtime
assert "app.after(80, poll)" in final_runtime
assert "install_postproduction_single_line_runtime" not in final_gui
assert "install_unlined_line_export_ui(app_module)" in final_gui
