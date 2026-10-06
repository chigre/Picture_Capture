from __future__ import annotations

from pathlib import Path

path = Path(__file__).with_name("phase5q_apply.py")
text = path.read_text(encoding="utf-8")
start_marker = '''replace_between(
    "tests/test_layout_column_drift_runtime.py",
'''
end_marker = '''
replace_once(
    "tests/test_runtime_entry_path_guards.py",
'''
if text.count(start_marker) != 1 or text.count(end_marker) != 1:
    raise SystemExit("phase5q_apply.py: expected one column-test migration block")
start = text.index(start_marker)
end = text.index(end_marker, start)
replacement = '''column_test = ROOT / "tests/test_layout_column_drift_runtime.py"
column_text = column_test.read_text(encoding="utf-8")
column_marker = "def test_runtime_order_is_preserved_across_core_gui_and_worker_composition():\\n"
if column_text.count(column_marker) != 1:
    raise SystemExit(
        f"tests/test_layout_column_drift_runtime.py: expected one final runtime-order test, found {column_text.count(column_marker)}"
    )
column_start = column_text.index(column_marker)
column_replacement = \'\'\'def test_static_row_recovery_keeps_column_drift_runtime_explicit():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    core = (root / "src/picture_capture/bootstrap/core.py").read_text(encoding="utf-8")
    gui = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")
    worker = (root / "src/picture_capture/bootstrap/worker.py").read_text(encoding="utf-8")
    physical = (root / "src/picture_capture/layout_physical_indent.py").read_text(encoding="utf-8")

    # Shared process setup is complete before processing is imported.
    assert core.index("install_ordinary_large_head_role_guard()") < core.index(
        "from .. import processing as processing_module"
    )

    # Row recovery is static; the broader column-drift seam remains explicit.
    assert "install_layout_row_recovery_runtime" not in gui
    assert "install_layout_row_recovery_runtime" not in worker
    assert "install_layout_column_drift_runtime()" in gui
    assert "install_layout_column_drift_runtime()" in worker
    assert "count = min(256, count)" in physical
\'\'\'
column_test.write_text(column_text[:column_start] + column_replacement, encoding="utf-8")
'''
path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
print("Phase 5Q helper prepared with EOF-safe column-test migration")
