from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tests/test_core.py"

old = '''def test_v295_illustration_crop_button_uses_shared_crop_settings_before_running_batch():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def split_illustrations_selected_scope(")
    end = text.index("    def _start_illustration_crop(", start)
    block = text[start:end]
    assert "self._start_illustration_crop(indices, self._load_crop_settings())" in block
    assert "_start_parallel_batch_task" not in block
'''

new = '''def test_v295_illustration_crop_button_uses_shared_crop_settings_before_running_batch():
    root = Path(__file__).resolve().parents[1]
    app_text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    controller_text = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "illustration.py"
    ).read_text(encoding="utf-8")

    app_start = app_text.index("    def split_illustrations_selected_scope(")
    app_end = app_text.index("    def _start_illustration_crop(", app_start)
    app_block = app_text[app_start:app_end]
    assert "self._illustration_controller_for_call().split_illustrations_selected_scope()" in app_block

    controller_start = controller_text.index("    def split_illustrations_selected_scope(")
    controller_end = controller_text.index("    def detect_illustrations_selected_scope(", controller_start)
    controller_block = controller_text[controller_start:controller_end]
    assert "app._start_illustration_crop(indices, app._load_crop_settings())" in controller_block
    assert "_start_parallel_batch_task" not in controller_block
'''

text = PATH.read_text(encoding="utf-8")
assert text.count(old) == 1, "expected exactly one stale v2.9.5 illustration-crop source-shape test"
PATH.write_text(text.replace(old, new, 1), encoding="utf-8")
