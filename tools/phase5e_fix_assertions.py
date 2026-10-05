from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    ROOT / "tests/test_ui_crop_controller.py",
    '''    runtime = (
        ROOT / "src/picture_capture/postproduction_single_line_runtime.py"
    ).read_text(encoding="utf-8")
    controller = (
''',
    '''    runtime_path = ROOT / "src/picture_capture/postproduction_single_line_runtime.py"
    controller = (
''',
)
replace_once(
    ROOT / "tests/test_ui_crop_controller.py",
    '''    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" not in runtime
    assert "def split_single_lines_selected_scope(self)" in app
    assert "self._crop_controller_for_call().split_single_lines_selected_scope()" in app
    assert "split_lines_current" not in runtime
''',
    '''    assert not runtime_path.exists()
    assert "def split_single_lines_selected_scope(self)" in app
    assert "self._crop_controller_for_call().split_single_lines_selected_scope()" in app
''',
)

replace_once(
    ROOT / "tests/test_ui_crop_controller_selected_scope.py",
    '''    runtime_text = (
        ROOT / "src/picture_capture/postproduction_single_line_runtime.py"
    ).read_text(encoding="utf-8")

''',
    '''    runtime_path = ROOT / "src/picture_capture/postproduction_single_line_runtime.py"

''',
)
replace_once(
    ROOT / "tests/test_ui_crop_controller_selected_scope.py",
    '''    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" not in runtime_text
    assert "def split_single_lines_selected_scope(self)" in app_text
''',
    '''    assert not runtime_path.exists()
    assert "def split_single_lines_selected_scope(self)" in app_text
''',
)

replace_once(
    ROOT / "tests/test_ui_illustration_controller.py",
    '''    runtime = (
        ROOT / "src/picture_capture/postproduction_single_line_runtime.py"
    ).read_text(encoding="utf-8")

''',
    '''    runtime_path = ROOT / "src/picture_capture/postproduction_single_line_runtime.py"

''',
)
replace_once(
    ROOT / "tests/test_ui_illustration_controller.py",
    '''    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" not in runtime
    assert "install_postproduction_single_line_runtime" not in runtime
    assert "def _snapshot_scope(app: Any)" in runtime
    assert "def start_single_line_export(app: Any)" not in runtime
    assert "threading.Thread(" not in runtime
    assert "detect_illustrations_selected_scope" not in runtime
    assert "split_illustrations_selected_scope" not in runtime
''',
    '''    assert not runtime_path.exists()
    assert "def _snapshot_scope(app: Any)" in (
        ROOT / "src/picture_capture/ui/controllers/crop.py"
    ).read_text(encoding="utf-8")
''',
)

replace_once(
    ROOT / "tests/test_ui_illustration_crop_controller.py",
    '''    runtime = (
        ROOT / "src/picture_capture/postproduction_single_line_runtime.py"
    ).read_text(encoding="utf-8")

''',
    '''    runtime_path = ROOT / "src/picture_capture/postproduction_single_line_runtime.py"

''',
)
replace_once(
    ROOT / "tests/test_ui_illustration_crop_controller.py",
    '''    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" not in runtime
    assert "install_postproduction_single_line_runtime" not in runtime
    assert "def _snapshot_scope(app: Any)" in runtime
    assert "def start_single_line_export(app: Any)" not in runtime
    assert "threading.Thread(" not in runtime
    assert "split_illustrations_selected_scope" not in runtime
''',
    '''    assert not runtime_path.exists()
    assert "def _snapshot_scope(app: Any)" in (
        ROOT / "src/picture_capture/ui/controllers/crop.py"
    ).read_text(encoding="utf-8")
''',
)

replace_once(
    ROOT / "tests/test_core.py",
    '''        first_row = (
            '(("单行切图", self.split_single_lines_selected_scope), '
            '("词条切图", self.split_entries_selected_scope), '
            '("插图切图", self.split_illustrations_selected_scope))'
        )
''',
    '''        first_row = (
            '(("单行切图", self.split_single_lines_selected_scope), '
            '("未画线行导出", self.export_unlined_rows_selected_scope), '
            '("词条切图", self.split_entries_selected_scope), '
            '("插图切图", self.split_illustrations_selected_scope))'
        )
''',
)

print("Phase 5E stale ownership assertions updated")
