from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for relative in (
    "tests/test_ui_illustration_controller.py",
    "tests/test_ui_illustration_crop_controller.py",
):
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    old = '    assert "def start_single_line_export(app: Any)" in runtime\n'
    new = (
        '    assert "def _snapshot_scope(app: Any)" in runtime\n'
        '    assert "def start_single_line_export(app: Any)" not in runtime\n'
        '    assert "threading.Thread(" not in runtime\n'
    )
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{relative}: expected one stale runtime assertion, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

print("Phase 5D stale ownership assertions updated")
